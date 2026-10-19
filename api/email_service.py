"""
MM.AI - Email service (Resend wrapper + fallback console)
Envoie les emails transactionnels (verification, reset password plus tard).
Si RESEND_API_KEY est absent du .env, le mail est juste imprime dans le terminal
Flask — le code marche pareil, utile pour le dev/tests sans cle API.
"""
from __future__ import annotations

import os
import sys
import requests

RESEND_API_URL = "https://api.resend.com/emails"


def _resend_configured() -> bool:
    """True si RESEND_API_KEY est defini et non vide."""
    return bool(os.getenv("RESEND_API_KEY", "").strip())


def _console_fallback(to: str, subject: str, html: str) -> dict:
    """
    Mode dev sans cle Resend : imprime le mail dans le terminal Flask.
    Permet de copier-coller le lien de verification a la main.
    """
    print("\n" + "=" * 70, file=sys.stderr)
    print(f"[EMAIL DEV] To: {to}", file=sys.stderr)
    print(f"[EMAIL DEV] Subject: {subject}", file=sys.stderr)
    print("[EMAIL DEV] HTML body:", file=sys.stderr)
    print(html, file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)
    return {"ok": True, "id": "console-fallback", "via": "console"}


def send_email(to: str, subject: str, html: str) -> dict:
    """
    Envoie un email via Resend (ou console fallback si pas configure).
    Retourne {ok: bool, id?: str, via: str, error?: str}.
    """
    if not _resend_configured():
        return _console_fallback(to, subject, html)

    api_key = os.environ["RESEND_API_KEY"]
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    from_name = os.getenv("RESEND_FROM_NAME", "MM.AI")
    sender = f"{from_name} <{from_email}>"

    try:
        resp = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            print(f"[EMAIL] Resend error {resp.status_code}: {resp.text}", file=sys.stderr)
            return {"ok": False, "via": "resend", "error": resp.text}
        data = resp.json()
        return {"ok": True, "via": "resend", "id": data.get("id")}
    except requests.RequestException as e:
        print(f"[EMAIL] Resend request failed: {e}", file=sys.stderr)
        return {"ok": False, "via": "resend", "error": str(e)}


# ---- Templates -------------------------------------------------------------

def render_reset_email(first_name: str, reset_url: str) -> tuple[str, str]:
    """Retourne (subject, html) pour l'email de réinitialisation de mot de passe."""
    subject = "Reset your MM.AI password"
    html = f"""\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             background:#0b0b0d; color:#e8e8ea; padding:32px; margin:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px; margin:0 auto;
         background:#15151a; border:1px solid #2a2a32; border-radius:12px; padding:32px;">
    <tr><td>
      <h1 style="margin:0 0 8px; font-family:'Oswald', sans-serif; letter-spacing:0.05em;
                 color:#fff; font-size:28px;">
        MM<span style="color:#d20a11;">.</span>AI
      </h1>
      <p style="color:#9aa0aa; font-size:13px; margin:0 0 24px;">MMA analytics &amp; fight prediction</p>
      <h2 style="color:#fff; font-size:20px; margin:0 0 16px;">Reset your password, {first_name}</h2>
      <p style="line-height:1.6; margin:0 0 24px;">
        You requested a password reset. Click the button below to set a new password.
        This link expires in <strong>2 hours</strong>.
      </p>
      <p style="text-align:center; margin:32px 0;">
        <a href="{reset_url}"
           style="display:inline-block; background:#d20a11; color:#fff; padding:14px 32px;
                  border-radius:8px; text-decoration:none; font-weight:600; letter-spacing:0.02em;">
          Reset my password
        </a>
      </p>
      <p style="color:#9aa0aa; font-size:12px; line-height:1.5; margin:24px 0 0;">
        Or copy this link :<br>
        <a href="{reset_url}" style="color:#d20a11; word-break:break-all;">{reset_url}</a>
      </p>
      <hr style="border:none; border-top:1px solid #2a2a32; margin:32px 0 16px;">
      <p style="color:#6b6f78; font-size:11px; margin:0;">
        If you didn't request this, you can safely ignore this email — your password won't change.
      </p>
    </td></tr>
  </table>
</body>
</html>
"""
    return subject, html


def render_verification_email(first_name: str, verify_url: str) -> tuple[str, str]:
    """Retourne (subject, html) pour l'email de verification d'inscription."""
    subject = "Verify your MM.AI account"
    html = f"""\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             background:#0b0b0d; color:#e8e8ea; padding:32px; margin:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px; margin:0 auto;
         background:#15151a; border:1px solid #2a2a32; border-radius:12px; padding:32px;">
    <tr><td>
      <h1 style="margin:0 0 8px; font-family:'Oswald', sans-serif; letter-spacing:0.05em;
                 color:#fff; font-size:28px;">
        MM<span style="color:#d20a11;">.</span>AI
      </h1>
      <p style="color:#9aa0aa; font-size:13px; margin:0 0 24px;">
        MMA analytics &amp; fight prediction
      </p>
      <h2 style="color:#fff; font-size:20px; margin:0 0 16px;">Welcome, {first_name} !</h2>
      <p style="line-height:1.6; margin:0 0 24px;">
        Thanks for signing up. To activate your account, please confirm your email
        address by clicking the button below. The link expires in 24 hours.
      </p>
      <p style="text-align:center; margin:32px 0;">
        <a href="{verify_url}"
           style="display:inline-block; background:#d20a11; color:#fff; padding:14px 32px;
                  border-radius:8px; text-decoration:none; font-weight:600;
                  letter-spacing:0.02em;">
          Verify my email
        </a>
      </p>
      <p style="color:#9aa0aa; font-size:12px; line-height:1.5; margin:24px 0 0;">
        Or copy this link into your browser :<br>
        <a href="{verify_url}" style="color:#d20a11; word-break:break-all;">{verify_url}</a>
      </p>
      <hr style="border:none; border-top:1px solid #2a2a32; margin:32px 0 16px;">
      <p style="color:#6b6f78; font-size:11px; margin:0;">
        If you didn't create an MM.AI account, you can safely ignore this email.
      </p>
    </td></tr>
  </table>
</body>
</html>
"""
    return subject, html
