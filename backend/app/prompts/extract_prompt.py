import json
import logging

from app.models import ExtractedApplicationData

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """\
You are a TTB (Alcohol and Tobacco Tax and Trade Bureau) label compliance specialist.
Examine the alcohol label image and extract the following 7 fields, reading only what
is actually printed on the label. Do not guess, infer, or fill in typical/expected
values for a label like this — if a field is not legible or not present, return null
for it.

FIELDS TO EXTRACT:
- brand_name: the brand name
- class_type: the class/type designation (e.g. "American Whiskey")
- alcohol_content: alcohol by volume (e.g. "40% ALC/VOL")
- net_contents: net contents (e.g. "750 mL")
- bottler_info: name and address of bottler/importer
- country_of_origin: country of origin
- government_warning: the full government warning text, transcribed EXACTLY as
  printed, character for character — do not paraphrase, correct, or normalize it.

Respond with ONLY valid JSON — no markdown fences, no preamble, no explanation
outside the JSON. Use this exact schema:

{
  "brand_name": "<text read from the label, or null if not legible/present>",
  "class_type": "<...or null>",
  "alcohol_content": "<...or null>",
  "net_contents": "<...or null>",
  "bottler_info": "<...or null>",
  "country_of_origin": "<...or null>",
  "government_warning": "<...or null>"
}
"""

_FIELD_NAMES = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_info",
    "country_of_origin",
    "government_warning",
]


def build_extract_prompt() -> str:
    return _EXTRACT_PROMPT


def parse_extraction_response(raw: str) -> ExtractedApplicationData:
    """Parse the model's JSON response into ExtractedApplicationData.

    Any parsing failure or non-string/blank value degrades to null for that
    field rather than raising — extraction is a best-effort accelerator, so a
    partially- or un-populated form is an acceptable fallback.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(f"Extract: model returned unparseable response: {exc}")
        return ExtractedApplicationData()

    values = {}
    for name in _FIELD_NAMES:
        val = data.get(name)
        values[name] = val if isinstance(val, str) and val.strip() else None

    return ExtractedApplicationData(**values)
