import json

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import ApplicationData
from app.prompts.verify_prompt import parse_verification_response


def test_expected_value_never_crosses_fields():
    """Regression test: each FieldResult.expected_value must come from its OWN
    application_data field, never another field's value. Every field below is
    given a visibly distinct value so any positional/index-based mismatch in
    the field-to-expected-value mapping would be caught immediately.
    """
    application_data = ApplicationData(
        brand_name="FIELD_A",
        class_type="FIELD_B",
        alcohol_content="FIELD_C",
        net_contents="FIELD_D",
        bottler_info="FIELD_E",
        country_of_origin="FIELD_F",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )

    llm_response = json.dumps({
        "brand_name": {"status": "pass", "extracted_value": "FIELD_A", "note": None},
        "class_type": {"status": "pass", "extracted_value": "FIELD_B", "note": None},
        "alcohol_content": {"status": "pass", "extracted_value": "FIELD_C", "note": None},
        "net_contents": {"status": "pass", "extracted_value": "FIELD_D", "note": None},
        "bottler_info": {"status": "pass", "extracted_value": "FIELD_E", "note": None},
        "country_of_origin": {"status": "pass", "extracted_value": "FIELD_F", "note": None},
        "government_warning": {
            "status": "pass",
            "extracted_value": CANONICAL_GOVERNMENT_WARNING,
            "note": None,
        },
    })

    result = parse_verification_response(llm_response, application_data)

    assert result.brand_name.expected_value == "FIELD_A"
    assert result.class_type.expected_value == "FIELD_B"
    assert result.alcohol_content.expected_value == "FIELD_C"
    assert result.net_contents.expected_value == "FIELD_D"
    assert result.bottler_info.expected_value == "FIELD_E"
    assert result.country_of_origin.expected_value == "FIELD_F"
    assert result.government_warning.expected_value == CANONICAL_GOVERNMENT_WARNING


def test_expected_value_alignment_holds_even_when_llm_returns_fields_out_of_order():
    """Same guarantee, but the LLM's JSON has its keys in a shuffled order —
    dict key order must never affect which expected_value pairs with which field.
    """
    application_data = ApplicationData(
        brand_name="FIELD_A",
        class_type="FIELD_B",
        alcohol_content="FIELD_C",
        net_contents="FIELD_D",
        bottler_info="FIELD_E",
        country_of_origin="FIELD_F",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )

    # Deliberately out of the field_names order used inside parse_verification_response.
    llm_response = json.dumps({
        "country_of_origin": {"status": "pass", "extracted_value": "FIELD_F", "note": None},
        "net_contents": {"status": "pass", "extracted_value": "FIELD_D", "note": None},
        "brand_name": {"status": "pass", "extracted_value": "FIELD_A", "note": None},
        "government_warning": {
            "status": "pass",
            "extracted_value": CANONICAL_GOVERNMENT_WARNING,
            "note": None,
        },
        "bottler_info": {"status": "pass", "extracted_value": "FIELD_E", "note": None},
        "alcohol_content": {"status": "pass", "extracted_value": "FIELD_C", "note": None},
        "class_type": {"status": "pass", "extracted_value": "FIELD_B", "note": None},
    })

    result = parse_verification_response(llm_response, application_data)

    assert result.brand_name.expected_value == "FIELD_A"
    assert result.class_type.expected_value == "FIELD_B"
    assert result.alcohol_content.expected_value == "FIELD_C"
    assert result.net_contents.expected_value == "FIELD_D"
    assert result.bottler_info.expected_value == "FIELD_E"
    assert result.country_of_origin.expected_value == "FIELD_F"


def _application_data() -> ApplicationData:
    return ApplicationData(
        brand_name="Stone's Throw",
        class_type="American Whiskey",
        alcohol_content="40% alc/vol",
        net_contents="750 mL",
        bottler_info="Stone's Throw Distillery",
        country_of_origin="USA",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )


def _response_with_gw(gw_extra: dict) -> str:
    base_field = {"status": "pass", "extracted_value": "x", "note": None}
    return json.dumps({
        "brand_name": base_field,
        "class_type": base_field,
        "alcohol_content": base_field,
        "net_contents": base_field,
        "bottler_info": base_field,
        "country_of_origin": base_field,
        "government_warning": {
            "status": "pass",
            "extracted_value": CANONICAL_GOVERNMENT_WARNING,
            "note": None,
            **gw_extra,
        },
    })


def test_prefix_bold_parsed_from_government_warning_field():
    result = parse_verification_response(
        _response_with_gw({"prefix_bold": "no"}), _application_data()
    )
    assert result.government_warning.prefix_bold == "no"


def test_prefix_bold_defaults_to_uncertain_when_missing():
    result = parse_verification_response(_response_with_gw({}), _application_data())
    assert result.government_warning.prefix_bold == "uncertain"


def test_prefix_bold_defaults_to_uncertain_when_invalid():
    result = parse_verification_response(
        _response_with_gw({"prefix_bold": "definitely-bold"}), _application_data()
    )
    assert result.government_warning.prefix_bold == "uncertain"


def test_prefix_bold_only_attached_to_government_warning_field():
    result = parse_verification_response(
        _response_with_gw({"prefix_bold": "yes"}), _application_data()
    )
    assert result.brand_name.prefix_bold is None
    assert result.class_type.prefix_bold is None
