from typing import Protocol, runtime_checkable

from app.models import ApplicationData, VerificationResult


@runtime_checkable
class VisionProvider(Protocol):
    """Port definition — any vision backend must satisfy this interface."""

    async def verify_label(
        self,
        image_b64: str,
        image_mime: str,
        application_data: ApplicationData,
    ) -> VerificationResult: ...

    def max_safe_concurrency(self) -> int:
        """Max in-flight requests a batch run should allow concurrently,
        given this provider's own rate-limit knobs (which vary by backend —
        e.g. only the real OpenAI API meters tokens-per-minute)."""
        ...
