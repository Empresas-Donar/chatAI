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
import sys
from pathlib import Path

# Repo root → resolves `core` package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# backend/ → resolves sibling packages (controllers, services, models, auth, db)
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import _LoginRedirect, require_auth
import controllers.login_controller as login
import controllers.dashboard_controller as dashboard
import controllers.csv_migrator_controller as csv_migrator
import controllers.tarjas_controller as tarjas
import controllers.purchase_orders_controller as purchase_orders
import controllers.sensors_controller as sensors
import controllers.despacho_controller as despacho
import controllers.chat_controller as chat

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
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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

_auth = [Depends(require_auth)]

app.include_router(login.router)
app.include_router(dashboard.router,       dependencies=_auth)
app.include_router(csv_migrator.router,    dependencies=_auth)
app.include_router(tarjas.router,          dependencies=_auth)
app.include_router(purchase_orders.router, dependencies=_auth)
app.include_router(sensors.router,         dependencies=_auth)
app.include_router(despacho.router,        dependencies=_auth)
app.include_router(chat.router,            dependencies=_auth)


@app.get("/health")
async def health():
    return {"status": "ok"}
