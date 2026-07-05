from typing import Protocol, runtime_checkable

from app.models import ApplicationData, ExtractedApplicationData, VerificationResult


@runtime_checkable
class VisionProvider(Protocol):
    """Port definition — any vision backend must satisfy this interface."""

    async def verify_label(
        self,
        image_b64: str,
        image_mime: str,
        application_data: ApplicationData,
    ) -> VerificationResult: ...

    async def extract_fields(
        self,
        image_b64: str,
        image_mime: str,
    ) -> ExtractedApplicationData: ...

    def max_safe_concurrency(self) -> int:
        """Max in-flight requests a batch run should allow concurrently,
        given this provider's own rate-limit knobs (which vary by backend —
        e.g. only the real OpenAI API meters tokens-per-minute)."""
        ...

    def estimate_seconds(self, num_requests: int) -> float:
        """Rough wall-clock estimate for running num_requests verify_label
        calls at this provider's max_safe_concurrency() — for a pre-run
        cost/time confirmation prompt, not a real SLA."""
        ...

    def estimate_cost_usd(self, num_requests: int) -> float | None:
        """Rough USD cost estimate for num_requests verify_label calls, or
        None when this provider's pricing isn't modeled."""
        ...
