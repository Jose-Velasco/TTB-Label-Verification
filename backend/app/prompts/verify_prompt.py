import json
import logging

from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import (
    ApplicationData,
    FieldResult,
    FieldStatus,
    OverallStatus,
    VerificationResult,
)

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a TTB (Alcohol and Tobacco Tax and Trade Bureau) label compliance specialist.
Examine the alcohol label image, extract the required fields, and compare each against
the expected application data provided.

EXPECTED APPLICATION DATA:
- Brand Name: {brand_name}
- Class/Type: {class_type}
- Alcohol Content: {alcohol_content}
- Net Contents: {net_contents}
- Bottler Info: {bottler_info}
- Country of Origin: {country_of_origin}
- Government Warning: {government_warning}

There are two groups of fields, and they are handled DIFFERENTLY:

  GROUP A - COMPARISON FIELDS: brand_name, class_type, alcohol_content,
  net_contents, bottler_info, country_of_origin. Judge these by MEANING: does
  the label carry the same real-world information as expected, regardless of
  formatting? Follow instructions 1-6.

  GROUP B - GOVERNMENT WARNING: government_warning is judged on VERBATIM
  TRANSCRIPTION, not meaning. The backend does an exact-character string match
  against the canonical legal text, so your only job is to transcribe exactly
  what is printed. Follow instruction 7. Do NOT apply the Group A confidence or
  comparison logic to it.

--- GROUP A: COMPARISON FIELDS (instructions 1-6) ---

1. READING CONFIDENCE. Before extracting a field, decide whether you are
   actually reading the characters off the image, or guessing what a label like
   this usually says. Ask: "Could I confidently re-type every character from
   what I can see, or am I filling in gaps?" If you are inferring rather than
   reading, that field is NOT a "pass" candidate (see instruction 4).

   This check is about how well you can READ text that is PRESENT. It is NOT
   about whether the field exists. If a field is simply absent from the label,
   that is a "fail" (instruction 5), NOT "unreadable." Use "unreadable" only
   when the text IS on the label but you cannot make out its characters.

   Worked examples:
   - Blur makes letter shapes ambiguous (e.g. "S" vs "5") -> "unreadable" or
     "warning", even if you have a plausible guess.
   - Glare/reflection obscures part of the text -> "unreadable" or "warning"
     for the affected field.
   - Rotation/skew cuts off or distorts text at the edges -> flag accordingly.
   - The field is clearly not printed on the label at all -> "fail" (absent),
     NOT "unreadable."
   - Image is sharp and every character is distinguishable -> read normally,
     no quality concern.

2. EXTRACT the exact text visible on the label — but only report values you
   actually read with confidence, per instruction 1.

3. COMPARE the extracted text against the expected value for the SAME field
   before choosing a status. A legible reading is not the same as a match.
   Restate both values and ask: "Same real-world information, just written or
   formatted differently, or ACTUALLY DIFFERENT information?"
   - Same information, formatting differences only (capitalization, spacing,
     punctuation, abbreviations, unit notation) -> "pass".
   - Actually different information (different brand, quantity, class/type,
     address, or any substantive discrepancy) -> "fail", even if perfectly
     legible.

4. CONFIDENCE OVERRIDES MATCH. If you are not confident in the reading (blur,
   glare, low contrast, skew, compression, or any image-quality issue), use
   "unreadable" (cannot make out the text) or "warning" (can read it but not
   fully confident). This OVERRIDES instruction 3: even if your best guess
   would match the expected value, do not report "pass" for a reading you are
   not confident you got right.

   Worked examples of comparison:
   - Expected "750ml", extracted "750 mL" -> same quantity -> "pass".
   - Expected "1 L", extracted "750 mL" -> different quantities -> "fail".
   - Expected "Bourbon Whiskey", extracted "Stone's Throw" -> unrelated values
     (a brand name where a class/type was expected) -> "fail".

5. ABSENT FIELD. If a field is completely absent from the label, status is
   "fail".

6. MINOR AMBIGUITY. For a small OCR-level ambiguity that is not a full content
   mismatch, status is "warning".

--- GROUP B: GOVERNMENT WARNING (instruction 7) ---

