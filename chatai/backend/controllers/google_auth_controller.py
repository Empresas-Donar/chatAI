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
import secrets

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from auth import set_session, set_google_token

logger = logging.getLogger("google_auth")
router = APIRouter(prefix="/auth", tags=["auth"])

ALLOWED_DOMAIN = "empresasdonar.cl"

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/callback",
)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/google")
async def google_login(request: Request):
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets",
        "state": state,
        "hd": ALLOWED_DOMAIN,
        "access_type": "online",
    }
    url = _GOOGLE_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", name="google_callback")
async def google_callback(request: Request):
    # CSRF check
    state_in_session = request.session.pop("oauth_state", None)
    state_from_google = request.query_params.get("state")
    if not state_in_session or state_in_session != state_from_google:
        logger.warning("OAuth state mismatch — possible CSRF")
        return RedirectResponse(url="/login?error=oauth", status_code=302)

    code = request.query_params.get("code")
    if not code:
        logger.warning("No authorization code in callback")
        return RedirectResponse(url="/login?error=oauth", status_code=302)

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        try:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except Exception as e:
            logger.warning("Token exchange error: %s", e)
            return RedirectResponse(url="/login?error=oauth", status_code=302)

        access_token = token_data.get("access_token")
        if not access_token:
            logger.warning("No access_token in token response")
            return RedirectResponse(url="/login?error=oauth", status_code=302)

        # Get user info
        try:
            userinfo_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()
        except Exception as e:
            logger.warning("Userinfo fetch error: %s", e)
            return RedirectResponse(url="/login?error=oauth", status_code=302)

    email = userinfo.get("email", "")
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        logger.warning("Rejected login from unauthorized domain: %s", email)
        return RedirectResponse(url="/login?error=domain", status_code=302)

    logger.info("Google login success: %s", email)
    response = RedirectResponse(url="/chat", status_code=302)
    set_session(response, email)
    set_google_token(response, access_token)
    return response
