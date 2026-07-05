from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.adapters.litellm_adapter import LiteLLMVisionAdapter
from app.config import settings
from app.routes import auth_router, batch_router, stress_test_router, verify_router
from app.services.verification import VerificationService

# Module-level singleton so routes can resolve it via get_verification_service()
_verification_service: VerificationService | None = None


def get_verification_service() -> VerificationService:
    if _verification_service is None:
        raise RuntimeError("VerificationService not initialized — check lifespan startup")
    return _verification_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _verification_service
    adapter = LiteLLMVisionAdapter(settings)
    _verification_service = VerificationService(adapter, settings)
    yield
    _verification_service = None


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="TTB Label Verification API",
    description="AI-powered alcohol label compliance verification for TTB agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_router)
app.include_router(verify_router)
app.include_router(batch_router)
app.include_router(stress_test_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.VISION_MODEL}