7. Transcribe the government warning EXACTLY as printed, character for
   character. The backend compares your transcription to the canonical legal
   text with an exact string match, so:
   - Do NOT paraphrase, summarize, correct apparent typos, normalize
     capitalization/punctuation, or "clean up" the wording. Transcribe the
     literal text, even if it looks unusual.
   - Judge status ONLY on whether you can physically READ the characters, NOT
     on whether you think your transcription is perfectly verbatim:
       * If the warning is clearly legible, status "pass" and give your best
         verbatim transcription. Do NOT downgrade a clear, readable warning to
         "warning" or "unreadable" out of doubt about whether it is 100%
         character-perfect — a legible read is always "pass" here.
       * Use "unreadable" only if you genuinely cannot make out the characters
         (severe blur, glare, or compression), with extracted_value null.
       * Use "warning" if part of the text is legible and part is not;
         transcribe the legible part and note which portion is uncertain.
   - Do not invent or assume standard wording you cannot actually see.

Respond with ONLY valid JSON — no markdown fences, no preamble, no explanation
outside the JSON. Use this exact schema. Fill in "reasoning" for every field
BEFORE deciding its status. For Group A fields, restate your reading confidence,
the expected and extracted values, and whether they are the same information
formatted differently or actually different. For government_warning, state your
confidence in reading the characters.

{{
  "brand_name": {{
    "reasoning": "<reading confidence; expected: ...; extracted: ...; same info differently formatted, or actually different, and why>",
    "status": "pass" | "fail" | "warning" | "unreadable",
    "extracted_value": "<text from label, or null if unreadable>",
    "note": "<optional explanation for non-pass status>"
  }},
  "class_type": {{ ... }},
  "alcohol_content": {{ ... }},
  "net_contents": {{ ... }},
  "bottler_info": {{ ... }},
  "country_of_origin": {{ ... }},
  "government_warning": {{
    "reasoning": "<confidence in reading the characters of the full warning text>",
    "status": "pass" | "fail" | "warning" | "unreadable",
    "extracted_value": "<full government warning text exactly as printed, or null if unreadable>",
    "note": "<optional explanation for non-pass status>"
  }}
}}
"""

# _PROMPT_TEMPLATE = """\
# You are a TTB (Alcohol and Tobacco Tax and Trade Bureau) label compliance specialist.
# Examine the alcohol label image and extract the following fields, then compare each
# against the expected application data provided.

# EXPECTED APPLICATION DATA:
# - Brand Name: {brand_name}
# - Class/Type: {class_type}
# - Alcohol Content: {alcohol_content}
# - Net Contents: {net_contents}
# - Bottler Info: {bottler_info}
# - Country of Origin: {country_of_origin}
# - Government Warning: {government_warning}

# INSTRUCTIONS:

# 1. FIRST, before extracting any field, assess the overall image quality. Ask
#    yourself: "Could I confidently re-type every character of this label from
#    what I can see, or am I filling in gaps with my best guess based on what a
#    label like this usually says?" If you are inferring likely text rather
#    than actually reading it, that field is NOT a "pass" candidate — see
#    instruction 5 below. This applies regardless of how legible the extracted
#    text LOOKS in your response; the question is whether you were confident
#    reading it off the actual image pixels, not whether your answer sounds
#    plausible.

#    Worked examples of this quality check:
#    - The image is blurry enough that letter shapes are ambiguous (e.g. you
#      cannot tell if a character is "S" or "5") -> mark that field "unreadable"
#      or "warning", even if you have a plausible guess.
#    - Glare or a bright reflection obscures part of the text -> mark the
#      affected field "unreadable" or "warning" for the obscured portion, even
#      if surrounding text is clear.
#    - The image is rotated or skewed such that some text is cut off or
#      distorted at the edges -> mark affected fields accordingly.
#    - Heavy compression artifacts make small text blocky or illegible (this
#      especially affects the government warning, which is usually printed in
#      small font) -> mark "unreadable" or "warning" rather than guessing at
#      the standard wording.
#    - The image is sharp, well-lit, and every character is clearly
#      distinguishable -> proceed normally, no quality concern.

# 2. For each field, extract the exact text visible on the label — but only
#    report values you actually read with confidence, per instruction 1.

# 3. You MUST explicitly compare the EXTRACTED text against the EXPECTED value
#    for that SAME field before choosing a status. Never assign "pass" just
#    because you successfully read some text off the label — a legible reading
#    is not the same as a match. For every field, restate both values to
#    yourself and ask: "Is this the SAME real-world information, just written
#    or formatted differently, or is it ACTUALLY DIFFERENT information?"
#    - Same information, different formatting only (capitalization, spacing,
#      punctuation, abbreviations, unit notation) -> status "pass".
#    - Actually different information (different brand, different quantity,
#      different class/type, different address, or any other substantive
#      discrepancy) -> status "fail", even if the extracted text is perfectly
#      legible.

