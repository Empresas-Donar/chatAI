"""
controllers/google_auth_controller.py
--------------------------------------
Google OAuth2 login — restricts access to @empresasdonar.cl accounts.

Routes:
  GET /auth/google    → redirect to Google consent screen
  GET /auth/callback  → handle Google callback, verify domain, set session
"""

import logging
import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.config import Config

from auth import set_session

logger = logging.getLogger("google_auth")
router = APIRouter(prefix="/auth", tags=["auth"])

ALLOWED_DOMAIN = "empresasdonar.cl"

# Fixed redirect URI — must match exactly what's registered in Google Cloud Console
_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/callback",
)

_config = Config()
_oauth = OAuth(_config)
_oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "hd": ALLOWED_DOMAIN,
    },
)


@router.get("/google")
async def google_login(request: Request):
    return await _oauth.google.authorize_redirect(request, _REDIRECT_URI)


@router.get("/callback", name="google_callback")
async def google_callback(request: Request):
    try:
        token = await _oauth.google.authorize_access_token(request, redirect_uri=_REDIRECT_URI)
    except Exception as e:
        logger.warning("OAuth token error: %s", e)
        return RedirectResponse(url="/login?error=oauth", status_code=302)

    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email", "")

    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        logger.warning("Rejected login from unauthorized domain: %s", email)
        return RedirectResponse(url="/login?error=domain", status_code=302)

    logger.info("Google login success: %s", email)
    response = RedirectResponse(url="/chat", status_code=302)
    set_session(response, email)
    return response
