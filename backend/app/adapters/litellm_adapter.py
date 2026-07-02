import litellm
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import Settings
from app.models import ApplicationData, VerificationResult
from app.prompts.verify_prompt import build_verify_prompt, parse_verification_response


class LiteLLMVisionAdapter:
    """Adapter that routes vision calls through LiteLLM.

    Swapping providers (Ollama ↔ Gemini ↔ OpenAI) requires only .env changes —
    no code modifications needed.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Proactive rate limiter: acquire a token before each API call so we
        # stay within the configured RPM ceiling at the application level.
        self.limiter = AsyncLimiter(settings.RATE_LIMIT_RPM, 60)

    # def _resolve_api_base(self) -> str | None:
    #     """Return the custom API base only for Ollama-routed models."""
    #     if "ollama" in self.settings.VISION_MODEL.lower():
    #         return self.settings.OLLAMA_API_BASE
    #     return None

    def _resolve_api_base(self) -> str | None:
        """Return the custom API base only for Ollama-routed models."""
        if "ollama" in self.settings.VISION_MODEL.lower():
            return self.settings.OLLAMA_API_BASE
        # Also use Ollama base when OLLAMA_API_BASE is set and model uses openai/ prefix
        if (
            self.settings.VISION_MODEL.startswith("openai/")
            and self.settings.OLLAMA_API_BASE
        ):
            return self.settings.OLLAMA_API_BASE
        return None

    def _resolve_api_key(self) -> str:
        """Pick the right API key based on the model string."""
        model = self.settings.VISION_MODEL.lower()
        if "gemini" in model and self.settings.GEMINI_API_KEY:
            return self.settings.GEMINI_API_KEY
        # Use Ollama dummy key when routing through local Ollama
        if "ollama" in model or (
            model.startswith("openai/") and bool(self.settings.OLLAMA_API_BASE)
        ):
            return "ollama"
        if self.settings.OPENAI_API_KEY:
            return self.settings.OPENAI_API_KEY
        return "ollama"

    # def _resolve_api_key(self) -> str:
    #     """Pick the right API key based on the model string."""
    #     model = self.settings.VISION_MODEL.lower()
    #     if "gemini" in model and self.settings.GEMINI_API_KEY:
    #         return self.settings.GEMINI_API_KEY
    #     if self.settings.OPENAI_API_KEY:
    #         return self.settings.OPENAI_API_KEY
    #     # Ollama doesn't require a real key
    #     return "ollama"

    @retry(
        retry=retry_if_exception_type(
            (litellm.RateLimitError, litellm.ServiceUnavailableError)
        ),
        wait=wait_random_exponential(min=4, max=60),
        stop=stop_after_attempt(3),
    )
    async def verify_label(
        self,
        image_b64: str,
        image_mime: str,
        application_data: ApplicationData,
    ) -> VerificationResult:
        """Extract and verify label fields against application data.

        Tenacity retries on rate-limit / transient errors with random exponential
        backoff — prevents thundering-herd on the provider during batch runs.
        """
        print(self.settings)
        async with self.limiter:
            response = await litellm.acompletion(
                model=self.settings.VISION_MODEL,
                api_base=self._resolve_api_base(),
                api_key=self._resolve_api_key(),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_mime};base64,{image_b64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": build_verify_prompt(application_data),
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
            )

        raw = response.choices[0].message.content
        return parse_verification_response(raw, application_data)
