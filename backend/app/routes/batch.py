import json

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.constants import AUTH_COOKIE_NAME, MAX_BATCH_IMAGES
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
    images: list[UploadFile] = File(
        ..., description=f"Label images (up to {MAX_BATCH_IMAGES})"
    ),
    application_data_map: str = Form(
        ...,
        description=(
            "JSON object mapping filename -> ApplicationData. Each image is "
            "verified against its own entry, matched by filename; an image "
            "with no matching entry is skipped (no vision-model call) rather "
            "than failing the whole batch."
        ),
    ),
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> StreamingResponse:
    """Verify multiple label images, each against its OWN application data.

    Returns one JSON object per line (NDJSON format). The frontend reads the
    stream incrementally so results appear as they arrive rather than waiting
    for the entire batch to finish.
    """
    if len(images) > MAX_BATCH_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BATCH_IMAGES} images per batch",
        )

    try:
        raw_map = json.loads(application_data_map)
        if not isinstance(raw_map, dict):
            raise ValueError("application_data_map must be a JSON object")
        app_data_map = {
            filename: ApplicationData.model_validate(payload)
            for filename, payload in raw_map.items()
        }
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid application_data_map: {exc}"
        )

    async def stream_results():
        async for result in service.verify_batch(images, app_data_map):
            yield result.model_dump_json() + "\n"

    return StreamingResponse(
        stream_results(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