# 4. Worked examples of this comparison:
#    - Expected "750ml", extracted "750 mL" -> the SAME quantity, just written
#      differently -> status "pass".
#    - Expected "1 L", extracted "750 mL" -> DIFFERENT quantities (1 liter is
#      not 750 milliliters) -> status "fail", not "pass".
#    - Expected "Bourbon Whiskey", extracted "Stone's Throw" -> completely
#      unrelated values (a class/type expectation compared against what is
#      clearly a brand name, not a class/type) -> status "fail".

# 5. If you are not highly confident in a reading — per the quality check in
#    instruction 1, due to blur, glare, low contrast, a crooked angle, heavy
#    compression, or any other image-quality issue — use "unreadable" (you
#    cannot make out the text at all) or "warning" (you can make out the text
#    but are not fully confident it's accurate). This rule OVERRIDES instruction
#    3: even if your best-guess reading would match the expected value, if you
#    are not confident you actually read it correctly, do not report "pass".
#    Never report "pass" for a field you are uncertain about just because your
#    best guess happens to resemble the expected value.

# 6. If a field is completely absent from the label, set status to "fail".

# 7. If there is a minor discrepancy that is not a full content mismatch (e.g. a
#    small OCR-level ambiguity), set status to "warning".

# 8. The government_warning field is handled separately by the backend for the
#    MATCH decision, but you must still apply the quality check in instruction 1
#    to it — if you cannot confidently read the full warning text (e.g. due to
#    small font size combined with blur/compression), extract what you can and
#    note your uncertainty; do not fabricate or assume standard wording you
#    cannot actually see. Give it status "pass" only if you are confident in
#    your reading; otherwise use "unreadable" or "warning" — the backend applies
#    exact-match validation on top of whatever you extract, but a low-confidence
#    guess should not be silently passed through as "pass".

# 9. Do NOT apply exact-match logic yourself for any field except government_warning's
#    final match decision (the backend handles that comparison separately) — but
#    DO apply the quality/confidence check from instruction 1 to every field,
#    including government_warning.

# Respond with ONLY valid JSON — no markdown fences, no preamble, no explanation
# outside the JSON. Use this exact schema. Fill in "reasoning" for every field
# BEFORE deciding its status — restate the expected and extracted values for
# that field, note your confidence in the reading per instruction 1, and state
# whether they are the same information differently formatted, or actually
# different information, per instruction 3 above:

# {{
#   "brand_name": {{
#     "reasoning": "<confidence in reading: ...; expected: ...; extracted: ...; same information differently formatted, or actually different information, and why>",
#     "status": "pass" | "fail" | "warning" | "unreadable",
#     "extracted_value": "<text from label or null if unreadable>",
#     "note": "<optional explanation for non-pass status>"
#   }},
#   "class_type": {{ ... }},
#   "alcohol_content": {{ ... }},
#   "net_contents": {{ ... }},
#   "bottler_info": {{ ... }},
#   "country_of_origin": {{ ... }},
#   "government_warning": {{
#     "reasoning": "<confidence in reading the full warning text>",
#     "status": "pass" | "fail" | "warning" | "unreadable",
#     "extracted_value": "<full government warning text as it appears on the label, or null if unreadable>",
#     "note": "<optional explanation for non-pass status>"
#   }}
# }}
# """


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
        # Only applies when the model actually extracted text; a null extraction
        # (whether the model called it "unreadable", "warning", or anything else)
        # must never be exact-matched against None, and always surfaces as unreadable.
        gw_field = fields["government_warning"]
        if gw_field.extracted_value is not None:
            gw_result = _validate_gw(gw_field.extracted_value)
            fields["government_warning"] = FieldResult(
                status=gw_result.status,
                extracted_value=gw_field.extracted_value,
                expected_value=application_data.government_warning,
                note=gw_result.note,
            )
        elif gw_field.status != FieldStatus.unreadable:
            fields["government_warning"] = FieldResult(
                status=FieldStatus.unreadable,
                extracted_value=None,
                expected_value=application_data.government_warning,
                note=gw_field.note
                or "Model did not extract any government warning text.",
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
