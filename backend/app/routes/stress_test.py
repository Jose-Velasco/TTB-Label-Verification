from io import BytesIO

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.datastructures import Headers, UploadFile

from app.config import settings
from app.constants import AUTH_COOKIE_NAME, MAX_STRESS_TEST_IMAGES
from app.models import ApplicationData
from app.services.stress_test_generator import (
    generate_stress_test_batch,
    split_main_and_unmatched_counts,
)
from app.services.verification import VerificationService

router = APIRouter(prefix="/api/stress-test", tags=["stress-test"])
limiter = Limiter(key_func=get_remote_address)


def _require_auth(ttb_auth: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME)) -> None:
    if ttb_auth != settings.APP_ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Authentication required")


def _get_service() -> VerificationService:
    from app.main import get_verification_service
    return get_verification_service()


class StressTestCountRequest(BaseModel):
    count: int = Field(
        ...,
        ge=1,
        le=MAX_STRESS_TEST_IMAGES,
        description=f"Total images to generate (1-{MAX_STRESS_TEST_IMAGES})",
    )


class StressTestEstimate(BaseModel):
    count: int
    real_call_count: int = Field(
        ..., description="Images that actually hit the vision model (excludes the fixed unmatched-image edge cases, which are skipped before any call)"
    )
    estimated_seconds: float
    estimated_cost_usd: float | None = Field(
        None, description="None when the current provider's pricing isn't modeled (e.g. Gemini)"
    )


def _make_upload_file(filename: str, data: bytes) -> UploadFile:
    """Build an in-memory UploadFile shaped like a real HTTP upload, without
    an actual upload round trip — this image was generated in-process, not
    read from a request, so there's nothing to re-serialize.
    """
    return UploadFile(
        file=BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": "image/png"}),
    )


@router.post("/estimate", response_model=StressTestEstimate)
@limiter.limit("20/minute")
async def estimate_stress_test(
    request: Request,  # required by slowapi
    body: StressTestCountRequest,
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> StressTestEstimate:
    """Rough cost/time estimate for a /run call at the given count, meant to
    back a confirmation prompt before triggering real vision-model spend.
    """
    main_count, _unmatched_count = split_main_and_unmatched_counts(body.count)
    return StressTestEstimate(
        count=body.count,
        real_call_count=main_count,
        estimated_seconds=service.provider.estimate_seconds(main_count),
        estimated_cost_usd=service.provider.estimate_cost_usd(main_count),
    )


@router.post("/run")
@limiter.limit("2/minute")
async def run_stress_test(
    request: Request,  # required by slowapi
    body: StressTestCountRequest,
    _auth: None = Depends(_require_auth),
    service: VerificationService = Depends(_get_service),
) -> StreamingResponse:
    """Generate `count` synthetic label images in-process and verify them
    through the SAME VerificationService.verify_batch real batch runs use —
    no file upload or CSV round trip needed, since generation and
    verification both happen server-side within this one request.

    Streams NDJSON results exactly like /api/verify-batch, so the frontend
    reuses the same streaming client and batch-results UI for both.
    """
    batch = generate_stress_test_batch(body.count)
    images = [
        _make_upload_file(filename, data) for filename, data in batch.image_bytes.items()
    ]
    application_data_map = {
        row.filename: ApplicationData(**row.application_data) for row in batch.main_rows
    }

    async def stream_results():
        async for result in service.verify_batch(images, application_data_map):
            yield result.model_dump_json() + "\n"

    return StreamingResponse(
        stream_results(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
