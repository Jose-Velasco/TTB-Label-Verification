from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.constants import AUTH_COOKIE_NAME
from app.models import ApplicationData, ExtractedApplicationData, VerificationResult
from app.services.verification import VerificationService

router = APIRouter(prefix="/api", tags=["verify"])
limiter = Limiter(key_func=get_remote_address)


def _require_auth(
    ttb_auth: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME)
) -> None:
    if ttb_auth != settings.APP_ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Authentication required")


def _get_service() -> VerificationService:
    """Dependency injection for the verification service.

    Imported here to avoid circular imports — main.py sets app.state.service
    during lifespan startup.
    """
    from app.main import get_verification_service

    return get_verification_service()


@router.post("/verify", response_model=VerificationResult)
@limiter.limit("5/minute")
async def verify_label(
    request: Request,  # required by slowapi for rate limiting
    image: UploadFile = File(
        ..., description="Label image (JPEG, PNG, or WebP, max 10 MB)"
    ),
    application_data: str = Form(..., description="JSON-encoded ApplicationData"),
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> VerificationResult:
    """Verify a single label image against application data."""
    try:
        app_data = ApplicationData.model_validate_json(application_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid application_data: {exc}")

    return await service.verify_single(image, app_data)


@router.post("/extract", response_model=ExtractedApplicationData)
@limiter.limit("10/minute")
async def extract_label_fields(
    request: Request,  # required by slowapi for rate limiting
    image: UploadFile = File(
        ..., description="Label image (JPEG, PNG, or WebP, max 10 MB)"
    ),
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> ExtractedApplicationData:
    """Read the 7 application-data fields off a label photo.

    A data-entry accelerator for the Application Data form — there's no
    application data to compare against yet, so this is extraction only.
    """
    return await service.extract_fields(image)
