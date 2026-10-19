"""
mm.ai - le module admin
Blueprint Flask : tout ce qui est reserve a l'admin (toi).

comment on devient admin :
  - PAS de colonne is_admin en base. On lit la liste ADMIN_EMAILS dans le .env
    (emails separes par virgule). Si l'email du compte connecte est dedans -> admin.
  - du coup rien a toggler en base, impossible d'escalader via une injection SQL,
    et ton compte normal (celui avec lequel tu te log) devient admin tout seul.

securite :
  - tout passe par le decorateur admin_required, qui rejoue login_required (JWT)
    puis verifie l'email en base contre ADMIN_EMAILS.
  - le front ne fait QUE cacher/montrer des boutons : la vraie barriere est ici,
    serveur-side, sur chaque endpoint. On ne fait jamais confiance au front.

regle du projet : ON NE SUPPRIME RIEN en dur (ni fighter ni user). L'admin edite,
corrige, change le tier. Les signalements sont marques "resolved", pas effaces.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps

import jwt as pyjwt
import psycopg2
from flask import Blueprint, jsonify, request

from auth import login_required, JWT_SECRET, JWT_ALGO

# 2FA (TOTP + QR). Import tolerant : si les libs manquent, l'app demarre quand
# meme et les endpoints 2FA renvoient 503 (mais alors l'admin est inaccessible).
try:
    import pyotp
    import qrcode
    import qrcode.image.svg
    _TWOFA_OK = True
except Exception:  # pragma: no cover
    _TWOFA_OK = False

# Duree de vie du jeton admin (court expres : re-2FA passe ce delai).
ADMIN_TOKEN_MINUTES = 60


# ---- Liste des admins (.env) -----------------------------------------------

def _admin_emails() -> set[str]:
    """Parse ADMIN_EMAILS du .env -> set d'emails normalises (lower)."""
    raw = os.getenv("ADMIN_EMAILS", "") or ""
    out = set()
    for chunk in raw.replace(";", ",").split(","):
        e = chunk.strip().lower()
        if e:
            out.add(e)
    return out


def is_admin_email(email: str | None) -> bool:
    return bool(email) and email.strip().lower() in _admin_emails()


# ---- Lookup user admin + 2FA -----------------------------------------------

def _admin_user(user_id):
    """(email_lower, totp_secret, totp_enabled) ou (None, None, None). Self-heal
    des colonnes 2FA si la migration 023 n'a pas encore tourne."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT email, totp_secret, totp_enabled FROM users WHERE id = %s", (user_id,))
        except psycopg2.errors.UndefinedColumn:
            conn.rollback()
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE")
            conn.commit()
            cur.execute("SELECT email, totp_secret, totp_enabled FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return (None, None, None)
    return ((row[0] or "").strip().lower(), row[1], bool(row[2]))


# ---- Jeton admin (scope=admin, court) --------------------------------------

def _make_admin_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "scope": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ADMIN_TOKEN_MINUTES),
    }
    tok = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return tok.decode() if isinstance(tok, bytes) else tok


def _decode_bearer():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    try:
        return pyjwt.decode(h.split(" ", 1)[1].strip(), JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        return None


# ---- Decorateurs -----------------------------------------------------------

def admin_preauth_required(f):
    """
    Etape 1 : JWT de login normal (mot de passe valide) + email dans ADMIN_EMAILS.
    Sert UNIQUEMENT aux endpoints 2FA (status / setup / enable / login).
    Ne donne PAS acces aux donnees : il faut encore passer la 2FA.
    """
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        email, _secret, _enabled = _admin_user(request.user_id)
        if email is None:
            return jsonify({"error": "user_not_found"}), 401
        if not is_admin_email(email):
            return jsonify({"error": "forbidden", "detail": "admin only"}), 403
        request.admin_email = email
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """
    Etape 2 : exige le JETON ADMIN (scope=admin, emis apres 2FA reussie) + email
    toujours dans ADMIN_EMAILS + 2FA activee. C'est la barriere des endpoints data.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        payload = _decode_bearer()
        if not payload:
            return jsonify({"error": "missing_token"}), 401
        if payload.get("scope") != "admin":
            return jsonify({"error": "admin_session_required"}), 401
        try:
            uid = int(payload["sub"])
        except (KeyError, ValueError):
            return jsonify({"error": "invalid_token"}), 401
        email, _secret, enabled = _admin_user(uid)
        if email is None:
            return jsonify({"error": "user_not_found"}), 401
        if not is_admin_email(email):
            return jsonify({"error": "forbidden"}), 403
        if not enabled:
            return jsonify({"error": "twofa_required"}), 403
        request.user_id = uid
        request.admin_email = email
        return f(*args, **kwargs)
    return wrapper


