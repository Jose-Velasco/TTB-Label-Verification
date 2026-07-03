"""Golden-sample evaluation suite — exercises the real LiteLLMVisionAdapter.

Opt-in only (pytest.ini marker `eval`): these tests make real vision-model calls
against whatever provider is configured in the environment (Ollama or Gemini).
They are slow and non-deterministic compared to the mocked unit tests in
tests/test_adapters.py, so they are excluded from the default `pytest tests/`
invocation and must be run explicitly with `-m eval`.

Run with:
    uv run pytest tests/ -v -m eval
"""

import base64
import copy

import pytest

from app.models import ApplicationData, FieldStatus, OverallStatus
from tests.eval import image_degradation as degrade
from tests.eval._golden_data import load_golden_samples

pytestmark = pytest.mark.eval

GOLDEN_SAMPLES = load_golden_samples()
SAMPLE_BY_ID = {s["id"]: s for s in GOLDEN_SAMPLES}
PASS_SAMPLE = SAMPLE_BY_ID["01"]

FIELD_NAMES = list(ApplicationData.model_fields)

# Expected overall_status per sample, keyed by filename (minus .svg) — the
# filenames themselves encode the expected outcome, per the README's sample table.
EXPECTED_OVERALL_STATUS = {
    "01_stones_throw_pass": OverallStatus.approved,
    "02_missing_warning_fail": OverallStatus.rejected,
    "03_title_case_warning_fail": OverallStatus.rejected,
}

# (label, degrade_fn, output_mime) — jpeg compression re-encodes as JPEG, the
# rest stay PNG, so the mime sent to the model must track the actual bytes.
DEGRADATIONS = [
    ("gaussian_blur", degrade.apply_gaussian_blur, "image/png"),
    ("low_contrast", degrade.apply_low_contrast, "image/png"),
    ("rotation", degrade.apply_rotation, "image/png"),
    ("jpeg_compression", degrade.apply_jpeg_compression_artifacts, "image/jpeg"),
    ("glare_overlay", degrade.apply_glare_overlay, "image/png"),
]


def _b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


@pytest.mark.parametrize(
    "sample", GOLDEN_SAMPLES, ids=[s["filename"] for s in GOLDEN_SAMPLES]
)
async def test_sample_matches_expected_outcome(sample, rasterize_sample, vision_adapter):
    png_bytes = rasterize_sample(sample["filename"])
    application_data = ApplicationData(**sample["application_data"])

    result = await vision_adapter.verify_label(_b64(png_bytes), "image/png", application_data)

    outcome_key = sample["filename"].removesuffix(".svg")
    expected = EXPECTED_OVERALL_STATUS[outcome_key]
    field_statuses = {name: getattr(result, name).status for name in FIELD_NAMES}
    assert result.overall_status == expected, (
        f"{sample['filename']}: expected overall_status={expected}, "
        f"got {result.overall_status}. Field statuses: {field_statuses}"
    )

    if sample["id"] == "03":
        assert result.government_warning.status == FieldStatus.fail, (
            "Title-case government warning should be rejected by the backend's "
            f"exact-match check. Got: {result.government_warning}"
        )


async def test_mismatched_application_data_fails(rasterize_sample, vision_adapter):
    """Regression test: the model must not rubber-stamp application data it
    never actually verified against the image.

    Takes the PASS sample image but corrupts brand_name to a different, equally
    realistic value before sending it. If the model still returns "pass" for
    brand_name, the fuzzy-matching instructions in verify_prompt.py are too
    lenient and are accepting expected_value uncritically instead of reading it
    off the image.
    """
    png_bytes = rasterize_sample(PASS_SAMPLE["filename"])

    corrupted_data = copy.deepcopy(PASS_SAMPLE["application_data"])
    corrupted_data["brand_name"] = "River Bend"
    application_data = ApplicationData(**corrupted_data)

    result = await vision_adapter.verify_label(_b64(png_bytes), "image/png", application_data)

    assert result.brand_name.status == FieldStatus.fail, (
        "Model accepted a brand_name ('River Bend') that does not match the "
        f"label image (actual label says 'Stone's Throw'). Got: {result.brand_name}. "
        "This means the fuzzy-matching prompt needs tightening — it should never "
        "pass a field it didn't actually verify against the image."
    )


@pytest.mark.parametrize(
    "degradation_name, degrade_fn, output_mime",
    DEGRADATIONS,
    ids=[d[0] for d in DEGRADATIONS],
)
async def test_degraded_image_returns_unreadable_or_needs_review(
    degradation_name, degrade_fn, output_mime, rasterize_sample, vision_adapter
):
    """The app should degrade gracefully on poor image quality rather than
    confidently hallucinating a pass — assert needs_review overall, or at least
    one field flagged unreadable/warning, for a degraded but otherwise-correct
    PASS-sample image + correct application data.
    """
    png_bytes = rasterize_sample(PASS_SAMPLE["filename"])
    degraded_bytes = degrade_fn(png_bytes)
    application_data = ApplicationData(**PASS_SAMPLE["application_data"])

    result = await vision_adapter.verify_label(_b64(degraded_bytes), output_mime, application_data)

    field_statuses = {name: getattr(result, name).status for name in FIELD_NAMES}
    degraded_gracefully = result.overall_status == OverallStatus.needs_review or any(
        status in (FieldStatus.unreadable, FieldStatus.warning)
        for status in field_statuses.values()
    )
    assert degraded_gracefully, (
        f"{degradation_name}: model did not flag degraded image quality. "
        f"overall_status={result.overall_status}, field statuses: {field_statuses}"
    )
