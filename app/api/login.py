"""Login/logout endpoints for the admin dashboard session gate (see app/auth.py).

``GET /login`` serves the standalone login page (app/templates/login.html —
deliberately outside app/static/ so the auth middleware, not the StaticFiles
mount, decides who can reach it). ``POST /login`` checks the single shared
admin password and sets the session cookie; ``POST /logout`` clears it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Response
from fastapi.responses import HTMLResponse

from app import auth

router = APIRouter(tags=["auth"])

_LOGIN_HTML = (Path(__file__).parent.parent / "templates" / "login.html").read_text(
    encoding="utf-8"
)


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    return _LOGIN_HTML


@router.post("/login")
async def login_submit(
    response: Response, password: str = Form(...)
) -> dict[str, bool]:
    if not auth.check_password(password):
        raise HTTPException(status_code=401, detail="Sai mật khẩu. Vui lòng thử lại.")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.create_session_token(),
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}