# ---- QR code (SVG, pur Python) ---------------------------------------------

def _qr_svg(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


# ---- Serialisation JSON-safe -----------------------------------------------

def _ser(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _rows(cur):
    """Retourne les rows du curseur en liste de dicts (cols depuis description)."""
    cols = [c[0] for c in cur.description]
    return [{c: _ser(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


# ---- Blueprint -------------------------------------------------------------

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.get("/check")
@admin_required
def check():
    """Ping protege par le jeton admin : le front confirme que la session 2FA tient."""
    return jsonify({"ok": True, "is_admin": True, "email": request.admin_email}), 200


# ---- 2FA (TOTP) ------------------------------------------------------------

def _read_code() -> str:
    raw = (request.get_json(silent=True) or {}).get("code", "")
    return str(raw).strip().replace(" ", "")


@admin_bp.get("/2fa/status")
@admin_preauth_required
def twofa_status():
    """Le front interroge ca avec le JWT de login : suis-je admin ? 2FA activee ?"""
    _email, _secret, enabled = _admin_user(request.user_id)
    return jsonify({
        "is_admin": True,
        "email": request.admin_email,
        "totp_enabled": bool(enabled),
        "twofa_available": _TWOFA_OK,
    }), 200


@admin_bp.post("/2fa/setup")
@admin_preauth_required
def twofa_setup():
    """Enrolement : genere un secret + QR a scanner. Pas encore actif (enable suit)."""
    if not _TWOFA_OK:
        return jsonify({"error": "twofa_unavailable"}), 503
    _email, _secret, enabled = _admin_user(request.user_id)
    if enabled:
        return jsonify({"error": "already_enabled"}), 409
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=request.admin_email, issuer_name="MM.AI Admin")
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET totp_secret = %s, totp_enabled = FALSE WHERE id = %s",
                    (secret, request.user_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"secret": secret, "otpauth_uri": uri, "qr_svg": _qr_svg(uri)}), 200


@admin_bp.post("/2fa/enable")
@admin_preauth_required
def twofa_enable():
    """Confirme l'enrolement : verifie un 1er code, active la 2FA, donne le jeton admin."""
    if not _TWOFA_OK:
        return jsonify({"error": "twofa_unavailable"}), 503
    _email, secret, enabled = _admin_user(request.user_id)
    if enabled:
        return jsonify({"error": "already_enabled"}), 409
    if not secret:
        return jsonify({"error": "no_setup"}), 400
    if not pyotp.TOTP(secret).verify(_read_code(), valid_window=1):
        return jsonify({"error": "invalid_code"}), 400
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET totp_enabled = TRUE WHERE id = %s", (request.user_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "admin_token": _make_admin_token(request.user_id)}), 200


@admin_bp.post("/2fa/login")
@admin_preauth_required
def twofa_login():
    """Login 2FA : verifie le code courant -> emet un jeton admin (60 min)."""
    if not _TWOFA_OK:
        return jsonify({"error": "twofa_unavailable"}), 503
    _email, secret, enabled = _admin_user(request.user_id)
    if not enabled or not secret:
        return jsonify({"error": "twofa_not_setup"}), 400
    if not pyotp.TOTP(secret).verify(_read_code(), valid_window=1):
        return jsonify({"error": "invalid_code"}), 400
    return jsonify({"ok": True, "admin_token": _make_admin_token(request.user_id)}), 200


# ---- Dashboard : stats cachees ---------------------------------------------

@admin_bp.get("/stats")
@admin_required
def stats():
    """
    Toutes les stats qu'on ne veut PAS dans le front public :
    sante des donnees fighters, comptes users / VIP, signalements, etc.
    Chaque bloc est isole : si une table manque, on renvoie quand meme le reste.
    """
    from app import get_conn
    conn = get_conn()
    out: dict = {}
    try:
        cur = conn.cursor()

        # --- Fighters -------------------------------------------------------
        try:
            cur.execute("""
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE photo_url IS NOT NULL
                                        OR photo_thumbnail_url IS NOT NULL) AS with_photo,
                    COUNT(*) FILTER (WHERE base_elo IS NOT NULL)          AS with_elo,
                    COUNT(*) FILTER (WHERE is_verified)                   AS verified,
                    COUNT(*) FILTER (WHERE is_active)                     AS active,
                    COUNT(*) FILTER (WHERE date_of_birth IS NULL)         AS missing_dob,
                    COUNT(*) FILTER (WHERE gender = 'F')                  AS women,
                    COUNT(*) FILTER (WHERE current_league IS NOT NULL)    AS with_league,
                    ROUND(AVG(data_quality_score)::numeric, 1)           AS avg_quality
                FROM fighters
            """)
            cols = [c[0] for c in cur.description]
            out["fighters"] = {c: _ser(v) for c, v in zip(cols, cur.fetchone())}
        except Exception as e:
            conn.rollback()
            out["fighters"] = {"error": str(e)}

        # Repartition de la completude (data_quality_score) par tranche
        try:
            cur.execute("""
                SELECT width_bucket(COALESCE(data_quality_score, 0), 0, 100, 5) AS bucket,
                       COUNT(*) AS n
                FROM fighters
                GROUP BY bucket ORDER BY bucket
            """)
            out["quality_buckets"] = _rows(cur)
        except Exception:
            conn.rollback()
            out["quality_buckets"] = []

        # Top base_elo (utile pour reperer les aberrations)
        try:
            cur.execute("""
                SELECT id, name, weight_class_current, gender,
                       base_elo, scouter_rating, fightmatrix_rating_points
                FROM fighters
                WHERE base_elo IS NOT NULL
                ORDER BY base_elo DESC
                LIMIT 10
            """)
            out["top_elo"] = _rows(cur)
        except Exception:
            conn.rollback()
            out["top_elo"] = []

        # --- Users ----------------------------------------------------------
        try:
            cur.execute("""
                SELECT
                    COUNT(*)                                            AS total,
                    COUNT(*) FILTER (WHERE tier = 'premium')            AS premium,
                    COUNT(*) FILTER (WHERE tier = 'free')               AS free,
                    COUNT(*) FILTER (WHERE email_verified)              AS verified,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')  AS new_7d,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS new_30d,
                    COUNT(*) FILTER (WHERE last_login_at > NOW() - INTERVAL '7 days') AS active_7d
                FROM users
            """)
            cols = [c[0] for c in cur.description]
            out["users"] = {c: _ser(v) for c, v in zip(cols, cur.fetchone())}
        except Exception as e:
            conn.rollback()
            out["users"] = {"error": str(e)}

        # Derniers inscrits
        try:
            cur.execute("""
                SELECT id, pseudo, first_name, last_name, email, tier,
                       email_verified, created_at, last_login_at
                FROM users
                ORDER BY created_at DESC
                LIMIT 8
            """)
            out["recent_users"] = _rows(cur)
        except Exception:
            conn.rollback()
            out["recent_users"] = []

        # --- Reports --------------------------------------------------------
        try:
            _ensure_reports(cur)
            cur.execute("""
                SELECT
                    COUNT(*)                                        AS total,
                    COUNT(*) FILTER (WHERE status = 'open')         AS open,
                    COUNT(*) FILTER (WHERE status = 'resolved')     AS resolved
                FROM reports
            """)
            cols = [c[0] for c in cur.description]
            out["reports"] = {c: _ser(v) for c, v in zip(cols, cur.fetchone())}
        except Exception as e:
            conn.rollback()
            out["reports"] = {"error": str(e)}

        conn.commit()
    finally:
        conn.close()

    return jsonify(out), 200


# ---- Users : liste + VIP ----------------------------------------------------

@admin_bp.get("/users")
@admin_required
def list_users():
    """Liste paginee des comptes (+ nb de favoris). Filtres : search, tier."""
    search = (request.args.get("search") or "").strip()
    tier = (request.args.get("tier") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 25
    offset = (page - 1) * per_page

    where, params = [], []
    if search:
        where.append("(LOWER(u.email) LIKE %s OR LOWER(u.pseudo) LIKE %s "
                     "OR LOWER(u.first_name) LIKE %s OR LOWER(u.last_name) LIKE %s)")
        like = f"%{search.lower()}%"
        params += [like, like, like, like]
    if tier in ("free", "premium"):
        where.append("u.tier = %s")
        params.append(tier)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM users u {where_sql}", params)
        total = cur.fetchone()[0]
        cur.execute(f"""
            SELECT u.id, u.pseudo, u.first_name, u.last_name, u.email, u.age,
                   u.tier, u.premium_until, u.email_verified,
                   u.created_at, u.last_login_at,
                   COALESCE(fav.n, 0) AS favorites
            FROM users u
            LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM user_favorites GROUP BY user_id) fav
                   ON fav.user_id = u.id
            {where_sql}
            ORDER BY u.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])
        users = _rows(cur)
    finally:
        conn.close()

    # marque les admins (lecture seule, depuis .env)
    admins = _admin_emails()
    for u in users:
        u["is_admin"] = (u.get("email") or "").lower() in admins

    return jsonify({
        "users": users,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
    }), 200


@admin_bp.patch("/users/<int:user_id>/tier")
@admin_required
def set_user_tier(user_id):
    """
    Passe un user en free <-> premium (offrir / retirer le VIP).
    Body : { "tier": "free"|"premium", "premium_until": "YYYY-MM-DD"? }
    premium_until absent ou null => VIP a vie (NULL en base).
    """
    data = request.get_json(silent=True) or {}
    tier = str(data.get("tier", "")).strip().lower()
    if tier not in ("free", "premium"):
        return jsonify({"error": "invalid_tier"}), 400

    premium_until = None
    if tier == "premium":
        raw = data.get("premium_until")
        if raw:
            try:
                premium_until = date.fromisoformat(str(raw)[:10])
            except ValueError:
                return jsonify({"error": "invalid_date", "detail": "YYYY-MM-DD"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET tier = %s, premium_until = %s WHERE id = %s RETURNING id",
            (tier, premium_until, user_id),
        )
        if not cur.fetchone():
            conn.rollback()
            return jsonify({"error": "user_not_found"}), 404
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "tier": tier,
                    "premium_until": premium_until.isoformat() if premium_until else None}), 200


# ---- Fighters : recherche + edition ----------------------------------------

# Colonnes editables (whitelist) + leur type pour la coercion.
# On EXCLUT volontairement : id, *_id sources, age (recalcule a la lecture),
# weight_class_gendered (colonne GENERATED), total_fights / recent_form_score
# (derives), created_at / updated_at.
_FIGHTER_FIELDS = {
    # texte libre
    "name": "str", "nickname": "str", "nationality": "str",
    "photo_url": "str", "photo_thumbnail_url": "str",
    "weight_class_current": "str", "weight_class_origin": "str",
    "height_inches": "str", "reach_inches": "str", "stance": "str",
    "first_sport": "str", "current_league": "str", "current_streak": "str",
    "last_5_results": "str", "fightmatrix_big_league_record": "str",
    "data_source": "str", "notes": "str",
    # genre (valide M/F)
    "gender": "gender",
    # dates ISO
    "date_of_birth": "date", "career_debut_date": "date", "last_fight_date": "date",
    # entiers
    "record_total_wins": "int", "record_total_losses": "int",
    "record_total_draws": "int", "record_total_nc": "int",
    "record_ufc_wins": "int", "record_ufc_losses": "int", "record_ufc_draws": "int",
    "wins_by_ko_tko": "int", "wins_by_submission": "int", "wins_by_decision": "int",
    "losses_by_ko_tko": "int", "losses_by_submission": "int", "losses_by_decision": "int",
    "ufc_title_match_win": "int", "ufc_official_rank": "int", "ufc_p4p_rank": "int",
    "data_quality_score": "int",
    # booleens
    "is_active": "bool", "is_ufc_champion": "bool", "is_verified": "bool",
    # decimaux
    "base_elo": "float", "scouter_rating": "float", "fightmatrix_rating_points": "float",
}

# Colonnes NOT NULL : on refuse de les vider.
_FIGHTER_NOT_NULL = {"name", "weight_class_current"}


def _coerce(kind: str, value):
    """(ok, valeur) ; "" -> NULL pour les colonnes nullable."""
    if value is None:
        return True, None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return True, None
    if kind == "str":
        return True, str(value)
    if kind == "gender":
        v = str(value).upper()
        return (v in ("M", "F")), (v if v in ("M", "F") else None)
    if kind == "int":
        try:
            return True, int(value)
        except (ValueError, TypeError):
            return False, None
    if kind == "float":
        try:
            return True, float(value)
        except (ValueError, TypeError):
            return False, None
    if kind == "bool":
        if isinstance(value, bool):
            return True, value
        return True, str(value).strip().lower() in ("1", "true", "yes", "on", "t")
    if kind == "date":
        try:
            return True, date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return False, None
    return False, None


@admin_bp.get("/fighters")
@admin_required
def admin_search_fighters():
    """Recherche fighters cote admin (renvoie les champs caches en plus)."""
    search = (request.args.get("search") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 25
    offset = (page - 1) * per_page

    where, params = [], []
    if search:
        if search.isdigit():
            where.append("(id = %s OR name ILIKE %s)")
            params += [int(search), f"%{search}%"]
        else:
            where.append("name ILIKE %s")
            params.append(f"%{search}%")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM fighters {where_sql}", params)
        total = cur.fetchone()[0]
        cur.execute(f"""
            SELECT id, name, nickname, gender, weight_class_current, nationality,
                   record_total_wins, record_total_losses, record_total_draws,
                   base_elo, scouter_rating, fightmatrix_rating_points,
                   data_quality_score, is_verified, is_active, current_league,
                   photo_thumbnail_url, updated_at
            FROM fighters
            {where_sql}
            ORDER BY (base_elo IS NULL), base_elo DESC, name ASC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])
        fighters = _rows(cur)
    finally:
        conn.close()

    return jsonify({
        "fighters": fighters,
        "page": page, "per_page": per_page, "total": total,
        "pages": (total + per_page - 1) // per_page,
    }), 200


@admin_bp.get("/fighters/<int:fighter_id>")
@admin_required
def admin_get_fighter(fighter_id):
    """Row complete (tous les champs) pour le formulaire d'edition."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM fighters WHERE id = %s", (fighter_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        cols = [c[0] for c in cur.description]
        fighter = {c: _ser(v) for c, v in zip(cols, row)}
    finally:
        conn.close()

    return jsonify({
        "fighter": fighter,
        "editable": sorted(_FIGHTER_FIELDS.keys()),
    }), 200


@admin_bp.patch("/fighters/<int:fighter_id>")
@admin_required
def admin_update_fighter(fighter_id):
    """
    Edite les champs fournis (parmi la whitelist). Champ par champ, pas de scrape.
    Ne touche QUE les colonnes envoyees dans le body.
    """
    data = request.get_json(silent=True) or {}
    sets, params, changed = [], [], {}

    for key, raw in data.items():
        if key not in _FIGHTER_FIELDS:
            continue  # on ignore silencieusement tout champ hors whitelist
        ok, coerced = _coerce(_FIGHTER_FIELDS[key], raw)
        if not ok:
            return jsonify({"error": "invalid_value", "field": key}), 400
        if key in _FIGHTER_NOT_NULL and coerced is None:
            return jsonify({"error": "cannot_be_empty", "field": key}), 400
        sets.append(f"{key} = %s")
        params.append(coerced)
        changed[key] = coerced

    if not sets:
        return jsonify({"error": "nothing_to_update"}), 400

    params.append(fighter_id)
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE fighters SET {', '.join(sets)}, updated_at = NOW() "
            f"WHERE id = %s RETURNING id",
            params,
        )
        if not cur.fetchone():
            conn.rollback()
            return jsonify({"error": "not_found"}), 404
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "duplicate", "detail": "name + date_of_birth deja pris"}), 409
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "server_error", "detail": str(e)}), 500
    finally:
        conn.close()

    # serialise les dates pour le retour JSON
    return jsonify({"ok": True, "updated": {k: _ser(v) for k, v in changed.items()}}), 200


# ---- Fight history : lecture + ajout manuel --------------------------------

def _parse_fh(raw) -> dict:
    """fight_history column -> dict Python (gere jsonb/dict ET text/str)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


@admin_bp.get("/fighters/<int:fighter_id>/history")
@admin_required
def admin_get_fight_history(fighter_id):
    """Retourne les combats du fighter (tableau chronologique)."""
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, fight_history FROM fighters WHERE id = %s", (fighter_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        name, fh_raw = row
    finally:
        conn.close()
    fh = _parse_fh(fh_raw)
    fights = fh.get("fights", [])
    return jsonify({"name": name, "fights": fights, "count": len(fights)}), 200


@admin_bp.post("/fighters/<int:fighter_id>/history/add")
@admin_required
def admin_add_fight(fighter_id):
    """
    Insere un combat dans fight_history en position chronologique.
    Body : { result, opponent, event, event_date, method, round, opponent_record }
    Respecte le format du scraper Tapology :
      - 'date'  : "Method Round N"  (champ bizarre hérité du scraper)
      - 'method': ""                (vide, c'est dans 'date')
      - 'event_date' : "YYYY-MM-DD" (vrai champ date, utilisé pour le tri)
    """
    data = request.get_json(silent=True) or {}
    result = str(data.get("result", "")).strip().upper()
    if result not in ("W", "L", "D", "NC"):
        return jsonify({"error": "invalid_result", "detail": "W/L/D/NC"}), 400
    opponent = str(data.get("opponent", "")).strip()
    if not opponent:
        return jsonify({"error": "opponent_required"}), 400
    event = str(data.get("event", "")).strip()
    raw_date = data.get("event_date")
    event_date = str(raw_date).strip()[:10] if raw_date else ""
    method_str = str(data.get("method", "")).strip()
    round_num = data.get("round")
    opponent_record = str(data.get("opponent_record", "")).strip()

    # Reconstitue le champ 'date' a la maniere du scraper (method + round)
    if method_str and round_num:
        date_field = f"{method_str} Round {round_num}"
    elif method_str:
        date_field = method_str
    else:
        date_field = ""

    new_fight: dict = {"result": result, "opponent": opponent,
                       "event": event, "date": date_field, "method": ""}
    if event_date:
        new_fight["event_date"] = event_date
    if opponent_record:
        new_fight["opponent_record"] = opponent_record

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT fight_history FROM fighters WHERE id = %s", (fighter_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        fh = _parse_fh(row[0])
        if not isinstance(fh, dict):
            fh = {}
        fights = fh.get("fights", [])
        fights.append(new_fight)

        # Tri chronologique sur event_date (combats sans date restent a leur place)
        def _sort_key(f):
            d = f.get("event_date", "")
            return d if (d and len(d) == 10 and d[0].isdigit()) else "0000-00-00"
        fights.sort(key=_sort_key)

        fh["fights"] = fights
        fh["count"] = len(fights)
        cur.execute(
            "UPDATE fighters SET fight_history = %s::jsonb, updated_at = NOW() WHERE id = %s",
            (json.dumps(fh, ensure_ascii=False), fighter_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "server_error", "detail": str(e)}), 500
    finally:
        conn.close()

    return jsonify({"ok": True, "count": len(fights)}), 200


# ---- Reports : voir + resoudre ---------------------------------------------

def _ensure_reports(cur):
    """Cree la table reports si absente + ajoute la colonne status (idempotent)."""
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
    cur.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open'")
    cur.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")


@admin_bp.get("/reports")
@admin_required
def list_reports():
    """Signalements (+ nom du fighter vise). Filtre status=open|resolved|all."""
    status = (request.args.get("status") or "open").strip().lower()
    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        _ensure_reports(cur)
        where, params = "", []
        if status in ("open", "resolved"):
            where = "WHERE r.status = %s"
            params.append(status)
        cur.execute(f"""
            SELECT r.id, r.fighter_id, f.name AS fighter_name, r.event_id,
                   r.report_type, r.message, r.status, r.created_at, r.resolved_at
            FROM reports r
            LEFT JOIN fighters f ON f.id = r.fighter_id
            {where}
            ORDER BY (r.status = 'open') DESC, r.created_at DESC
            LIMIT 200
        """, params)
        reports = _rows(cur)
        conn.commit()
    finally:
        conn.close()
    return jsonify({"reports": reports}), 200


@admin_bp.patch("/reports/<int:report_id>")
@admin_required
def update_report(report_id):
    """Marque un signalement resolved / open. Pas de suppression en dur."""
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip().lower()
    if status not in ("open", "resolved"):
        return jsonify({"error": "invalid_status"}), 400

    from app import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        _ensure_reports(cur)
        resolved_at = "NOW()" if status == "resolved" else "NULL"
        cur.execute(
            f"UPDATE reports SET status = %s, resolved_at = {resolved_at} "
            f"WHERE id = %s RETURNING id",
            (status, report_id),
        )
        if not cur.fetchone():
            conn.rollback()
            return jsonify({"error": "not_found"}), 404
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "status": status}), 200
