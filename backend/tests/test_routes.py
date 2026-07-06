import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import (
    ApplicationData,
    FieldResult,
    FieldStatus,
    OverallStatus,
    VerificationResult,
)

SAMPLE_APP_DATA = {
    "brand_name": "Stone's Throw",
    "class_type": "American Whiskey",
    "alcohol_content": "40% alc/vol",
    "net_contents": "750 mL",
    "bottler_info": "Stone's Throw Distillery",
    "country_of_origin": "USA",
    "government_warning": CANONICAL_GOVERNMENT_WARNING,
}

MINIMAL_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xD9])


def _pass_field(expected: str) -> FieldResult:
    return FieldResult(status=FieldStatus.pass_, extracted_value=expected, expected_value=expected)


def make_mock_result() -> VerificationResult:
    d = SAMPLE_APP_DATA
    return VerificationResult(
        overall_status=OverallStatus.approved,
        brand_name=_pass_field(d["brand_name"]),
        class_type=_pass_field(d["class_type"]),
        alcohol_content=_pass_field(d["alcohol_content"]),
        net_contents=_pass_field(d["net_contents"]),
        bottler_info=_pass_field(d["bottler_info"]),
        country_of_origin=_pass_field(d["country_of_origin"]),
        government_warning=_pass_field(d["government_warning"]),
    )


@pytest.fixture
def app_data_json() -> str:
    return json.dumps(SAMPLE_APP_DATA)


@pytest.fixture
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    from app.config import settings
    from app.constants import AUTH_COOKIE_NAME
    return {"Cookie": f"{AUTH_COOKIE_NAME}={settings.APP_ACCESS_KEY}"}


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.verify_single = AsyncMock(return_value=make_mock_result())
    service.provider.estimate_seconds = MagicMock(return_value=6.0)
    service.provider.estimate_cost_usd = MagicMock(return_value=0.001)
    return service


@pytest.fixture(autouse=True)
def patch_service(mock_service):
    # verify.py/batch.py/stress_test.py's _get_service() all import
    # get_verification_service from app.main *inside* the function body (to
    # avoid a circular import), so it's never a module-level attribute on
    # any of those route modules for patch() to target — app.main is the one
    # place it's actually defined, and where the deferred import resolves it
    # from at call time.
    with patch("app.main.get_verification_service", return_value=mock_service):
        yield mock_service


