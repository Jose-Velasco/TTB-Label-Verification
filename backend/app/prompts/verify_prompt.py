import json
import logging

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import ApplicationData, FieldResult, FieldStatus, OverallStatus, VerificationResult

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a TTB (Alcohol and Tobacco Tax and Trade Bureau) label compliance specialist.
Examine the alcohol label image and extract the following fields, then compare each
against the expected application data provided.

EXPECTED APPLICATION DATA:
- Brand Name: {brand_name}
- Class/Type: {class_type}
- Alcohol Content: {alcohol_content}
- Net Contents: {net_contents}
- Bottler Info: {bottler_info}
- Country of Origin: {country_of_origin}
- Government Warning: {government_warning}

INSTRUCTIONS:
1. For each field, extract the exact text visible on the label.
2. Compare the extracted text to the expected value using FUZZY matching — minor
   differences in capitalization, spacing, punctuation, abbreviations, or unit
   formatting (e.g. "750ml" == "750 mL", "Stone's Throw" == "STONE'S THROW") should
   be treated as a PASS.
3. The government_warning field is handled separately by the backend; extract it
   as-is and give it status "pass" — the backend will apply exact-match validation.
4. If a field is completely absent from the label, set status to "fail".
5. If the image quality prevents reading a field, set status to "unreadable".
6. If there is a minor but notable discrepancy, set status to "warning".
7. Do NOT apply exact-match logic yourself for any field except government_warning
   (the backend handles that separately).

Respond with ONLY valid JSON — no markdown fences, no preamble, no explanation.
Use this exact schema:

{{
  "brand_name": {{
    "status": "pass" | "fail" | "warning" | "unreadable",
    "extracted_value": "<text from label or null if unreadable>",
    "note": "<optional explanation for non-pass status>"
  }},
  "class_type": {{ ... }},
  "alcohol_content": {{ ... }},
  "net_contents": {{ ... }},
  "bottler_info": {{ ... }},
  "country_of_origin": {{ ... }},
  "government_warning": {{
    "status": "pass",
    "extracted_value": "<full government warning text as it appears on the label>",
    "note": null
  }}
}}
"""


def build_verify_prompt(application_data: ApplicationData) -> str:
    return _PROMPT_TEMPLATE.format(
        brand_name=application_data.brand_name,
        class_type=application_data.class_type,
        alcohol_content=application_data.alcohol_content,
        net_contents=application_data.net_contents,
        bottler_info=application_data.bottler_info,
        country_of_origin=application_data.country_of_origin,
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )


def _make_needs_review_result(
    application_data: ApplicationData, note: str
) -> VerificationResult:
    """Return a safe fallback result when the model response cannot be parsed."""
    return VerificationResult(
        overall_status=OverallStatus.needs_review,
        brand_name=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.brand_name,
            note=note,
        ),
        class_type=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.class_type,
            note=note,
        ),
        alcohol_content=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.alcohol_content,
            note=note,
        ),
        net_contents=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.net_contents,
            note=note,
        ),
        bottler_info=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.bottler_info,
            note=note,
        ),
        country_of_origin=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.country_of_origin,
            note=note,
        ),
        government_warning=FieldResult(
            status=FieldStatus.unreadable,
            extracted_value=None,
            expected_value=application_data.government_warning,
            note=note,
        ),
        image_quality_note=note,
    )


def parse_verification_response(
    raw: str, application_data: ApplicationData
) -> VerificationResult:
    """Parse the model's JSON response and apply government warning exact-match."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        note = f"Model returned unparseable response: {exc}"
        logger.warning(note)
        return _make_needs_review_result(application_data, note)

    try:
        # Import here to break the potential circular import chain:
        # prompts → services.validation → (no further imports from prompts)
        from app.services.validation import validate_government_warning as _validate_gw

        fields = {}
        field_names = [
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "bottler_info",
            "country_of_origin",
            "government_warning",
        ]
        expected_map = {
            "brand_name": application_data.brand_name,
            "class_type": application_data.class_type,
            "alcohol_content": application_data.alcohol_content,
            "net_contents": application_data.net_contents,
            "bottler_info": application_data.bottler_info,
            "country_of_origin": application_data.country_of_origin,
            "government_warning": application_data.government_warning,
        }

        for name in field_names:
            fd = data.get(name, {})
            status_raw = fd.get("status", "unreadable")
            try:
                status = FieldStatus(status_raw)
            except ValueError:
                status = FieldStatus.unreadable

            fields[name] = FieldResult(
                status=status,
                extracted_value=fd.get("extracted_value"),
                expected_value=expected_map[name],
                note=fd.get("note"),
            )

        # Backend applies exact-match for government warning regardless of what the
        # model decided — this ensures the strict TTB requirement is always enforced.
        gw_field = fields["government_warning"]
        if gw_field.extracted_value is not None:
            gw_result = _validate_gw(gw_field.extracted_value)
            fields["government_warning"] = FieldResult(
                status=gw_result.status,
                extracted_value=gw_field.extracted_value,
                expected_value=application_data.government_warning,
                note=gw_result.note,
            )

        result = VerificationResult(
            overall_status=OverallStatus.approved,  # will be recomputed below
            **fields,
        )
        # Recompute overall status from actual field statuses
        result.overall_status = result.computed_overall_status
        return result

    except Exception as exc:
        note = f"Failed to build VerificationResult from model output: {exc}"
        logger.warning(note)
        return _make_needs_review_result(application_data, note)
