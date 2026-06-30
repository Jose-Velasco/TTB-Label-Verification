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
    return service


@pytest.fixture(autouse=True)
def patch_service(mock_service):
    with patch("app.routes.verify.get_verification_service", return_value=mock_service), \
         patch("app.routes.batch.get_verification_service", return_value=mock_service):
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


async def test_verify_batch_returns_ndjson(client, auth_headers, app_data_json, mock_service):
    async def _gen():
        yield make_mock_result()

    mock_service.verify_batch = MagicMock(return_value=_gen())

    response = await client.post(
        "/api/verify-batch",
        files=[
            ("images", ("a.jpg", MINIMAL_JPEG, "image/jpeg")),
            ("images", ("b.jpg", MINIMAL_JPEG, "image/jpeg")),
        ],
        data={"application_data": app_data_json},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "ndjson" in response.headers.get("content-type", "")
