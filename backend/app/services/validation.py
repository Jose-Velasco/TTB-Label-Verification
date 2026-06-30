from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import FieldResult, FieldStatus


def validate_government_warning(extracted_text: str) -> FieldResult:
    """Strict exact-match validation for the government warning statement.

    TTB regulations require the warning to appear word-for-word with
    'GOVERNMENT WARNING:' in ALL CAPS. Any deviation is a fail, not a warning.
    Leading/trailing whitespace is stripped before comparison.
    """
    normalized = extracted_text.strip()

    if normalized == CANONICAL_GOVERNMENT_WARNING:
        return FieldResult(
            status=FieldStatus.pass_,
            extracted_value=normalized,
            expected_value=CANONICAL_GOVERNMENT_WARNING,
            note=None,
        )

    # Diagnose the specific failure to aid the agent in corrections.
    if not normalized.startswith("GOVERNMENT WARNING:"):
        note = (
            "Government warning must begin with 'GOVERNMENT WARNING:' in ALL CAPS. "
            f"Found: {normalized[:50]!r}..."
        )
    elif normalized != CANONICAL_GOVERNMENT_WARNING:
        note = (
            "Government warning text does not exactly match the canonical TTB statement. "
            "Verify wording, punctuation, and capitalization."
        )
    else:
        note = "Government warning validation failed."

    return FieldResult(
        status=FieldStatus.fail,
        extracted_value=normalized,
        expected_value=CANONICAL_GOVERNMENT_WARNING,
        note=note,
    )
