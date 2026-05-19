"""
controllers/login_controller.py
Routes:
  GET  /login        → render login page
  POST /login        → validate credentials, set cookie, redirect
  GET  /logout       → clear cookie, redirect to /login
"""

import time
from collections import defaultdict

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import check_credentials, clear_session, get_current_user, set_session

router = APIRouter()
_templates: Jinja2Templates = None

# Simple in-memory rate limiter: max 10 attempts per IP per 15 minutes
_login_attempts: dict = defaultdict(list)
_RATE_WINDOW = 900   # 15 minutes in seconds
_RATE_LIMIT   = 10


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= _RATE_LIMIT:
        return True
    _login_attempts[ip].append(now)
    return False


def _safe_next(next_url: str) -> str:
    """Only allow relative paths to prevent open redirect."""
    if not next_url or not next_url.startswith("/") or "//" in next_url:
        return "/"
    return next_url


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return _templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
):
    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        return RedirectResponse(url="/login?error=rate_limited", status_code=302)

    if check_credentials(username, password):
        response = RedirectResponse(url=_safe_next(next), status_code=302)
        set_session(response, username)
        return response
    return RedirectResponse(url="/login?error=1", status_code=302)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    clear_session(response)
    return response
