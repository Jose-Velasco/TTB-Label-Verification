"""Generate visual reference images for manual review of image-degradation severity.

Standalone script, separate from the pytest eval suite. tests/eval/test_golden_samples.py
only asserts pass/fail programmatically on degraded images — it never lets a human
actually look at what was sent to the model. This script rasterizes the PASS sample
label and saves every degradation variant (at mild/default/severe levels) to disk as
real PNG/JPEG files, so a human can eyeball each one and sanity-check whether it's
reasonable to expect that severity level to fail an image-quality check, and whether
the "default" level used by the eval suite is roughly at the boundary of readability,
too mild, or too severe.

Run with:
    uv run python scripts/generate_degraded_previews.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.eval._golden_data import load_golden_samples, rasterize_sample_svg
from tests.eval.image_degradation import (
    apply_gaussian_blur,
    apply_glare_overlay,
    apply_jpeg_compression_artifacts,
    apply_low_contrast,
    apply_rotation,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "degraded_previews"

# (filename stem, file extension, degrade function, kwarg name, {severity: value})
# "default" values match the parameter defaults used by tests/eval/test_golden_samples.py.
DEGRADATION_SPECS = [
    ("01_gaussian_blur", "png", apply_gaussian_blur, "radius",
     {"mild": 4.0, "default": 8.0, "severe": 14.0}),
    ("02_low_contrast", "png", apply_low_contrast, "factor",
     {"mild": 0.6, "default": 0.3, "severe": 0.12}),
    ("03_rotation", "png", apply_rotation, "degrees",
     {"mild": 6.0, "default": 15.0, "severe": 30.0}),
    ("04_jpeg_compression", "jpg", apply_jpeg_compression_artifacts, "quality",
     {"mild": 40, "default": 15, "severe": 5}),
    ("05_glare_overlay", "png", apply_glare_overlay, "opacity",
     {"mild": 0.2, "default": 0.4, "severe": 0.65}),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    samples = load_golden_samples()
    pass_sample = next(s for s in samples if s["id"] == "01")
    original_png = rasterize_sample_svg(pass_sample["filename"])

    # (filename, degradation type, param name, param value, size in bytes)
    generated: list[tuple[str, str, str, object, int]] = []

    original_path = OUTPUT_DIR / "00_original.png"
    original_path.write_bytes(original_png)
    generated.append(("00_original.png", "none", "-", "-", original_path.stat().st_size))

    for stem, ext, degrade_fn, param_name, severities in DEGRADATION_SPECS:
        degradation_type = stem.split("_", 1)[1]
        for severity_label, param_value in severities.items():
            variant_bytes = degrade_fn(original_png, **{param_name: param_value})
            filename = f"{stem}_{severity_label}.{ext}"
            out_path = OUTPUT_DIR / filename
            out_path.write_bytes(variant_bytes)
            generated.append(
                (filename, degradation_type, param_name, param_value, out_path.stat().st_size)
            )

    print(f"Generated {len(generated)} files in {OUTPUT_DIR}\n")
    header = f"{'filename':<32} {'degradation':<16} {'param':<10} {'value':<8} {'size':>10}"
    print(header)
    print("-" * len(header))
    for filename, degradation_type, param_name, param_value, size_bytes in generated:
        print(
            f"{filename:<32} {degradation_type:<16} {param_name:<10} "
            f"{str(param_value):<8} {size_bytes:>9,}B"
        )


if __name__ == "__main__":
    main()
