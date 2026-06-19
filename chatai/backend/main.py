"""
main.py
-------
Application entry point. Wires together controllers, middleware and static files.

Architecture (MVC):
  controllers/  ← HTTP layer (routes + request/response)
  services/     ← Business logic
  models/       ← Data shapes
  frontend/     ← Views (HTML templates + static assets)
"""

import logging
import os
import sys
from pathlib import Path

# Repo root → resolves `core` package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# backend/ → resolves sibling packages (controllers, services, models, auth, db)
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from auth import _LoginRedirect, require_auth
import controllers.login_controller as login
import controllers.google_auth_controller as google_auth
import controllers.dashboard_controller as dashboard
import controllers.csv_migrator_controller as csv_migrator
import controllers.tarjas_controller as tarjas
import controllers.purchase_orders_controller as purchase_orders
import controllers.sensors_controller as sensors
import controllers.despacho_controller as despacho
import controllers.chat_controller as chat
import controllers.looker_controller as looker
import controllers.roles_controller as roles
import controllers.reports_controller as reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BASE_DIR      = Path(__file__).parent.parent
UPLOAD_DIR    = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
STATIC_DIR    = BASE_DIR / "frontend" / "static"

app = FastAPI(
    title="Donar Integraciones",
    version="2.0.0",
    docs_url=None,    # disable Swagger UI in production
    redoc_url=None,   # disable ReDoc in production
)

_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8000"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# SessionMiddleware must be added last (runs first) so the OAuth state cookie
# is available before CORS processing. samesite="lax" is required — "strict"
# blocks the cookie on the cross-origin redirect back from Google.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", ""),
    https_only=os.environ.get("HTTPS_ONLY", "false").lower() == "true",
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

import time as _time
import hashlib as _hashlib

def _static_version():
    """Hash of all static files — changes whenever any JS/CSS file is modified."""
    h = _hashlib.md5()
    for f in sorted(STATIC_DIR.rglob("*")):
        if f.is_file() and f.suffix in (".js", ".css"):
            h.update(f.read_bytes())
    return h.hexdigest()[:10]

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["static_v"] = _static_version()

# Inject current_user and user_role into every template context automatically
from auth import get_current_user as _get_current_user, get_user_role as _get_user_role
_orig_response = templates.TemplateResponse

def _template_response_with_user(request, name=None, context=None, *args, **kwargs):
    # Support both positional and keyword calling conventions
    if name is None and isinstance(request, str):
        name, request = request, context
        context = args[0] if args else {}
    context = context or {}
    user = _get_current_user(request)
    context.setdefault("current_user", user)
    context.setdefault("user_role", _get_user_role(user) if user else "user")
    return _orig_response(request, name, context, **kwargs)

templates.TemplateResponse = _template_response_with_user


@app.exception_handler(_LoginRedirect)
async def login_redirect_handler(request: Request, exc: _LoginRedirect):
    next_path = exc.next_path or "/"
    return RedirectResponse(url=f"/login?next={next_path}", status_code=302)


# Inject shared dependencies into controllers
login.init(templates=templates)
dashboard.init(templates=templates)
csv_migrator.init(upload_dir=UPLOAD_DIR, templates=templates)
tarjas.init(templates=templates)
purchase_orders.init(templates=templates)
sensors.init(templates=templates)
despacho.init(templates=templates)
chat.init(templates=templates)
looker.init(templates=templates)
roles.init(templates=templates)
reports.init(templates=templates)

_auth = [Depends(require_auth)]

app.include_router(login.router)
app.include_router(google_auth.router)  # no auth required — it IS the auth
app.include_router(dashboard.router,       dependencies=_auth)
app.include_router(csv_migrator.router,    dependencies=_auth)
app.include_router(tarjas.router,          dependencies=_auth)
app.include_router(purchase_orders.router, dependencies=_auth)
app.include_router(sensors.router,         dependencies=_auth)
app.include_router(despacho.router,        dependencies=_auth)
app.include_router(chat.router,            dependencies=_auth)
app.include_router(looker.router,          dependencies=_auth)
app.include_router(roles.router,           dependencies=_auth)
app.include_router(reports.router,         dependencies=_auth)


@app.get("/", dependencies=_auth)
async def root_redirect():
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/health", dependencies=_auth)
async def health():
    return {"status": "ok"}
