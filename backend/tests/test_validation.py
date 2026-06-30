import pytest

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import FieldStatus
from app.services.validation import validate_government_warning


def test_exact_canonical_warning_passes():
    result = validate_government_warning(CANONICAL_GOVERNMENT_WARNING)
    assert result.status == FieldStatus.pass_


def test_title_case_prefix_fails():
    bad = CANONICAL_GOVERNMENT_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    result = validate_government_warning(bad)
    assert result.status == FieldStatus.fail
    assert "ALL CAPS" in result.note


def test_truncated_warning_fails():
    truncated = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )
    result = validate_government_warning(truncated)
    assert result.status == FieldStatus.fail


def test_altered_wording_fails():
    altered = CANONICAL_GOVERNMENT_WARNING.replace("impairs", "affects")
    result = validate_government_warning(altered)
    assert result.status == FieldStatus.fail


def test_leading_trailing_whitespace_stripped():
    padded = f"  {CANONICAL_GOVERNMENT_WARNING}  "
    result = validate_government_warning(padded)
    assert result.status == FieldStatus.pass_


def test_empty_string_fails():
    result = validate_government_warning("")
    assert result.status == FieldStatus.fail


def test_missing_prefix_fails():
    no_prefix = CANONICAL_GOVERNMENT_WARNING.replace("GOVERNMENT WARNING: ", "")
    result = validate_government_warning(no_prefix)
    assert result.status == FieldStatus.fail
