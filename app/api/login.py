"""Login/logout endpoints for the admin dashboard session gate (see app/auth.py).

``GET /login`` serves the standalone login page (app/templates/login.html —
deliberately outside app/static/ so the auth middleware, not the StaticFiles
mount, decides who can reach it). ``POST /login`` checks email+password
against ``app/accounts.py`` and sets the session cookie; ``POST /logout``
clears it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app import accounts, auth
from app.models.schemas import ChangePasswordRequest

router = APIRouter(tags=["auth"])

_LOGIN_HTML = (Path(__file__).parent.parent / "templates" / "login.html").read_text(
    encoding="utf-8"
)


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    return _LOGIN_HTML


@router.post("/login")
async def login_submit(
    response: Response, email: str = Form(...), password: str = Form(...)
) -> dict[str, bool | str]:
    if not accounts.is_valid_domain(email):
        raise HTTPException(
            status_code=401,
            detail=f"Email phải thuộc miền {accounts.EMAIL_DOMAIN}.",
        )
    account = accounts.authenticate(email, password)
    if account is None:
        raise HTTPException(
            status_code=401, detail="Sai email hoặc mật khẩu. Vui lòng thử lại."
        )
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.create_session_token(account),
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    # role is returned so the login page can send an employee to /chat even
    # if it was about to honor a "?next=/admin/..." it can no longer reach.
    return {"ok": True, "role": account.role}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
async def me(request: Request) -> dict[str, str | None]:
    """The signed-in account, for the admin console to render real identity
    (never a fabricated name/department) and to hide admin-only controls for
    an employee-role account client-side. Not the enforcement point — that's
    ``auth.require_admin`` on the mutating endpoints themselves.
    """
    account = auth.current_account(request)
    if account is None:
        return {"email": None, "role": None}
    return {"email": account.email, "role": account.role}


@router.post("/change-password")
async def change_password(
    request: Request, body: ChangePasswordRequest
) -> dict[str, bool]:
    """Self-service password change (P2-J6, audit/REPORT.md) — the minimum
    viable account-lifecycle surface: any signed-in account (not admin-only)
    changes its OWN password, verified against its current one. Reachable by
    any account because admin_session_gate already requires a session for
    every non-public path; the target is always the caller's own session
    account, never a client-supplied email, so one account can never change
    another's password this way.
    """
    account = auth.current_account(request)
    if account is None:
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập.")
    try:
        accounts.update_password(
            account.email, body.current_password, body.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@router.get("/accounts", dependencies=[Depends(auth.require_admin)])
async def list_accounts() -> list[dict[str, str]]:
    """Emails + roles only — admin-only, never returns a password hash.

    Read-only: there is still no self-service signup or in-app account
    creation, only scripts/seed_accounts.py run by hand on the server.
    """
    return [{"email": a.email, "role": a.role} for a in accounts.list_accounts()]
