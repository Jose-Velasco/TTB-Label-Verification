import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import ApplicationData, FieldStatus, OverallStatus


SAMPLE_APP_DATA = ApplicationData(
    brand_name="Stone's Throw",
    class_type="American Whiskey",
    alcohol_content="40% alc/vol",
    net_contents="750 mL",
    bottler_info="Stone's Throw Distillery",
    country_of_origin="USA",
    government_warning=CANONICAL_GOVERNMENT_WARNING,
)

VALID_LLM_RESPONSE = json.dumps({
    "brand_name": {"status": "pass", "extracted_value": "Stone's Throw", "note": None},
    "class_type": {"status": "pass", "extracted_value": "American Whiskey", "note": None},
    "alcohol_content": {"status": "pass", "extracted_value": "40% alc/vol", "note": None},
    "net_contents": {"status": "pass", "extracted_value": "750 mL", "note": None},
    "bottler_info": {"status": "pass", "extracted_value": "Stone's Throw Distillery", "note": None},
    "country_of_origin": {"status": "pass", "extracted_value": "USA", "note": None},
    "government_warning": {
        "status": "pass",
        "extracted_value": CANONICAL_GOVERNMENT_WARNING,
        "note": None,
    },
})


def _mock_litellm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.VISION_MODEL = "gemini/gemini-2.5-flash"
    s.OLLAMA_API_BASE = "http://ollama:11434/v1"
    s.GEMINI_API_KEY = "test-key"
    s.OPENAI_API_KEY = ""
    s.RATE_LIMIT_RPM = 60
    return s


@pytest.fixture
def adapter(mock_settings):
    from app.adapters.litellm_adapter import LiteLLMVisionAdapter
    return LiteLLMVisionAdapter(mock_settings)


async def test_valid_json_response_parses_to_verification_result(adapter):
    mock_resp = _mock_litellm_response(VALID_LLM_RESPONSE)
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await adapter.verify_label("b64data", "image/jpeg", SAMPLE_APP_DATA)

    assert result.overall_status == OverallStatus.approved
    assert result.brand_name.status == FieldStatus.pass_


async def test_invalid_json_returns_needs_review(adapter):
    mock_resp = _mock_litellm_response("this is not json at all")
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await adapter.verify_label("b64data", "image/jpeg", SAMPLE_APP_DATA)

    assert result.overall_status == OverallStatus.needs_review
    assert result.image_quality_note is not None


async def test_rate_limit_error_triggers_retry(adapter):
    import litellm
    from tenacity import wait_none
    mock_resp = _mock_litellm_response(VALID_LLM_RESPONSE)

    call_count = 0

    async def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise litellm.RateLimitError(
                message="rate limited", llm_provider="gemini", model="gemini-2.5-flash"
            )
        return mock_resp

    # Override tenacity's wait strategy to avoid real sleeps during the test.
    # The retry decorator is bound to the method; .retry is the Retrying object.
    original_wait = adapter.verify_label.retry.wait
    adapter.verify_label.retry.wait = wait_none()
    try:
        with patch("litellm.acompletion", side_effect=flaky):
            result = await adapter.verify_label("b64data", "image/jpeg", SAMPLE_APP_DATA)
    finally:
        adapter.verify_label.retry.wait = original_wait

    assert call_count == 3
    assert result.overall_status == OverallStatus.approved


async def test_image_b64_and_mime_passed_to_litellm(adapter):
    mock_resp = _mock_litellm_response(VALID_LLM_RESPONSE)
    b64 = "abc123=="
    mime = "image/png"

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp) as mock_call:
        await adapter.verify_label(b64, mime, SAMPLE_APP_DATA)

    call_kwargs = mock_call.call_args.kwargs
    messages = call_kwargs["messages"]
    image_content = messages[0]["content"][0]
    assert image_content["type"] == "image_url"
    assert f"data:{mime};base64,{b64}" in image_content["image_url"]["url"]
