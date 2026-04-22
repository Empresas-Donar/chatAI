"""
controllers/login_controller.py
Routes:
  GET  /login        → render login page
  POST /login        → validate credentials, set cookie, redirect
  GET  /logout       → clear cookie, redirect to /login
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import check_credentials, clear_session, get_current_user, set_session

router = APIRouter()
_templates: Jinja2Templates = None


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
    if check_credentials(username, password):
        response = RedirectResponse(url=next or "/", status_code=302)
        set_session(response, username)
        return response
    return RedirectResponse(url="/login?error=1", status_code=302)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    clear_session(response)
    return response
