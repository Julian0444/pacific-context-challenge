"""
auth.py — Demo-grade session auth for QueryTrace product mode (Fase P).

Design:
- Users live per workspace in corpora/<slug>/users.json (username, name, role,
  is_admin, password_sha256, password_hint). Demo passwords are deliberately
  public. Loading is the workspace resolver's job (src.workspaces); this
  module only verifies credentials and mints/validates session tokens.
- Sessions are stateless signed cookies: base64url(JSON payload) + "." +
  base64url(HMAC-SHA256(secret, payload)). No session store — survives
  restarts, correct for a single-instance demo.
- SECRET_KEY comes from the QUERYTRACE_SECRET_KEY env var; a dev default is
  used with a loud warning when unset.
- Login attempts are rate-limited in-process per client IP.

Known limitation (declared in README): no registration, no password reset,
no OIDC. The upgrade path is OIDC/Okta with IdP groups mapped to roles.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Optional

_logger = logging.getLogger(__name__)

SESSION_COOKIE = "qt_session"
SESSION_TTL_SECONDS = 12 * 3600  # demo sessions last 12h

_DEV_SECRET = "querytrace-dev-secret-do-not-use-in-prod"

# Login rate limit: max attempts per IP within the window.
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60.0

_rate_lock = threading.Lock()
_login_attempts: dict = {}  # ip -> deque[timestamps]


def get_secret_key() -> str:
    """Return the signing secret; warn loudly when falling back to the dev default."""
    secret = os.getenv("QUERYTRACE_SECRET_KEY", "").strip()
    if secret:
        return secret
    _logger.warning(
        "QUERYTRACE_SECRET_KEY is not set — using the INSECURE dev default. "
        "Set it in any deployed environment."
    )
    return _DEV_SECRET


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users(path: str) -> dict:
    """Load a workspace's users.json, keyed by username."""
    with open(path, "r") as f:
        data = json.load(f)
    return {u["username"]: u for u in data["users"]}


def verify_credentials(users: dict, username: str, password: str) -> Optional[dict]:
    """Return the user dict when username/password match, else None."""
    user = users.get(username)
    if user is None:
        return None
    expected = user.get("password_sha256", "")
    if hmac.compare_digest(hash_password(password), expected):
        return user
    return None


# ---------------------------------------------------------------------------
# Signed session tokens
# ---------------------------------------------------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_bytes: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return _b64e(mac)


def create_session_token(
    user: dict,
    secret: str,
    now: Optional[float] = None,
    workspace: Optional[str] = None,
) -> str:
    """Build a signed session token for a verified user.

    `workspace` binds the session to the workspace it was created in
    (Fase 2): using the cookie against another workspace is rejected
    upstream. None is treated as the default workspace by the API layer.
    """
    payload = {
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "is_admin": bool(user.get("is_admin", False)),
        "workspace": workspace,
        "exp": int((now if now is not None else time.time()) + SESSION_TTL_SECONDS),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{_b64e(payload_bytes)}.{_sign(payload_bytes, secret)}"


def verify_session_token(token: str, secret: str, now: Optional[float] = None) -> Optional[dict]:
    """Return the session payload for a valid, unexpired token; None otherwise.

    Tampering, malformed tokens, and expiry all return None (→ 401 upstream),
    never raise — a forged cookie must not be able to cause a 500.
    """
    if not token or "." not in token:
        return None
    try:
        payload_part, sig_part = token.split(".", 1)
        payload_bytes = _b64d(payload_part)
        if not hmac.compare_digest(_sign(payload_bytes, secret), sig_part):
            return None
        payload = json.loads(payload_bytes)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or (now if now is not None else time.time()) >= exp:
        return None
    return payload


# ---------------------------------------------------------------------------
# Login rate limiting (in-process, per IP)
# ---------------------------------------------------------------------------

def allow_login_attempt(ip: str, now: Optional[float] = None) -> bool:
    """Record a login attempt for `ip`; False when over the per-minute limit."""
    ts = now if now is not None else time.time()
    with _rate_lock:
        window = _login_attempts.setdefault(ip, deque())
        while window and ts - window[0] > LOGIN_RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= LOGIN_RATE_LIMIT:
            return False
        window.append(ts)
        return True


def reset_rate_limiter() -> None:
    """Test helper: clear all recorded login attempts."""
    with _rate_lock:
        _login_attempts.clear()
