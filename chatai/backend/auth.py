"""
auth.py — Cookie-based session auth (replaces HTTP Basic).

Flow:
  1. Any protected request without a valid session cookie → redirect to /login
  2. POST /login validates credentials → sets signed cookie → redirect to /
  3. GET  /logout clears the cookie → redirect to /login

Cookie is signed with ITSDANGEROUS using SECRET_KEY from .env.

Roles (stored in public.user_roles):
  admin — full access including Remuneraciones/Ventas and Utilidades
  user  — read access; blocked from sensitive modules
"""

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SESSION_COOKIE = "donar_session"
_GTOKEN_COOKIE = "donar_gtoken"
_MAX_AGE = 60 * 60 * 8  # 8 hours


def _signer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY env var is required and not set")
    return URLSafeTimedSerializer(secret)


def set_session(response: RedirectResponse, username: str) -> None:
    token = _signer().dumps(username)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("HTTPS_ONLY", "false").lower() == "true",
    )


def clear_session(response: RedirectResponse) -> None:
    response.delete_cookie(_SESSION_COOKIE)
    response.delete_cookie(_GTOKEN_COOKIE)


def set_google_token(response: RedirectResponse, access_token: str) -> None:
    signed = _signer().dumps(access_token)
    response.set_cookie(
        key=_GTOKEN_COOKIE,
        value=signed,
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("HTTPS_ONLY", "false").lower() == "true",
    )


def get_google_token(request: Request) -> Optional[str]:
    signed = request.cookies.get(_GTOKEN_COOKIE)
    if not signed:
        return None
    try:
        return _signer().loads(signed, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> Optional[str]:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        return _signer().loads(token, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def require_auth(request: Request):
    """FastAPI dependency — redirects to /login if not authenticated."""
    user = get_current_user(request)
    if not user:
        raise _LoginRedirect(request.url.path)
    return user


def check_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("AUTH_USER", "")
    expected_pass = os.environ.get("AUTH_PASSWORD", "")
    user_ok = secrets.compare_digest(username.encode(), expected_user.encode())
    pass_ok = secrets.compare_digest(password.encode(), expected_pass.encode())
    return user_ok and pass_ok


def get_user_role(email: str) -> str:
    """Return 'admin' or 'user' for a given email.

    Bootstrap rule: if the user_roles table is empty, everyone is admin
    so the first administrator can seed the table without being locked out.
    Once at least one row exists, only explicitly assigned roles apply.
    """
    if not email:
        return "user"
    try:
        from db import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.user_roles")
                total = cur.fetchone()[0]
                if total == 0:
                    return "admin"
                cur.execute(
                    "SELECT role FROM public.user_roles WHERE email = %s",
                    (email.strip().lower(),),
                )
                row = cur.fetchone()
                return row[0] if row else "user"
        finally:
            conn.close()
    except Exception:
        return "user"


def require_admin(request: Request):
    """FastAPI dependency — raises 403 if user is not an admin."""
    user = get_current_user(request)
    if not user:
        raise _LoginRedirect(request.url.path)
    role = get_user_role(user)
    if role != "admin":
        raise HTTPException(
            status_code=403, detail="Acceso restringido a administradores"
        )
    return user


class _LoginRedirect(Exception):
    def __init__(self, next_path: str):
        self.next_path = next_path
