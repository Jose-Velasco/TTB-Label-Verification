"""Generate a folder of label images + a matching CSV for manually exercising
the batch page's CSV-import feature (correct rows, mismatched fields, missing
fields, unmatched images, unmatched CSV rows, duplicate filenames).

Standalone script, separate from the pytest eval suite. Reuses
tests/eval/_golden_data.py for SVG rasterization and the golden samples'
true field values instead of re-deriving either.

Samples 02 and 03 have a defect baked into the *image itself* (missing /
title-cased government warning), so they fail verification regardless of
what application data is supplied — only sample 01 is capable of an
"approved" result. That's factored into the expected-outcome summary below.

Run with:
    uv run python scripts/generate_batch_stress_test.py --count 10
"""

import argparse
import csv
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.eval._golden_data import load_golden_samples, rasterize_sample_svg

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "batch_stress_test"
IMAGES_DIR = OUTPUT_DIR / "images"
CSV_PATH = OUTPUT_DIR / "labels.csv"

FIELD_NAMES = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_info",
    "country_of_origin",
    "government_warning",
]

# Fields eligible for "wrong value" / "missing value" corruption. government_warning
# is excluded: the backend always checks the *extracted* text against the canonical
# constant (app/services/validation.py), never against the CSV-supplied value, so
# corrupting it wouldn't exercise any comparison logic and blanking it in the CSV is
# a no-op (the importer only overwrites a field when the CSV cell is non-empty, and
# the row already defaults government_warning to the canonical text).
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

NUM_UNMATCHED_IMAGES = 2  # images with no CSV row at all
NUM_UNMATCHED_ROWS = 2  # CSV rows with no matching image
NUM_DUPLICATE_ROWS = 1  # extra CSV row reusing an already-used filename


def pick_alternate(field: str, true_value: str, rng: random.Random) -> str:
    pool = [v for v in ALTERNATE_VALUES[field] if v != true_value]
    return rng.choice(pool)


def build_row(sample: dict, bucket: str, rng: random.Random) -> tuple[dict, str | None]:
    """Return (field values for the CSV row, corrupted-field name or None)."""
    true_data = sample["application_data"]
    fields = dict(true_data)

    if bucket == "correct":
        return fields, None

    target_field = rng.choice(CORRUPTIBLE_FIELDS)
    if bucket == "wrong_field":
        fields[target_field] = pick_alternate(
            target_field, true_data[target_field], rng
        )
    else:  # missing_field
        fields[target_field] = ""
    return fields, target_field


def expected_outcome(sample_id: str, bucket: str) -> str:
    if bucket == "missing_field":
        return "SKIPPED (incomplete row, excluded from run)"
    if sample_id != "01":
        return "REJECTED (image's own government warning is non-compliant)"
    if bucket == "wrong_field":
        return "REJECTED (field mismatch)"
    return "APPROVED"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=10, help="Number of main rows to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed for reproducible output"
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    samples = load_golden_samples()
    raster_cache: dict[str, bytes] = {}

    def rasterize(filename: str) -> bytes:
        if filename not in raster_cache:
            raster_cache[filename] = rasterize_sample_svg(filename)
        return raster_cache[filename]

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Roughly-even, shuffled assignment of the 3 samples across N main rows.
    sample_sequence = [samples[i % len(samples)] for i in range(args.count)]
    rng.shuffle(sample_sequence)

    csv_rows: list[dict] = []
    report_rows: list[tuple[str, str, str, str | None, str]] = (
        []
    )  # filename, sample_id, bucket, corrupted_field, outcome

    idx = 0
    for sample in sample_sequence:
        idx += 1
        bucket = rng.choices(
            list(BUCKET_WEIGHTS), weights=list(BUCKET_WEIGHTS.values())
        )[0]
        filename = f"label_{expected_outcome(sample["id"], bucket)}_{idx:03d}.png"
        fields, corrupted_field = build_row(sample, bucket, rng)

        (IMAGES_DIR / filename).write_bytes(rasterize(sample["filename"]))
        csv_rows.append({"filename": filename, **fields})
        report_rows.append(
            (
                filename,
                sample["id"],
                bucket,
                corrupted_field,
                expected_outcome(sample["id"], bucket),
            )
        )

    # --- Edge case: images with no matching CSV row ---
    unmatched_image_names = []
    for _ in range(NUM_UNMATCHED_IMAGES):
        idx += 1
        filename = f"label_{idx:03d}_unmatched_image.png"
        sample = rng.choice(samples)
        (IMAGES_DIR / filename).write_bytes(rasterize(sample["filename"]))
        unmatched_image_names.append(filename)

    # --- Edge case: CSV rows with no matching image ---
    unmatched_row_names = []
    for i in range(NUM_UNMATCHED_ROWS):
        idx += 1
        filename = f"label_{idx:03d}_unmatched_row.png"
        sample = rng.choice(samples)
        csv_rows.append({"filename": filename, **sample["application_data"]})
        unmatched_row_names.append(filename)

    # --- Edge case: duplicate filename in the CSV ---
    # Reuses an already-used filename with different data so the *second*
    # occurrence is unambiguously a conflicting duplicate; the CSV importer
    # keeps the first occurrence and flags the rest.
    duplicate_source = csv_rows[0]
    duplicate_row = dict(duplicate_source)
    dup_field = rng.choice(CORRUPTIBLE_FIELDS)
    duplicate_row[dup_field] = pick_alternate(
        dup_field, duplicate_source[dup_field], rng
    )
    for _ in range(NUM_DUPLICATE_ROWS):
        csv_rows.append(duplicate_row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", *FIELD_NAMES])
        writer.writeheader()
        writer.writerows(csv_rows)

    # --- Summary ---
    total_images = args.count + NUM_UNMATCHED_IMAGES
    outcome_counts: dict[str, int] = {}
    for *_rest, outcome in report_rows:
        key = outcome.split(" ", 1)[0]
        outcome_counts[key] = outcome_counts.get(key, 0) + 1

    print(
        f"Generated {total_images} images and {len(csv_rows)} CSV rows in {OUTPUT_DIR}\n"
    )

    print(f"Main rows (N={args.count}):")
    print(
        f"  {'filename':<16} {'sample':<8} {'bucket':<15} {'corrupted field':<18} expected outcome"
    )
    print("  " + "-" * 90)
    for filename, sample_id, bucket, corrupted_field, outcome in report_rows:
        print(
            f"  {filename:<16} {sample_id:<8} {bucket:<15} "
            f"{(corrupted_field or '-'):<18} {outcome}"
        )

    print("\nExpected outcome breakdown (main rows):")
    for key, count in sorted(outcome_counts.items()):
        print(f"  {key:<10} {count}")

    print("\nEdge cases (fixed counts, independent of N):")
    print(
        f"  {NUM_UNMATCHED_IMAGES} image(s) with no CSV row -> expected SKIPPED: {', '.join(unmatched_image_names)}"
    )
    print(
        f"  {NUM_UNMATCHED_ROWS} CSV row(s) with no image -> ignored, reported as unmatched in the UI: {', '.join(unmatched_row_names)}"
    )
    print(
        f"  {NUM_DUPLICATE_ROWS} duplicate CSV row for {duplicate_source['filename']} "
        f"(differing {dup_field}) -> first occurrence applies, duplicate flagged/ignored in the UI"
    )

    print(f"\nImages: {IMAGES_DIR}")
    print(f"CSV:    {CSV_PATH}")


if __name__ == "__main__":
    main()
