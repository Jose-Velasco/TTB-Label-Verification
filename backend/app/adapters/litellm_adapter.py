import base64
import re
from io import BytesIO

import litellm
from aiolimiter import AsyncLimiter
from PIL import Image
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import Settings
from app.models import ApplicationData, ExtractedApplicationData, VerificationResult
from app.prompts.extract_prompt import build_extract_prompt, parse_extraction_response
from app.prompts.verify_prompt import build_verify_prompt, parse_verification_response

# --- Retry tuning for RateLimitError vs. other transient errors ---
#
# A 429 tells us almost exactly how long to wait (OpenAI/litellm expose it via
# the Retry-After header or, failing that, embed it in the message itself —
# e.g. "Please try again in 1.003s"), so honor that instead of guessing with
# the same generic exponential backoff used for a 5xx. ServiceUnavailableError
# carries no such hint, so it keeps the original fixed backoff/attempt count.
_RETRY_AFTER_MESSAGE_RE = re.compile(r"try again in\s+([\d.]+)\s*s", re.IGNORECASE)
_RATE_LIMIT_WAIT_BUFFER_SECONDS = 0.5  # pad past the provider's own estimate
_RATE_LIMIT_MAX_WAIT_SECONDS = 60.0  # TPM/RPM windows reset within this on paid tiers
_RATE_LIMIT_MAX_ATTEMPTS = 6  # more patient than a generic transient error
_TRANSIENT_MAX_ATTEMPTS = 3  # unchanged: ServiceUnavailableError's original policy
_rate_limit_fallback_wait = wait_random_exponential(min=5, max=_RATE_LIMIT_MAX_WAIT_SECONDS)
_transient_wait = wait_random_exponential(min=4, max=60)

# --- Token estimate for TPM-aware batch concurrency (see max_safe_concurrency) ---
_LOW_DETAIL_TOKENS = 2833  # flat cost for OPENAI_IMAGE_DETAIL="low"
_TOKENS_PER_TILE = 5667  # gpt-4o-mini cost per 512x512 tile at "high"/"auto"
_TEXT_OVERHEAD_TOKENS = 700  # prompt text + typical completion, non-image
_MEASURED_AVG_TOKENS_UNBOUNDED_HIGH_DETAIL = 39_000  # real-world avg, no downscale cap

# --- Pre-run cost/time estimate (see estimate_seconds / estimate_cost_usd) ---
# Rough empirical average wall-clock time for a single /verify call (model
# latency, not counting queueing behind other concurrent calls) — used only
# to give a user a ballpark before they kick off a batch, not a real SLA.
_ESTIMATED_SECONDS_PER_CALL = 6.0
# gpt-4o-mini published per-token pricing (USD), approximate and current as
# of writing. Blended toward the input rate since a /verify call is almost
# entirely image+prompt tokens with a comparatively small JSON completion
# (max_tokens=4096, actual usage well under that) — treating the whole
# estimate as input-priced overstates cost only slightly.
_OPENAI_GPT4O_MINI_PRICE_PER_TOKEN = 0.15 / 1_000_000


def _parse_duration_string(value: str) -> float | None:
    """Parse a compact "1h2m3.4s"-style duration (e.g. litellm/OpenAI's
    x-ratelimit-reset-* headers). Returns None if nothing recognizable."""
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", value.strip())
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = match.groups()
    return (
        (float(hours) if hours else 0.0) * 3600
        + (float(minutes) if minutes else 0.0) * 60
        + (float(seconds) if seconds else 0.0)
    )


