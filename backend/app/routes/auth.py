from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.config import Settings, settings
from app.constants import AUTH_COOKIE_MAX_AGE, AUTH_COOKIE_NAME

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    """Validate password and set auth cookie.

    Intentionally uses constant-time-equivalent string comparison to avoid
    timing oracle on the access key.
    """
    # secrets.compare_digest works on str in Python 3.9+
    import hmac
    if not hmac.compare_digest(body.password, settings.APP_ACCESS_KEY):
        raise HTTPException(status_code=401, detail="Invalid password")

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=settings.APP_ACCESS_KEY,
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        # secure=True in prod via COOKIE_SECURE — nginx terminates TLS so the
        # backend itself sees plain HTTP either way; same-origin deployment
        # (single nginx serving both frontend and /api) means SameSite=Lax is
        # sufficient, no cross-site cookie handling needed.
        secure=settings.COOKIE_SECURE,
    )
    return {"status": "ok"}


@router.get("/logout")
async def logout(response: Response) -> dict:
    # Match the same attributes used to set the cookie — some browsers only
    # honor a delete_cookie() whose Secure/SameSite match the original.
    response.delete_cookie(
        key=AUTH_COOKIE_NAME, samesite="lax", secure=settings.COOKIE_SECURE
    )
    return {"status": "ok"}
