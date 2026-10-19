"""
mm.ai - le module d'auth
Blueprint Flask : register / login / verify / resend-verification / me / logout.

comment ca marche :
  - les mdp sont hashés avec bcrypt.
  - JWT (PyJWT) signé avec JWT_SECRET_KEY, expire en 24h, stocké cote frontend
    dans localStorage et envoyé dans le header `Authorization: Bearer <jwt>`.
  - la vérif email est obligatoire : impossible de se connecter tant que
    email_verified = FALSE.
  - le token de verification : secrets.token_urlsafe(32), expire 24h, single-use
    (supprimé après validation).
"""
# 
# ============================================================
# [AUTH] Verify URL (copy\paste in browser):
#   http://localhost:5000/api/auth/verify?token=xxxx
# ============================================================
# 

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt as pyjwt
import psycopg2
from flask import Blueprint, jsonify, request, redirect

from email_service import send_email, render_verification_email, render_reset_email


# ---- Config ----------------------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change_me_in_production")
JWT_ALGO = "HS256"
JWT_EXPIRES_HOURS = 24

VERIFY_TOKEN_EXPIRES_HOURS = 24

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")


# ---- Helpers ---------------------------------------------------------------

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PSEUDO_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
def _make_jwt(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def _decode_jwt(token: str) -> dict | None:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        return None

def _validate_register_payload(d: dict) -> str | None:
    """Retourne un message d'erreur si invalide, None sinon."""
    required = ("pseudo", "first_name", "last_name", "age", "email", "password")
    for k in required:
        if k not in d or d[k] in (None, ""):
            return f"Missing field: {k}"
    pseudo = str(d["pseudo"]).strip()
    if not PSEUDO_RE.match(pseudo):
        return "Pseudo must be 3-20 chars (letters, digits, underscore)"
    email = str(d["email"]).strip().lower()
    if not EMAIL_RE.match(email):
        return "Invalid email format"

    try:
        age = int(d["age"])
    except (ValueError, TypeError):
        return "Age must be a number"
    if age < 13 or age > 120:
        return "Age must be between 13 and 120"
    pwd = str(d["password"])
    if len(pwd) < 8:
        return "Password must be at least 8 characters"
    first = str(d["first_name"]).strip()
    last = str(d["last_name"]).strip()
    if len(first) < 1 or len(first) > 60:
        return "First name length invalid (1-60 chars)"
    if len(last) < 1 or len(last) > 60:
        return "Last name length invalid (1-60 chars)"
    return None


# ---- Decorator -------------------------------------------------------------

def login_required(f):
    """Decorator : exige un JWT valide dans Authorization: Bearer <token>."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing_token"}), 401
        token = auth_header.split(" ", 1)[1].strip()
        payload = _decode_jwt(token)
        if not payload:
            return jsonify({"error": "invalid_token"}), 401
        try:
            request.user_id = int(payload["sub"])
        except (KeyError, ValueError):
            return jsonify({"error": "invalid_token"}), 401
        return f(*args, **kwargs)
    return wrapper


def premium_required(f):
    """
    décorateur : bloque l'accès si l'utilisateur n'est pas premium.
    à mettre sur /api/matchmaking et le Scouter quand on activera le paywall.
    """
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        # Get_conn vient de app.py (registre dans le blueprint via current_app si besoin)
        from app import get_conn
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT tier FROM users WHERE id = %s", (request.user_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "user_not_found"}), 401
            if row[0] != "premium":
                return jsonify({"error": "premium_required"}), 402
        finally:
            conn.close()
        return f(*args, **kwargs)
    return wrapper


# ---- Blueprint -------------------------------------------------------------

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/register")
def register():
    """
    Inscription. Crée user (email_verified=False), génère token, envoie email Resend.
    Retourne 201 avec un message (pas de JWT — l'user doit verifier d'abord).
    """
    data = request.get_json(silent=True) or {}
    err = _validate_register_payload(data)
    if err:
        return jsonify({"error": "validation", "detail": err}), 400

    pseudo = str(data["pseudo"]).strip()
    first_name = str(data["first_name"]).strip()
    last_name = str(data["last_name"]).strip()
    age = int(data["age"])
    email = str(data["email"]).strip().lower()
    pwd_hash = _hash_password(str(data["password"]))

    verification_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=VERIFY_TOKEN_EXPIRES_HOURS)

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (
                pseudo, first_name, last_name, age, email, password_hash,
                verification_token, verification_expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (pseudo, first_name, last_name, age, email, pwd_hash,
             verification_token, expires_at),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
    except psycopg2.errors.UniqueViolation as e:
        conn.rollback()
        detail = str(e).lower()
        if "email" in detail:
            return jsonify({"error": "email_taken"}), 409
        if "pseudo" in detail:
            return jsonify({"error": "pseudo_taken"}), 409
        return jsonify({"error": "unique_violation"}), 409
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "server_error", "detail": str(e)}), 500
    finally:
        conn.close()

    # Envoie l'email de verification
    verify_url = f"{APP_BASE_URL}/api/auth/verify?token={verification_token}"
    subject, html = render_verification_email(first_name, verify_url)
    email_result = send_email(email, subject, html)

    # Log toujours visible dans le terminal (utile en dev meme avec Resend)
    import sys
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[AUTH] New registration: {email} ({first_name} {last_name})", file=sys.stderr)
    print(f"[AUTH] Verify URL (copy/paste in browser):", file=sys.stderr)
    print(f"  {verify_url}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return jsonify({
        "ok": True,
        "user_id": user_id,
        "email": email,
        "email_sent_via": email_result.get("via"),
        "message": "Account created. Please check your inbox to verify your email.",
    }), 201


@auth_bp.get("/verify")
def verify_email():
    """
    Endpoint GET clique depuis l'email. Set email_verified=TRUE et redirige vers
    /verified.html (page front qui invite a se connecter).
    """
    token = (request.args.get("token") or "").strip()
    if not token:
        return redirect(f"{APP_BASE_URL}/verified.html?status=missing_token")

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email_verified, verification_expires_at
            FROM users
            WHERE verification_token = %s
            """,
            (token,),
        )
        row = cur.fetchone()
        if not row:
            return redirect(f"{APP_BASE_URL}/verified.html?status=invalid_token")
        user_id, already_verified, expires_at = row

        if already_verified:
            return redirect(f"{APP_BASE_URL}/verified.html?status=already")

        # on vérifie l'expiration (psycopg renvoie un datetime aware)
        if expires_at and expires_at < datetime.now(timezone.utc):
            return redirect(f"{APP_BASE_URL}/verified.html?status=expired")

        cur.execute(
            """
            UPDATE users
            SET email_verified = TRUE,
                verification_token = NULL,
                verification_expires_at = NULL
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return redirect(f"{APP_BASE_URL}/verified.html?status=ok")


@auth_bp.post("/resend-verification")
def resend_verification():
    """
    Renvoie un nouvel email de verification a un user existant non verifie.
    Body : { "email": "..." }
    Repond toujours 200 (pas de leak d'info sur l'existence du compte).
    """
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"ok": True}), 200

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, first_name, email_verified FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": True}), 200
        user_id, first_name, already_verified = row
        if already_verified:
            return jsonify({"ok": True, "already_verified": True}), 200

        new_token = secrets.token_urlsafe(32)
        new_expires = datetime.now(timezone.utc) + timedelta(hours=VERIFY_TOKEN_EXPIRES_HOURS)
        cur.execute(
            "UPDATE users SET verification_token = %s, verification_expires_at = %s WHERE id = %s",
            (new_token, new_expires, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    verify_url = f"{APP_BASE_URL}/api/auth/verify?token={new_token}"
    subject, html = render_verification_email(first_name, verify_url)
    send_email(email, subject, html)
    return jsonify({"ok": True, "resent": True}), 200


@auth_bp.post("/login")
def login():
    """
    Login par email OU pseudo + password. Strict gate : email_verified obligatoire.
    Body : { "identifier": "...", "password": "..." }
    Retourne { token, user: {id, pseudo, first_name, tier, ...} }
    """
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier", "")).strip()
    password = str(data.get("password", ""))
    if not identifier or not password:
        return jsonify({"error": "missing_credentials"}), 400

    # Email uniquement (pas de login par pseudo)
    email_input = identifier.lower()

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, pseudo, first_name, last_name, email, password_hash,
                   email_verified, tier, premium_until, avatar_data
            FROM users
            WHERE LOWER(email) = %s
            """,
            (email_input,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "invalid_credentials"}), 401

        (user_id, pseudo, first_name, last_name, email, pwd_hash,
         email_verified, tier, premium_until, avatar_data) = row

        if not _check_password(password, pwd_hash):
            return jsonify({"error": "invalid_credentials"}), 401

        if not email_verified:
            return jsonify({
                "error": "email_not_verified",
                "email": email,
            }), 403

        # Mise a jour last_login_at
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()

    token = _make_jwt(user_id, email)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "id": user_id,
            "pseudo": pseudo,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "tier": tier,
            "premium_until": premium_until.isoformat() if premium_until else None,
            "avatar_data": avatar_data,
        },
    }), 200


