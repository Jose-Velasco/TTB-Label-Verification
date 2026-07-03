import pytest

from app.adapters.litellm_adapter import LiteLLMVisionAdapter
from app.config import Settings
from tests.eval._golden_data import load_golden_samples, rasterize_sample_svg


@pytest.fixture(scope="session")
def golden_samples() -> list[dict]:
    """The parsed contents of frontend/public/samples/data.json."""
    return load_golden_samples()


@pytest.fixture(scope="session")
def rasterize_sample():
    """Factory fixture: given a sample SVG filename, return rasterized PNG bytes."""
    return rasterize_sample_svg


@pytest.fixture
def vision_adapter() -> LiteLLMVisionAdapter:
    """A real LiteLLMVisionAdapter built from Settings loaded from the environment.

    Uses whatever VISION_MODEL / OLLAMA_API_BASE / GEMINI_API_KEY is configured
    when the test runs — no mocking. Function-scoped (not session-scoped) because
    the adapter's internal AsyncLimiter binds to the event loop it's created in,
    and pytest-asyncio gives each test function its own loop by default.
    """
    return LiteLLMVisionAdapter(Settings())
