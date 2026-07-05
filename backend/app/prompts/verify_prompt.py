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
   actually read with confidence, per instruction 1. Determine extracted_value
   from the IMAGE ONLY, before you consult or restate the expected value for
   that field. Extraction and comparison are separate steps done in that order.

2b. NEVER ANCHOR ON THE EXPECTED VALUE. extracted_value must never be a copy
   of the expected value unless the label's printed text is genuinely,
   verbatim identical to it. If you notice yourself about to write the
   expected value as extracted_value, stop: re-examine the image region for
   that field and either transcribe the real printed characters, or — if you
   cannot actually read them — use null with status "unreadable"/"warning".
   Silently substituting the expected value because the reading is unclear is
   a critical error, not a safe default.

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

4b. SELF-CONSISTENCY CHECK. Before finalizing each field, verify that
   extracted_value, status, and note/reasoning do not contradict each other
   IN EITHER DIRECTION:
   - If note or reasoning says you could not determine, read, or make out the
     value -> status MUST be "unreadable" or "warning", NEVER "pass", and
     extracted_value MUST be null, NEVER the expected value or any other text.
   - If status is "unreadable" -> extracted_value MUST be null, AND your
     reasoning must not state or imply that you actually read specific text
     off the label. If your reasoning describes what the label says (e.g.
     "the label reads 40% ALC/VOL" or "the label reads 750 mL"), you have
     contradicted "unreadable" — the correct status is determined by comparing
     that reading to the expected value (instruction 3), NOT "unreadable".
     "Unreadable" means you could not read ANY meaningful text for that field,
     full stop — it is never a valid status alongside reasoning that quotes or
     paraphrases what the label says.
   - A separate, common trap: do NOT use "unreadable" (or a null
     extracted_value) to mean "I read the label fine, but the expected value
     looks like a placeholder, typo, or unlikely value, so I can't judge a
     match." That is NOT what "unreadable" means. If you read real text off the
     label, extracted_value MUST contain that real text and status MUST come
     from the comparison logic in instructions 3-4, even if the expected value
     looks implausible, garbled, or clearly wrong. A clearly-read label field
     against an implausible or placeholder expected value is a "fail" (the
     information does not match), NOT "unreadable" and NOT "pass". The quality
     of the expected value never changes whether the LABEL was readable.
   - If status is "pass" -> extracted_value MUST be a real, non-null reading
     you actually took from the image, not null and not an unexplained copy
     of the expected value.
   A field whose reasoning and status/extracted_value disagree in either
   direction is a critical error — reread the image or correct the field
   before responding, don't leave the contradiction in your output.

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

8. BOLD CHECK. Separately judge whether the literal "GOVERNMENT WARNING:"
   prefix is printed in BOLD - visibly heavier stroke weight than the
   surrounding warning text.
     - clearly heavier strokes -> "yes"
     - clearly same weight     -> "no"
     - can't tell / warning unreadable -> "uncertain"

Respond with ONLY valid JSON — no markdown fences, no preamble, no explanation
outside the JSON. Use this exact schema, and fill each field's keys IN THE
ORDER SHOWN — "extracted_value" MUST be written first, decided from the image
alone, before "reasoning" ever mentions the expected value (per instructions 2
and 2b). Do not go back and change extracted_value after writing the
comparison — if the comparison reveals you actually guessed, fix that by
setting extracted_value to null and status to "unreadable"/"warning", not by
leaving a copied expected value in place. Keep "reasoning" to ONE short
clause (under ~12 words) stating the verdict, not a restatement of both
values — e.g. "matches, formatting only", "different quantity", "text
blurred, can't confirm". For government_warning, a short confidence note is
enough (e.g. "clearly legible").

{{
  "brand_name": {{
    "extracted_value": "<text read from the label image ONLY, decided before you look at the expected value; null if unreadable>",
    "reasoning": "<one short clause: verdict only, e.g. 'matches, formatting only' or 'different brand'>",
    "status": "pass" | "fail" | "warning" | "unreadable",
    "note": "<optional explanation for non-pass status>"
  }},
  "class_type": {{ ... }},
  "alcohol_content": {{ ... }},
  "net_contents": {{ ... }},
  "bottler_info": {{ ... }},
  "country_of_origin": {{ ... }},
  "government_warning": {{
    "extracted_value": "<full government warning text exactly as printed, decided before comparing; null if unreadable>",
    "reasoning": "<one short clause: reading confidence only, e.g. 'clearly legible'>",
    "status": "pass" | "fail" | "warning" | "unreadable",
    "note": "<optional explanation for non-pass status>",
    "prefix_bold": "yes" | "no" | "uncertain"
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


def _make_skipped_result(filename: str | None, reason: str) -> VerificationResult:
    """Result for a batch image with no matching application data.

    Distinct from _make_needs_review_result: that one represents a model/
    parsing failure after an actual vision call; this one is a data-entry
    gap caught before any call is made, so there's no application data to
    populate expected_value with (left blank rather than guessed).
    """
    placeholder = FieldResult(
        status=FieldStatus.unreadable,
        extracted_value=None,
        expected_value="",
        note=reason,
    )
    return VerificationResult(
        overall_status=OverallStatus.needs_review,
        brand_name=placeholder,
        class_type=placeholder,
        alcohol_content=placeholder,
        net_contents=placeholder,
        bottler_info=placeholder,
        country_of_origin=placeholder,
        government_warning=placeholder,
        image_quality_note=reason,
        filename=filename,
        skipped=True,
    )


def _parse_prefix_bold(gw_raw: dict) -> str:
    """Normalize the model's government_warning.prefix_bold value — a soft
    signal (see VerificationResult.computed_overall_status), so anything
    missing or unrecognized falls back to "uncertain" (no penalty) rather
    than being treated as a hard failure to parse.
    """
    value = gw_raw.get("prefix_bold")
    return value if value in ("yes", "no", "uncertain") else "uncertain"


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

        prefix_bold = _parse_prefix_bold(data.get("government_warning", {}))

        for name in field_names:
            fd = data.get(name, {})
            status_raw = fd.get("status", "unreadable")
            try:
                status = FieldStatus(status_raw)
            except ValueError:
                status = FieldStatus.unreadable

            # "unreadable" is defined (per the prompt schema) as "no text was
            # confidently read" — enforce that invariant here rather than trust
            # the model to leave extracted_value null on its own, since a model
            # occasionally fills it in anyway despite marking the field unreadable.
            extracted_value = fd.get("extracted_value")
            if status == FieldStatus.unreadable:
                extracted_value = None

            fields[name] = FieldResult(
                status=status,
                extracted_value=extracted_value,
                expected_value=expected_map[name],
                note=fd.get("note"),
                prefix_bold=prefix_bold if name == "government_warning" else None,
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
                prefix_bold=prefix_bold,
            )
        elif gw_field.status != FieldStatus.unreadable:
            fields["government_warning"] = FieldResult(
                status=FieldStatus.unreadable,
                extracted_value=None,
                expected_value=application_data.government_warning,
                note=gw_field.note
                or "Model did not extract any government warning text.",
                prefix_bold=prefix_bold,
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
