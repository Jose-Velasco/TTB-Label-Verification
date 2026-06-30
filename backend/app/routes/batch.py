from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.constants import AUTH_COOKIE_NAME
from app.models import ApplicationData
from app.services.verification import VerificationService

router = APIRouter(prefix="/api", tags=["batch"])
limiter = Limiter(key_func=get_remote_address)


def _require_auth(ttb_auth: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME)) -> None:
    if ttb_auth != settings.APP_ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Authentication required")


def _get_service() -> VerificationService:
    from app.main import get_verification_service
    return get_verification_service()


@router.post("/verify-batch")
@limiter.limit("2/minute")
async def verify_batch(
    request: Request,  # required by slowapi
    images: list[UploadFile] = File(..., description="Label images (up to 20)"),
    application_data: str = Form(..., description="JSON-encoded ApplicationData"),
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> StreamingResponse:
    """Verify multiple label images, streaming NDJSON results as each completes.

    Returns one JSON object per line (NDJSON format). The frontend reads the
    stream incrementally so results appear as they arrive rather than waiting
    for the entire batch to finish.
    """
    if len(images) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 images per batch")

    try:
        app_data = ApplicationData.model_validate_json(application_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid application_data: {exc}")

    async def stream_results():
        async for result in service.verify_batch(images, app_data):
            yield result.model_dump_json() + "\n"

    return StreamingResponse(
        stream_results(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
