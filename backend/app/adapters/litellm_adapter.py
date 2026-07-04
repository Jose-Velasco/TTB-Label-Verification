import base64
from io import BytesIO

import litellm
from aiolimiter import AsyncLimiter
from PIL import Image
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

    def _is_ollama_routed(self) -> bool:
        """True when VISION_MODEL should hit the local Ollama server.

        The "openai/" litellm prefix is ambiguous on its own — it's used for
        both real OpenAI models and Ollama-served models via its
        OpenAI-compatible shim — so USE_OLLAMA_API_BASE disambiguates
        explicitly rather than guessing from the model name.
        """
        model = self.settings.VISION_MODEL.lower()
        return "ollama" in model or (
            model.startswith("openai/") and self.settings.USE_OLLAMA_API_BASE
        )

    def _resolve_api_base(self) -> str | None:
        """Return the custom API base only for Ollama-routed models."""
        if self._is_ollama_routed():
            return self.settings.OLLAMA_API_BASE
        return None

    def _resolve_api_key(self) -> str:
        """Pick the right API key based on the model string."""
        model = self.settings.VISION_MODEL.lower()
        if "gemini" in model and self.settings.GEMINI_API_KEY:
            return self.settings.GEMINI_API_KEY
        # Use Ollama dummy key when routing through local Ollama
        if self._is_ollama_routed():
            return "ollama"
        if self.settings.OPENAI_API_KEY:
            return self.settings.OPENAI_API_KEY
        return "ollama"

    def _thinking_kwargs(self) -> dict:
        """Extra litellm kwargs to control Gemma 4 thinking mode.

        We route through litellm's openai/ provider against Ollama's
        OpenAI-compatible endpoint, which ignores Ollama's native "think"
        bool (confirmed empirically: sending think=true/false/omitted all
        produced identical thinking-on behavior). The standard OpenAI
        `reasoning_effort` field IS honored by that endpoint though —
        "none" reliably disables thinking (verified: no reasoning_content,
        completion tokens drop ~60%). litellm blocks unrecognized
        reasoning_effort values for arbitrary models unless explicitly
        allowed via allowed_openai_params.
        """
        if not self._is_ollama_routed() or self.settings.LLM_THINKING:
            return {}
        return {
            "reasoning_effort": "none",
            "allowed_openai_params": ["reasoning_effort"],
        }

    def _maybe_downscale_for_openai(
        self, image_b64: str, image_mime: str
    ) -> tuple[str, str]:
        """Downscale the image before sending to a real OpenAI model.

        Only applies on the real-OpenAI path (never Ollama/Gemma — see
        OPENAI_IMAGE_MAX_DIMENSION in config.py for why). Keeps aspect ratio
        and never upscales (PIL's thumbnail() only shrinks).
        """
        max_dim = self.settings.OPENAI_IMAGE_MAX_DIMENSION
        if self._is_ollama_routed() or not max_dim:
            return image_b64, image_mime

        image = Image.open(BytesIO(base64.b64decode(image_b64)))
        image.thumbnail((max_dim, max_dim))

        fmt = "JPEG" if image_mime == "image/jpeg" else "PNG"
        if fmt == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        buf = BytesIO()
        image.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8"), image_mime

    def _build_image_url(self, image_b64: str, image_mime: str) -> dict:
        """Build the image_url payload for the vision message.

        OPENAI_IMAGE_DETAIL and OPENAI_IMAGE_MAX_DIMENSION are two
        overlapping levers on the same problem (image token cost) and must
        compose, not fight: detail="low" collapses the image to a flat
        low-res representation server-side regardless of the dimensions we
        send, so downscaling first would waste local CPU for zero token
        savings — skip it. detail="high"/"auto" tile normally, so the
        downscale still controls tile count as before. Ollama/Gemma doesn't
        understand "detail" at all (different vision encoder, no tiling),
        so it's only ever added on the real-OpenAI path.
        """
        if self._is_ollama_routed():
            return {"url": f"data:{image_mime};base64,{image_b64}"}

        detail = self.settings.OPENAI_IMAGE_DETAIL
        if detail == "low":
            return {"url": f"data:{image_mime};base64,{image_b64}", "detail": "low"}

        image_b64, image_mime = self._maybe_downscale_for_openai(image_b64, image_mime)
        return {"url": f"data:{image_mime};base64,{image_b64}", "detail": detail}

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
        image_url = self._build_image_url(image_b64, image_mime)
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
                                "image_url": image_url,
                            },
                            {
                                "type": "text",
                                "text": build_verify_prompt(application_data),
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                # Safety cap on completion length. Ollama's context window
                # (prompt + thinking + answer) is the real ceiling — see
                # OLLAMA_CONTEXT_LENGTH in docker-compose.devcontainer.yml —
                # this just bounds a single runaway generation.
                max_tokens=4096,
                **self._thinking_kwargs(),
            )

        raw = response.choices[0].message.content
        return parse_verification_response(raw, application_data)
