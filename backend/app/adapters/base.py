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
