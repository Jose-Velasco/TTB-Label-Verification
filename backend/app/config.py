from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Vision provider — e.g. "gemini/gemini-2.5-flash" or "openai/gemma3:4b"
    VISION_MODEL: str = "gemini/gemini-2.5-flash"
    OLLAMA_API_BASE: str = "http://ollama:11434/v1"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Explicit switch for the "openai/" prefix ambiguity: that prefix is used
    # both for real OpenAI models (e.g. openai/gpt-4o-mini, routed to the real
    # API) and for local Ollama-served models via its OpenAI-compatible shim
    # (e.g. openai/gemma4:e4b-it-qat, routed to OLLAMA_API_BASE). The model
    # name alone can't disambiguate these, so this flag does.
    USE_OLLAMA_API_BASE: bool = False

    # Off by default: this task is schema-guided extraction where the prompt
    # already makes the model produce structured per-field reasoning, so a
    # separate model-level thinking pass is redundant latency cost. Flip on
    # for A/B testing (accuracy vs. latency) against the golden samples.
    LLM_THINKING: bool = False

    # Downscale images to at most this many pixels (longest side) before
    # sending to a real OpenAI model. 0 disables resizing. gpt-4o-mini bills
    # images per 512px tile (~5667 tokens/tile) — the image is ~92% of total
    # prompt tokens at native label resolution, so this is the main latency
    # lever. Ollama/Gemma uses a different fixed-patch vision encoder with no
    # per-tile cost, so this only ever applies on the real-OpenAI path.
    OPENAI_IMAGE_MAX_DIMENSION: int = 0

    # OpenAI vision "detail" level: "high"/"auto" tile normally (subject to
    # OPENAI_IMAGE_MAX_DIMENSION above); "low" collapses the image to a flat
    # ~2833-token representation server-side, bypassing tiling entirely.
    # Default "high" — NOT "low" — because low detail risks making small
    # print (esp. the government warning, which needs verbatim
    # transcription) illegible on real photographed labels. "low" is
    # opt-in only, for cost-sensitive use cases willing to trade legibility
    # margin for it. Ignored on the Ollama/Gemma path (different vision
    # encoder, no such parameter).
    OPENAI_IMAGE_DETAIL: Literal["auto", "low", "high"] = "high"

    # Rate limiting
    RATE_LIMIT_RPM: int = 15

    # Tokens-per-minute ceiling for the real OpenAI API (Tier 1 gpt-4o-mini
    # default: 200k). Ignored on the Gemini/Ollama paths — only OpenAI meters
    # vision requests this way. For a fixed prompt, TPM (not RPM) is usually
    # the real throughput ceiling for image-heavy vision calls: see
    # LiteLLMVisionAdapter.max_safe_concurrency().
    OPENAI_TPM_LIMIT: int = 200_000

    # Auth
    APP_ACCESS_KEY: str = "changeme"

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
