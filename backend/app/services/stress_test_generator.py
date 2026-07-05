"""Generates synthetic stress-test batches in memory.

Reuses the exact sample-corruption logic originally written for
scripts/generate_batch_stress_test.py (that script now imports
generate_stress_test_batch from here instead of reimplementing it — see its
docstring for the manual CSV-import-testing use case it's still used for).

Unlike the CLI script, this never touches disk: it returns PNG bytes and
per-image application data straight in memory, so a request handler can feed
the result directly into VerificationService.verify_batch without a round
trip through file upload or CSV serialization.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.services.golden_samples import load_golden_samples, rasterize_sample_svg

FIELD_NAMES = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_info",
    "country_of_origin",
    "government_warning",
]

# Fields eligible for "wrong value" / "missing value" corruption.
# government_warning is excluded: verification always checks the *extracted*
# label text against the canonical constant (app/constants.py's
# CANONICAL_GOVERNMENT_WARNING), never against the supplied application data,
# so corrupting or blanking it here wouldn't exercise any comparison logic.
CORRUPTIBLE_FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_info",
    "country_of_origin",
]

# Small hand-written pools of realistic alternate values per field — real
# brand/ABV/net-contents look-alikes, not keyboard-mash placeholders, so a
# "wrong field" row exercises the same meaning-comparison the vision model
# actually performs.
ALTERNATE_VALUES = {
    "brand_name": ["River Bend", "Blue Ridge", "Copperline", "Old Harbor"],
    "class_type": [
        "Bourbon Whiskey",
        "Tennessee Whiskey",
        "American Whiskey",
        "Rye Whiskey",
        "Blended Whiskey",
    ],
    "alcohol_content": ["40% ALC/VOL", "43% ALC/VOL", "45% ALC/VOL", "50% ALC/VOL"],
    "net_contents": ["750 mL", "1 L", "375 mL", "1.75 L"],
    "bottler_info": [
        "River Bend Spirits LLC, Nashville TN 37201",
        "Blue Ridge Distilling Co., Knoxville TN 37902",
        "Copperline Distillers, Louisville KY 40202",
        "Old Harbor Spirits Co., Portland ME 04101",
    ],
    "country_of_origin": ["Canada", "Scotland", "Ireland", "Mexico"],
}

# Weights for the three per-row data buckets.
BUCKET_WEIGHTS = {"correct": 0.50, "wrong_field": 0.35, "missing_field": 0.15}

# A small fixed number of generated images are deliberately left out of the
# returned application-data map, so a generated batch also exercises
# VerificationService.verify_batch's no-matching-filename "skipped" path, not
# just real verification outcomes.
NUM_UNMATCHED_IMAGES = 2


def pick_alternate(field_name: str, true_value: str, rng: random.Random) -> str:
    pool = [v for v in ALTERNATE_VALUES[field_name] if v != true_value]
    return rng.choice(pool)


def build_row(sample: dict, bucket: str, rng: random.Random) -> tuple[dict, str | None]:
    """Return (application-data fields, corrupted-field name or None)."""
    true_data = sample["application_data"]
    fields = dict(true_data)

    if bucket == "correct":
        return fields, None

    target_field = rng.choice(CORRUPTIBLE_FIELDS)
    if bucket == "wrong_field":
        fields[target_field] = pick_alternate(target_field, true_data[target_field], rng)
    else:  # missing_field
        fields[target_field] = ""
    return fields, target_field


def expected_outcome(sample_id: str, bucket: str) -> str:
    """Human-readable prediction for scripts/generate_batch_stress_test.py's
    printed report.

    Assumes CSV-import semantics (a blank field excludes the row from the
    batch in the frontend's CSV table) — NOT accurate for callers that feed
    rows straight into VerificationService.verify_batch, where a blank field
    still gets verified (and will likely fail or need review) rather than
    being excluded. Only meaningful for the CLI script's CSV-import scenario.
    """
    if bucket == "missing_field":
        return "SKIPPED (incomplete row, excluded from run)"
    if sample_id != "01":
        return "REJECTED (image's own government warning is non-compliant)"
    if bucket == "wrong_field":
        return "REJECTED (field mismatch)"
    return "APPROVED"


@dataclass
class GeneratedMainRow:
    filename: str
    sample_id: str
    bucket: str
    corrupted_field: str | None
    application_data: dict[str, str]


@dataclass
class StressTestBatch:
    main_rows: list[GeneratedMainRow]
    unmatched_image_filenames: list[str]
    image_bytes: dict[str, bytes]  # filename -> PNG bytes, covers every generated image


def split_main_and_unmatched_counts(total_count: int) -> tuple[int, int]:
    """Split a requested total image count into (main_rows, unmatched_images).

    A small fixed number of images are deliberately excluded from the
    application-data map so a generated batch also exercises the
    no-matching-filename "skipped" path (see VerificationService.verify_batch),
    not just real verification outcomes.
    """
    unmatched = min(NUM_UNMATCHED_IMAGES, max(0, total_count - 1))
    return total_count - unmatched, unmatched


def generate_stress_test_batch(total_count: int, seed: int | None = None) -> StressTestBatch:
    """Generate `total_count` synthetic label images in memory: real golden
    label artwork rasterized to PNG, each paired with application data that's
    either an exact match, has one field corrupted to a wrong-but-plausible
    value, or has one field blanked — plus a couple of images with no
    application-data entry at all (see split_main_and_unmatched_counts).

    seed=None (the default) draws fresh randomness each call, so repeated
    "Generate & Run" clicks produce different batches; pass a fixed seed for
    reproducible output (as scripts/generate_batch_stress_test.py does).
    """
    rng = random.Random(seed)
    samples = load_golden_samples()

    raster_cache: dict[str, bytes] = {}

    def rasterize(filename: str) -> bytes:
        if filename not in raster_cache:
            raster_cache[filename] = rasterize_sample_svg(filename)
        return raster_cache[filename]

    main_count, unmatched_count = split_main_and_unmatched_counts(total_count)

    sample_sequence = [samples[i % len(samples)] for i in range(main_count)]
    rng.shuffle(sample_sequence)

    image_bytes: dict[str, bytes] = {}
    main_rows: list[GeneratedMainRow] = []

    idx = 0
    for sample in sample_sequence:
        idx += 1
        bucket = rng.choices(list(BUCKET_WEIGHTS), weights=list(BUCKET_WEIGHTS.values()))[0]
        filename = f"label_{idx:03d}.png"
        fields, corrupted_field = build_row(sample, bucket, rng)

        image_bytes[filename] = rasterize(sample["filename"])
        main_rows.append(
            GeneratedMainRow(
                filename=filename,
                sample_id=sample["id"],
                bucket=bucket,
                corrupted_field=corrupted_field,
                application_data=fields,
            )
        )

    unmatched_image_filenames: list[str] = []
    for _ in range(unmatched_count):
        idx += 1
        filename = f"label_{idx:03d}_unmatched.png"
        sample = rng.choice(samples)
        image_bytes[filename] = rasterize(sample["filename"])
        unmatched_image_filenames.append(filename)

    return StressTestBatch(
        main_rows=main_rows,
        unmatched_image_filenames=unmatched_image_filenames,
        image_bytes=image_bytes,
    )