def _extract_retry_after_seconds(exc: BaseException) -> float | None:
    """Best-effort extraction of the provider's own suggested wait time.

    Checked in order: the standard `Retry-After` header, OpenAI's
    `x-ratelimit-reset-tokens`/`x-ratelimit-reset-requests` headers (only
    present on the real OpenAI API), then the "Please try again in 1.003s"
    text OpenAI embeds in the error message body when no header is present.
    litellm.RateLimitError.response is only populated with real headers when
    the upstream SDK's original httpx.Response carried them through — see
    litellm.exceptions.RateLimitError's docstring on `self.headers` — so this
    degrades gracefully to the message-text parse when headers are absent.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers:
        retry_after = headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        for header_name in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            reset_value = headers.get(header_name)
            if reset_value:
                parsed = _parse_duration_string(reset_value)
                if parsed is not None:
                    return parsed

    match = _RETRY_AFTER_MESSAGE_RE.search(str(exc))
    if match:
        return float(match.group(1))
    return None


def _wait_for_verify_retry(retry_state: RetryCallState) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, litellm.RateLimitError):
        retry_after = _extract_retry_after_seconds(exc)
        if retry_after is not None:
            wait_seconds = retry_after + _RATE_LIMIT_WAIT_BUFFER_SECONDS
            return min(wait_seconds, _RATE_LIMIT_MAX_WAIT_SECONDS)
        # No hint available from headers or message — TPM/RPM windows reset
        # within seconds to well under a minute on paid tiers, so back off
        # more generously than a generic transient error rather than risk
        # exhausting retries right as the window is about to clear.
        return _rate_limit_fallback_wait(retry_state)
    return _transient_wait(retry_state)


def _stop_for_verify_retry(retry_state: RetryCallState) -> bool:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    max_attempts = (
        _RATE_LIMIT_MAX_ATTEMPTS
        if isinstance(exc, litellm.RateLimitError)
        else _TRANSIENT_MAX_ATTEMPTS
    )
    return stop_after_attempt(max_attempts)(retry_state)


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

    def _is_real_openai_model(self) -> bool:
        """True on the real OpenAI API path (not Ollama, not Gemini) — the
        only path metered by OPENAI_TPM_LIMIT. Mirrors the same branching
        `_resolve_api_key` uses to fall through to a real OpenAI key."""
        model = self.settings.VISION_MODEL.lower()
        return not self._is_ollama_routed() and "gemini" not in model

    def _estimate_tokens_per_request(self) -> int:
        """Estimate total tokens (prompt + image + completion) for one
        /verify call, derived from the same OPENAI_IMAGE_MAX_DIMENSION /
        OPENAI_IMAGE_DETAIL knobs that control actual image token cost — so
        the estimate moves if those settings are ever retuned, instead of a
        hardcoded number silently drifting from reality.

        gpt-4o-mini vision pricing: "low" detail is a flat ~2833 tokens
        regardless of image size; "high"/"auto" tiles the (possibly
        downscaled) image into 512x512 tiles at ~5667 tokens/tile on top of
        the same ~2833 base (see OPENAI_IMAGE_MAX_DIMENSION/OPENAI_IMAGE_DETAIL
        comments in config.py for the same figures). _TEXT_OVERHEAD_TOKENS
        folds in the (comparatively small) prompt text + completion cost.
        """
        if self.settings.OPENAI_IMAGE_DETAIL == "low":
            return _LOW_DETAIL_TOKENS + _TEXT_OVERHEAD_TOKENS

        max_dim = self.settings.OPENAI_IMAGE_MAX_DIMENSION
        if not max_dim:
            # No downscale cap configured — native photo resolution varies
            # per upload and isn't knowable ahead of time, so fall back to
            # the real-world measured average at these (current default)
            # settings rather than guess a tile count.
            return _MEASURED_AVG_TOKENS_UNBOUNDED_HIGH_DETAIL

        tiles_per_side = -(-max_dim // 512)  # ceil division
        num_tiles = tiles_per_side * tiles_per_side
        return _LOW_DETAIL_TOKENS + _TOKENS_PER_TILE * num_tiles + _TEXT_OVERHEAD_TOKENS

    def max_safe_concurrency(self) -> int:
        """Max in-flight requests a batch run should allow concurrently,
        bounded by whichever of RPM or TPM is more restrictive right now.

        RPM bound: reserve at most 25% of the per-minute request budget for
        concurrent inflight calls (the same RATE_LIMIT_RPM ceiling the
        per-call AsyncLimiter above enforces one request at a time).

        TPM bound: real OpenAI vision requests are token-heavy enough that
        TPM, not RPM, is usually the actual ceiling — e.g. at this class's
        default settings (200k TPM, ~39k tokens/request) only ~5 requests/
        minute are sustainable regardless of a much higher RPM allowance.
        Only meaningful on the real OpenAI path; Gemini/Ollama don't share
        this constraint (different metering, or no metering at all).
        """
        rpm_bound = max(1, self.settings.RATE_LIMIT_RPM // 4)

        if not self._is_real_openai_model():
            return rpm_bound

        tokens_per_request = self._estimate_tokens_per_request()
        tpm_bound = max(1, self.settings.OPENAI_TPM_LIMIT // tokens_per_request)
        return min(rpm_bound, tpm_bound)

    def estimate_seconds(self, num_requests: int) -> float:
        """Rough wall-clock estimate: num_requests calls running
        max_safe_concurrency() at a time, each taking ~_ESTIMATED_SECONDS_PER_CALL.
        """
        if num_requests <= 0:
            return 0.0
        concurrency = self.max_safe_concurrency()
        batches = -(-num_requests // concurrency)  # ceil division
        return batches * _ESTIMATED_SECONDS_PER_CALL

    def estimate_cost_usd(self, num_requests: int) -> float | None:
        """Rough USD cost for num_requests calls at current model/detail
        settings. $0 on the local Ollama path; None on Gemini, whose pricing
        isn't modeled here.
        """
        if num_requests <= 0:
            return 0.0
        if self._is_ollama_routed():
            return 0.0
        if not self._is_real_openai_model():
            return None
        tokens_per_request = self._estimate_tokens_per_request()
        return num_requests * tokens_per_request * _OPENAI_GPT4O_MINI_PRICE_PER_TOKEN

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
        wait=_wait_for_verify_retry,
        stop=_stop_for_verify_retry,
    )
    async def verify_label(
        self,
        image_b64: str,
        image_mime: str,
        application_data: ApplicationData,
    ) -> VerificationResult:
        """Extract and verify label fields against application data.

        Tenacity retries RateLimitError using the provider's own suggested
        wait time when available (falling back to a patient backoff), and
        ServiceUnavailableError with a generic exponential backoff — see
        _wait_for_verify_retry / _stop_for_verify_retry above.
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

    @retry(
        retry=retry_if_exception_type(
            (litellm.RateLimitError, litellm.ServiceUnavailableError)
        ),
        wait=_wait_for_verify_retry,
        stop=_stop_for_verify_retry,
    )
    async def extract_fields(
        self,
        image_b64: str,
        image_mime: str,
    ) -> ExtractedApplicationData:
        """Read the 7 application-data fields off a label image with no
        expected values to compare against — used to pre-populate the
        application-data form from a freshly captured/uploaded photo.
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
                            {"type": "image_url", "image_url": image_url},
                            {"type": "text", "text": build_extract_prompt()},
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=1024,
                **self._thinking_kwargs(),
            )

        raw = response.choices[0].message.content
        return parse_extraction_response(raw)
