from io import BytesIO

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.datastructures import Headers, UploadFile

from app.config import settings
from app.constants import AUTH_COOKIE_NAME, MAX_STRESS_TEST_IMAGES
from app.models import ApplicationData, FieldStatus, VerificationResult
from app.services.stress_test_generator import (
    ExpectedOutcome,
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


class StressTestResult(BaseModel):
    """One streamed NDJSON line for /run: the real verification result plus
    the ground truth the generator built into that image, so the frontend
    can show correctness (not just outcome) without re-deriving it.
    """

    result: VerificationResult
    expected_status: str = Field(
        ..., description="Ground truth overall outcome: 'approved', 'rejected', or 'skipped'"
    )
    expected_failing_fields: list[str] = Field(
        default_factory=list,
        description="Fields the generator deliberately corrupted or that are always-failing (only meaningful when expected_status is 'rejected')",
    )
    outcome_match: bool = Field(
        ..., description="Whether this result's status (and, if rejected, its failing fields) matched the ground truth"
    )


def _score_result(result: VerificationResult, expected: ExpectedOutcome) -> bool:
    """Does the real verify result match what the generator built into this
    image? For rejected cases, the EXPECTED field(s) must have actually
    failed — not just some other field.
    """
    if expected.status == "skipped":
        return result.skipped
    if result.skipped or result.overall_status.value != expected.status:
        return False
    if expected.status == "rejected":
        return all(
            getattr(result, field_name).status == FieldStatus.fail
            for field_name in expected.failing_fields
        )
    return True


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

    Streams NDJSON like /api/verify-batch, but each line is a StressTestResult
    (the VerificationResult plus the ground truth baked into that image) so
    the frontend can score correctness, not just display outcomes.
    """
    batch = generate_stress_test_batch(body.count)
    images = [
        _make_upload_file(filename, data) for filename, data in batch.image_bytes.items()
    ]
    application_data_map = {
        row.filename: ApplicationData(**row.application_data) for row in batch.main_rows
    }

    expected_outcomes = batch.expected_outcomes

    async def stream_results():
        async for result in service.verify_batch(images, application_data_map):
            expected = expected_outcomes.get(result.filename or "")
            if expected is None:
                # Every filename this endpoint generates has ground truth —
                # this would only happen if something re-filenamed a result.
                expected = ExpectedOutcome(status="unknown")
            item = StressTestResult(
                result=result,
                expected_status=expected.status,
                expected_failing_fields=list(expected.failing_fields),
                outcome_match=_score_result(result, expected),
            )
            yield item.model_dump_json() + "\n"

    return StreamingResponse(
        stream_results(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
