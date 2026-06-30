import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import (
    ApplicationData,
    FieldResult,
    FieldStatus,
    OverallStatus,
    VerificationResult,
)
from app.services.verification import VerificationService


def make_upload_file(content: bytes, filename: str = "test.jpg", content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


def _pass_field(expected: str) -> FieldResult:
    return FieldResult(status=FieldStatus.pass_, extracted_value=expected, expected_value=expected)


def _mock_result(app_data: ApplicationData) -> VerificationResult:
    return VerificationResult(
        overall_status=OverallStatus.approved,
        brand_name=_pass_field(app_data.brand_name),
        class_type=_pass_field(app_data.class_type),
        alcohol_content=_pass_field(app_data.alcohol_content),
        net_contents=_pass_field(app_data.net_contents),
        bottler_info=_pass_field(app_data.bottler_info),
        country_of_origin=_pass_field(app_data.country_of_origin),
        government_warning=_pass_field(app_data.government_warning),
    )


@pytest.fixture
def sample_app_data() -> ApplicationData:
    return ApplicationData(
        brand_name="Stone's Throw",
        class_type="American Whiskey",
        alcohol_content="40% alc/vol",
        net_contents="750 mL",
        bottler_info="Stone's Throw Distillery",
        country_of_origin="USA",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.RATE_LIMIT_RPM = 15
    return settings


@pytest.fixture
def mock_provider():
    return AsyncMock()


@pytest.fixture
def service(mock_provider, mock_settings) -> VerificationService:
    return VerificationService(mock_provider, mock_settings)


@pytest.fixture
def jpeg_bytes() -> bytes:
    return bytes([0xFF, 0xD8, 0xFF, 0xD9])  # minimal valid JPEG marker


async def test_verify_single_passes_correct_inputs(service, mock_provider, sample_app_data):
    expected = _mock_result(sample_app_data)
    mock_provider.verify_label.return_value = expected

    upload = make_upload_file(b"\xFF\xD8\xFF\xD9", "label.jpg", "image/jpeg")
    result = await service.verify_single(upload, sample_app_data)

    mock_provider.verify_label.assert_called_once()
    call_args = mock_provider.verify_label.call_args
    assert call_args.kwargs["application_data"] == sample_app_data or call_args.args[2] == sample_app_data
    assert result.overall_status == OverallStatus.approved


async def test_verify_single_returns_correct_shape(service, mock_provider, sample_app_data):
    expected = _mock_result(sample_app_data)
    mock_provider.verify_label.return_value = expected

    upload = make_upload_file(b"\xFF\xD8\xFF\xD9", "label.jpg", "image/jpeg")
    result = await service.verify_single(upload, sample_app_data)

    assert isinstance(result, VerificationResult)
    assert result.processing_time_ms is not None
    assert result.filename == "label.jpg"


async def test_adapter_exception_returns_needs_review(service, mock_provider, sample_app_data):
    mock_provider.verify_label.side_effect = RuntimeError("Network error")

    upload = make_upload_file(b"\xFF\xD8\xFF\xD9", "label.jpg", "image/jpeg")
    result = await service.verify_single(upload, sample_app_data)

    assert result.overall_status == OverallStatus.needs_review
    assert result.image_quality_note is not None


async def test_invalid_mime_type_returns_needs_review(service, mock_provider, sample_app_data):
    upload = make_upload_file(b"%PDF-1.4", "doc.pdf", "application/pdf")
    result = await service.verify_single(upload, sample_app_data)

    assert result.overall_status == OverallStatus.needs_review
    mock_provider.verify_label.assert_not_called()