async def test_verify_returns_200_with_valid_jpeg(client, auth_headers, app_data_json):
    response = await client.post(
        "/api/verify",
        files={"image": ("label.jpg", MINIMAL_JPEG, "image/jpeg")},
        data={"application_data": app_data_json},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "approved"


async def test_verify_returns_400_with_missing_image(client, auth_headers, app_data_json):
    response = await client.post(
        "/api/verify",
        data={"application_data": app_data_json},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_verify_returns_401_when_not_authenticated(client, app_data_json):
    response = await client.post(
        "/api/verify",
        files={"image": ("label.jpg", MINIMAL_JPEG, "image/jpeg")},
        data={"application_data": app_data_json},
    )
    assert response.status_code == 401


async def test_login_sets_cookie_with_correct_password(client):
    from app.config import settings
    response = await client.post("/api/login", json={"password": settings.APP_ACCESS_KEY})
    assert response.status_code == 200
    assert "ttb_auth" in response.cookies


async def test_login_returns_401_with_wrong_password(client):
    response = await client.post("/api/login", json={"password": "wrong-password"})
    assert response.status_code == 401


async def test_login_cookie_omits_secure_by_default(client):
    # Default COOKIE_SECURE=False (local dev over plain HTTP).
    from app.config import settings
    response = await client.post("/api/login", json={"password": settings.APP_ACCESS_KEY})
    assert "Secure" not in response.headers.get("set-cookie", "")


async def test_login_cookie_is_secure_when_configured(client):
    from app.config import settings
    original = settings.COOKIE_SECURE
    settings.COOKIE_SECURE = True
    try:
        response = await client.post("/api/login", json={"password": settings.APP_ACCESS_KEY})
        assert "Secure" in response.headers.get("set-cookie", "")
    finally:
        settings.COOKIE_SECURE = original


async def test_stress_test_estimate_returns_projection(client, auth_headers, mock_service):
    from app.services.stress_test_generator import NUM_UNMATCHED_IMAGES

    response = await client.post(
        "/api/stress-test/estimate",
        json={"count": 20},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 20
    assert body["real_call_count"] == 20 - NUM_UNMATCHED_IMAGES
    assert body["estimated_seconds"] == 6.0
    assert body["estimated_cost_usd"] == 0.001


async def test_stress_test_estimate_rejects_count_above_cap(client, auth_headers):
    response = await client.post(
        "/api/stress-test/estimate",
        json={"count": 101},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_stress_test_estimate_requires_auth(client):
    response = await client.post("/api/stress-test/estimate", json={"count": 20})
    assert response.status_code == 401


async def test_stress_test_run_streams_ndjson(client, auth_headers, mock_service):
    async def _gen():
        yield make_mock_result()

    mock_service.verify_batch = MagicMock(return_value=_gen())

    response = await client.post(
        "/api/stress-test/run",
        json={"count": 5},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "ndjson" in response.headers.get("content-type", "")


def _field(status: FieldStatus, expected: str) -> FieldResult:
    return FieldResult(status=status, extracted_value=expected, expected_value=expected)


def _result(overall: OverallStatus, filename: str, **fail_fields: FieldStatus) -> VerificationResult:
    """Build a VerificationResult where every field passes except those
    named in fail_fields (which get the given non-pass status).
    """
    d = SAMPLE_APP_DATA
    fields = {
        name: _field(fail_fields.get(name, FieldStatus.pass_), d[name]) for name in d
    }
    return VerificationResult(overall_status=overall, filename=filename, **fields)


async def test_stress_test_run_scores_results_against_ground_truth(client, auth_headers, mock_service):
    from app.services.stress_test_generator import (
        ExpectedOutcome,
        GeneratedMainRow,
        StressTestBatch,
    )

    approved_row = GeneratedMainRow(
        filename="label_APPROVED_001.png",
        sample_id="01",
        bucket="correct",
        corrupted_field=None,
        application_data=SAMPLE_APP_DATA,
        expected=ExpectedOutcome(status="approved"),
    )
    non_compliant_row = GeneratedMainRow(
        filename="label_REJECTED (government_warning)_002.png",
        sample_id="02",
        bucket="correct",
        corrupted_field=None,
        application_data=SAMPLE_APP_DATA,
        expected=ExpectedOutcome(status="rejected", failing_fields=("government_warning",)),
    )
    fake_batch = StressTestBatch(
        main_rows=[approved_row, non_compliant_row],
        unmatched_image_filenames=["label_SKIPPED_003_unmatched.png"],
        image_bytes={
            approved_row.filename: b"png",
            non_compliant_row.filename: b"png",
            "label_SKIPPED_003_unmatched.png": b"png",
        },
    )

    async def _gen():
        # Correctly matches ground truth: approved, all fields pass.
        yield _result(OverallStatus.approved, approved_row.filename)
        # The government-warning bug: the label is non-compliant (ground
        # truth expects government_warning to fail) but the model call
        # incorrectly reports every field passing -> must be flagged as a
        # mismatch, not silently counted as correct.
        yield _result(OverallStatus.approved, non_compliant_row.filename)
        # Skipped as expected (no application data for this filename).
        yield VerificationResult(
            overall_status=OverallStatus.needs_review,
            filename="label_SKIPPED_003_unmatched.png",
            skipped=True,
            **{name: _field(FieldStatus.unreadable, "") for name in SAMPLE_APP_DATA},
        )

    mock_service.verify_batch = MagicMock(return_value=_gen())

    with patch("app.routes.stress_test.generate_stress_test_batch", return_value=fake_batch):
        response = await client.post(
            "/api/stress-test/run",
            json={"count": 3},
            headers=auth_headers,
        )

    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.strip().splitlines()]
    by_filename = {line["result"]["filename"]: line for line in lines}

    approved_line = by_filename[approved_row.filename]
    assert approved_line["expected_status"] == "approved"
    assert approved_line["outcome_match"] is True

    bug_line = by_filename[non_compliant_row.filename]
    assert bug_line["expected_status"] == "rejected"
    assert bug_line["expected_failing_fields"] == ["government_warning"]
    assert bug_line["outcome_match"] is False  # caught the bug: expected fail, got pass

    skipped_line = by_filename["label_SKIPPED_003_unmatched.png"]
    assert skipped_line["expected_status"] == "skipped"
    assert skipped_line["outcome_match"] is True


async def test_stress_test_run_rejects_count_above_cap(client, auth_headers):
    response = await client.post(
        "/api/stress-test/run",
        json={"count": 101},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_verify_batch_returns_ndjson(client, auth_headers, mock_service):
    async def _gen():
        yield make_mock_result()

    mock_service.verify_batch = MagicMock(return_value=_gen())

    response = await client.post(
        "/api/verify-batch",
        files=[
            ("images", ("a.jpg", MINIMAL_JPEG, "image/jpeg")),
            ("images", ("b.jpg", MINIMAL_JPEG, "image/jpeg")),
        ],
        data={"application_data_map": json.dumps({"a.jpg": SAMPLE_APP_DATA, "b.jpg": SAMPLE_APP_DATA})},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "ndjson" in response.headers.get("content-type", "")