@auth_bp.get("/me")
@login_required
def me():
    """Retourne le user courant a partir du JWT. Sert au front pour hydrater la nav."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, pseudo, first_name, last_name, email, tier, premium_until,
                   email_verified, created_at, pseudo_changed_at, avatar_data
            FROM users
            WHERE id = %s
            """,
            (request.user_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "user_not_found"}), 404
    finally:
        conn.close()

    (uid, pseudo, first_name, last_name, email, tier, premium_until,
     email_verified, created_at, pseudo_changed_at, avatar_data) = row
    return jsonify({
        "id": uid,
        "pseudo": pseudo,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "tier": tier,
        "premium_until": premium_until.isoformat() if premium_until else None,
        "email_verified": email_verified,
        "created_at": created_at.isoformat() if created_at else None,
        "pseudo_changed_at": pseudo_changed_at.isoformat() if pseudo_changed_at else None,
        "avatar_data": avatar_data,
    }), 200


@auth_bp.post("/logout")
def logout():
    """No-op serveur. Le front efface le JWT de son cote."""
    return jsonify({"ok": True}), 200


# ---- Mot de passe oublie ----------------------------------------------------

RESET_TOKEN_EXPIRES_HOURS = 2


@auth_bp.post("/forgot-password")
def forgot_password():
    """
    Envoie un email de réinitialisation. Toujours 200 (anti-leak).
    Body : { "email": "..." }
    """
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"ok": True}), 200

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, first_name FROM users WHERE LOWER(email) = %s AND email_verified = TRUE",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": True}), 200
        user_id, first_name = row
        reset_token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRES_HOURS)
        cur.execute(
            "UPDATE users SET reset_token = %s, reset_token_expires_at = %s WHERE id = %s",
            (reset_token, expires, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    reset_url = f"{APP_BASE_URL}/reset-password.html?token={reset_token}"
    subject, html = render_reset_email(first_name, reset_url)
    send_email(email, subject, html)

    import sys
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[AUTH] Password reset requested: {email}", file=sys.stderr)
    print(f"[AUTH] Reset URL:", file=sys.stderr)
    print(f"  {reset_url}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return jsonify({"ok": True}), 200


@auth_bp.post("/reset-password")
def reset_password():
    """
    Valide le token et change le mot de passe.
    Body : { "token": "...", "password": "..." }
    """
    data = request.get_json(silent=True) or {}
    token = str(data.get("token", "")).strip()
    new_password = str(data.get("password", ""))
    if not token:
        return jsonify({"error": "missing_token"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "password_too_short", "detail": "Minimum 8 characters"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, reset_token_expires_at FROM users WHERE reset_token = %s",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "invalid_token"}), 400
        user_id, expires_at = row
        if expires_at and expires_at < datetime.now(timezone.utc):
            return jsonify({"error": "token_expired"}), 400
        new_hash = _hash_password(new_password)
        cur.execute(
            "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expires_at = NULL WHERE id = %s",
            (new_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True}), 200


# ---- Suppression de compte --------------------------------------------------

@auth_bp.delete("/me")
@login_required
def delete_account():
    """
    Supprime le compte (et toutes ses données) apres confirmation du mot de passe.
    Body : { "password": "..." }
    """
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", ""))
    if not password:
        return jsonify({"error": "password_required"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (request.user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "user_not_found"}), 404
        if not _check_password(password, row[0]):
            return jsonify({"error": "invalid_password"}), 401
        cur.execute("DELETE FROM users WHERE id = %s", (request.user_id,))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True}), 200


# ---- Profil -----------------------------------------------------------------

@auth_bp.patch("/profile")
@login_required
def update_profile():
    """
    Modifie le pseudo (une seule fois par compte, tracked via pseudo_changed_at).
    Body : { "pseudo": "..." }
    """
    data = request.get_json(silent=True) or {}
    new_pseudo = str(data.get("pseudo", "")).strip()
    if not PSEUDO_RE.match(new_pseudo):
        return jsonify({"error": "invalid_pseudo", "detail": "3-20 chars, letters/digits/underscore"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pseudo, pseudo_changed_at FROM users WHERE id = %s", (request.user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "user_not_found"}), 404
        current_pseudo, pseudo_changed_at = row
        if pseudo_changed_at is not None:
            return jsonify({"error": "pseudo_already_changed",
                            "detail": "Username can only be changed once"}), 409
        if new_pseudo.lower() == current_pseudo.lower():
            return jsonify({"error": "same_pseudo"}), 400
        cur.execute(
            "UPDATE users SET pseudo = %s, pseudo_changed_at = NOW() WHERE id = %s",
            (new_pseudo, request.user_id),
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "pseudo_taken"}), 409
    finally:
        conn.close()

    return jsonify({"ok": True, "pseudo": new_pseudo}), 200


# ---- Favoris ----------------------------------------------------------------

@auth_bp.get("/favorites")
@login_required
def get_favorites():
    """Liste les combattants favoris de l'utilisateur avec infos de base."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT f.id, f.name, f.photo_thumbnail_url, f.weight_class_current,
                   f.record_total_wins, f.record_total_losses, f.record_total_draws, f.gender,
                   f.nationality
            FROM user_favorites uf
            JOIN fighters f ON f.id = uf.fighter_id
            WHERE uf.user_id = %s
            ORDER BY uf.created_at DESC
            """,
            (request.user_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify({
        "favorites": [
            {
                "id": r[0], "name": r[1], "photo_thumbnail_url": r[2],
                "weight_class_current": r[3], "record_total_wins": r[4],
                "record_total_losses": r[5], "record_total_draws": r[6],
                "gender": r[7], "nationality": r[8],
            }
            for r in rows
        ]
    }), 200


@auth_bp.get("/favorites/ids")
@login_required
def get_favorite_ids():
    """Retourne seulement les IDs favoris (leger, pour check UI)."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT fighter_id FROM user_favorites WHERE user_id = %s", (request.user_id,))
        rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify({"ids": [r[0] for r in rows]}), 200


@auth_bp.post("/favorites/<int:fighter_id>")
@login_required
def add_favorite(fighter_id):
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_favorites (user_id, fighter_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (request.user_id, fighter_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "favorited": True}), 200


@auth_bp.delete("/favorites/<int:fighter_id>")
@login_required
def remove_favorite(fighter_id):
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_favorites WHERE user_id = %s AND fighter_id = %s",
            (request.user_id, fighter_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "favorited": False}), 200


# ---- Avatar -----------------------------------------------------------------

AVATAR_MAX_BYTES = 262144  # 256 KB base64 ~ 192 KB raw image

@auth_bp.patch("/avatar")
@login_required
def update_avatar():
    """
    Met a jour (ou supprime) l'avatar du user.
    Body : { "avatar_data": "<data:image/...;base64,...>" } ou { "avatar_data": null }
    """
    data = request.get_json(silent=True) or {}
    avatar_data = data.get("avatar_data")

    if avatar_data is not None:
        if not isinstance(avatar_data, str):
            return jsonify({"error": "invalid_avatar"}), 400
        if not avatar_data.startswith("data:image/"):
            return jsonify({"error": "invalid_avatar", "detail": "Must be a data URL"}), 400
        if len(avatar_data) > AVATAR_MAX_BYTES:
            return jsonify({"error": "avatar_too_large", "detail": "Max 200 KB"}), 400
        allowed_prefixes = ("data:image/jpeg;", "data:image/png;", "data:image/webp;", "data:image/gif;")
        if not any(avatar_data.startswith(p) for p in allowed_prefixes):
            return jsonify({"error": "invalid_type", "detail": "JPEG, PNG, WebP or GIF only"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET avatar_data = %s WHERE id = %s", (avatar_data, request.user_id))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True}), 200


# ---- Reports ----------------------------------------------------------------

REPORT_TYPES_ALLOWED = {"wrong_record", "wrong_stats", "wrong_photo", "outdated", "other"}

@auth_bp.post("/reports")
def create_report():
    """
    Signalement d'une erreur sur un combattant ou un event.
    Body : { fighter_id?, event_id?, report_type, message? }
    Pas d'auth requise (un visiteur peut signaler).
    """
    data = request.get_json(silent=True) or {}
    fighter_id = data.get("fighter_id") or None
    event_id = data.get("event_id") or None
    report_type = str(data.get("report_type", "other")).strip()
    message = str(data.get("message", "")).strip()[:500]

    if report_type not in REPORT_TYPES_ALLOWED:
        report_type = "other"
    if not fighter_id and not event_id:
        return jsonify({"error": "missing_target"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        # Create table if not exists (idempotent, run once)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          SERIAL PRIMARY KEY,
                fighter_id  INT REFERENCES fighters(id) ON DELETE SET NULL,
                event_id    INT,
                report_type VARCHAR(50) NOT NULL,
                message     TEXT,
                ip_address  TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64]
        cur.execute(
            "INSERT INTO reports (fighter_id, event_id, report_type, message, ip_address) VALUES (%s, %s, %s, %s, %s)",
            (fighter_id, event_id, report_type, message or None, ip),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "server_error", "detail": str(e)}), 500
    finally:
        conn.close()

    return jsonify({"ok": True}), 201
