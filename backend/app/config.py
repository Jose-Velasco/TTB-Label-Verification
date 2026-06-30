from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Vision provider — e.g. "gemini/gemini-2.5-flash" or "openai/gemma3:4b"
    VISION_MODEL: str = "gemini/gemini-2.5-flash"
    OLLAMA_API_BASE: str = "http://ollama:11434/v1"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Rate limiting
    RATE_LIMIT_RPM: int = 15

    # Auth
    APP_ACCESS_KEY: str = "changeme"

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
