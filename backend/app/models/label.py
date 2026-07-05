from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    pass_ = "pass"
    fail = "fail"
    warning = "warning"
    unreadable = "unreadable"


class OverallStatus(str, Enum):
    approved = "approved"
    rejected = "rejected"
    needs_review = "needs_review"


class ApplicationData(BaseModel):
    """Fields submitted by the TTB compliance agent for comparison against the label."""

    brand_name: str = Field(..., description="Brand name as it appears on the application")
    class_type: str = Field(..., description="Class and type designation (e.g., 'American Whiskey')")
    alcohol_content: str = Field(..., description="Alcohol by volume (e.g., '40% alc/vol')")
    net_contents: str = Field(..., description="Net contents (e.g., '750 mL')")
    bottler_info: str = Field(..., description="Name and address of bottler/importer")
    country_of_origin: str = Field(..., description="Country of origin")
    government_warning: str = Field(..., description="Full government warning text as it should appear")


class ExtractedApplicationData(BaseModel):
    """Fields read off a photographed label via /api/extract.

    A data-entry accelerator, not authoritative data — any field may be null
    if the model couldn't read it, and the agent must confirm/correct these
    against the actual application before verifying.
    """

    brand_name: Optional[str] = None
    class_type: Optional[str] = None
    alcohol_content: Optional[str] = None
    net_contents: Optional[str] = None
    bottler_info: Optional[str] = None
    country_of_origin: Optional[str] = None
    government_warning: Optional[str] = None


class FieldResult(BaseModel):
    """Verification result for a single label field."""

    status: FieldStatus
    extracted_value: Optional[str] = Field(
        None, description="Value read from the label image; None if unreadable"
    )
    expected_value: str = Field(..., description="Value from the application data")
    note: Optional[str] = Field(None, description="Explanation for fail/warning/unreadable status")


class VerificationResult(BaseModel):
    """Complete verification result for one label image."""

    overall_status: OverallStatus
    brand_name: FieldResult
    class_type: FieldResult
    alcohol_content: FieldResult
    net_contents: FieldResult
    bottler_info: FieldResult
    country_of_origin: FieldResult
    government_warning: FieldResult
    processing_time_ms: Optional[float] = None
    image_quality_note: Optional[str] = Field(
        None, description="Note when image quality prevents reliable extraction"
    )
    filename: Optional[str] = None

    @property
    def computed_overall_status(self) -> OverallStatus:
        """Derive overall status from field statuses — used for consistent logic."""
        fields = [
            self.brand_name,
            self.class_type,
            self.alcohol_content,
            self.net_contents,
            self.bottler_info,
            self.country_of_origin,
            self.government_warning,
        ]
        statuses = {f.status for f in fields}
        if FieldStatus.fail in statuses:
            return OverallStatus.rejected
        if FieldStatus.warning in statuses or FieldStatus.unreadable in statuses:
            return OverallStatus.needs_review
        return OverallStatus.approved
