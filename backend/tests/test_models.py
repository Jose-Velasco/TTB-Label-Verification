import pytest
from pydantic import ValidationError

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import (
    ApplicationData,
    FieldResult,
    FieldStatus,
    OverallStatus,
    VerificationResult,
)


def test_valid_application_data_parses():
    data = ApplicationData(
        brand_name="Stone's Throw",
        class_type="American Whiskey",
        alcohol_content="40% alc/vol",
        net_contents="750 mL",
        bottler_info="Stone's Throw Distillery, Portland OR",
        country_of_origin="United States of America",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )
    assert data.brand_name == "Stone's Throw"


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        ApplicationData(
            brand_name="Test",
            # class_type missing
            alcohol_content="40%",
            net_contents="750 mL",
            bottler_info="Test Co",
            country_of_origin="USA",
            government_warning=CANONICAL_GOVERNMENT_WARNING,
        )


def _make_field(status: FieldStatus) -> FieldResult:
    return FieldResult(status=status, extracted_value="x", expected_value="x")


def _make_result(**overrides) -> VerificationResult:
    defaults = {
        "overall_status": OverallStatus.approved,
        "brand_name": _make_field(FieldStatus.pass_),
        "class_type": _make_field(FieldStatus.pass_),
        "alcohol_content": _make_field(FieldStatus.pass_),
        "net_contents": _make_field(FieldStatus.pass_),
        "bottler_info": _make_field(FieldStatus.pass_),
        "country_of_origin": _make_field(FieldStatus.pass_),
        "government_warning": _make_field(FieldStatus.pass_),
    }
    defaults.update(overrides)
    return VerificationResult(**defaults)


def test_all_pass_fields_gives_approved():
    result = _make_result()
    assert result.computed_overall_status == OverallStatus.approved


def test_any_fail_field_gives_rejected():
    result = _make_result(brand_name=_make_field(FieldStatus.fail))
    assert result.computed_overall_status == OverallStatus.rejected


def test_warning_only_gives_needs_review():
    result = _make_result(net_contents=_make_field(FieldStatus.warning))
    assert result.computed_overall_status == OverallStatus.needs_review


def test_unreadable_only_gives_needs_review():
    result = _make_result(bottler_info=_make_field(FieldStatus.unreadable))
    assert result.computed_overall_status == OverallStatus.needs_review


def test_fail_takes_priority_over_warning():
    result = _make_result(
        brand_name=_make_field(FieldStatus.fail),
        net_contents=_make_field(FieldStatus.warning),
    )
    assert result.computed_overall_status == OverallStatus.rejected


# --- government_warning.prefix_bold (soft signal, not a hard gate) ---


def _make_gw_field(status: FieldStatus, prefix_bold) -> FieldResult:
    return FieldResult(status=status, extracted_value="x", expected_value="x", prefix_bold=prefix_bold)


def test_prefix_bold_no_downgrades_otherwise_approved_to_needs_review():
    result = _make_result(government_warning=_make_gw_field(FieldStatus.pass_, "no"))
    assert result.computed_overall_status == OverallStatus.needs_review


def test_prefix_bold_yes_keeps_approved():
    result = _make_result(government_warning=_make_gw_field(FieldStatus.pass_, "yes"))
    assert result.computed_overall_status == OverallStatus.approved


def test_prefix_bold_uncertain_keeps_approved():
    result = _make_result(government_warning=_make_gw_field(FieldStatus.pass_, "uncertain"))
    assert result.computed_overall_status == OverallStatus.approved


def test_prefix_bold_none_keeps_approved():
    # e.g. non-government_warning fields, which never set prefix_bold.
    result = _make_result(government_warning=_make_gw_field(FieldStatus.pass_, None))
    assert result.computed_overall_status == OverallStatus.approved


def test_prefix_bold_no_does_not_override_an_actual_rejection():
    result = _make_result(
        brand_name=_make_field(FieldStatus.fail),
        government_warning=_make_gw_field(FieldStatus.pass_, "no"),
    )
    assert result.computed_overall_status == OverallStatus.rejected


def test_prefix_bold_no_does_not_override_an_existing_needs_review():
    result = _make_result(
        net_contents=_make_field(FieldStatus.warning),
        government_warning=_make_gw_field(FieldStatus.pass_, "no"),
    )
    assert result.computed_overall_status == OverallStatus.needs_review
