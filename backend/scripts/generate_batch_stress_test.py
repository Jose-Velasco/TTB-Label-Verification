"""Generate a folder of label images + a matching CSV for manually exercising
the batch page's CSV-import feature (correct rows, mismatched fields, missing
fields, unmatched images, unmatched CSV rows, duplicate filenames).

Standalone script, separate from the pytest eval suite. Main-row generation
(sample selection, field corruption, rasterization) now lives in
app.services.stress_test_generator — shared with the /api/stress-test/run
endpoint, which needs the same logic in-memory instead of written to disk.
This script layers its own disk/CSV writing and CSV-only edge cases
(unmatched rows, duplicate filenames — neither of which make sense once
there's no CSV import step to test) on top of that shared generation.

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

from app.services.golden_samples import load_golden_samples
from app.services.stress_test_generator import (
    CORRUPTIBLE_FIELDS,
    FIELD_NAMES,
    NUM_UNMATCHED_IMAGES,
    expected_outcome,
    generate_stress_test_batch,
    pick_alternate,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "batch_stress_test"
IMAGES_DIR = OUTPUT_DIR / "images"
CSV_PATH = OUTPUT_DIR / "labels.csv"

NUM_UNMATCHED_ROWS = 2  # CSV rows with no matching image
NUM_DUPLICATE_ROWS = 1  # extra CSV row reusing an already-used filename


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=10, help="Number of main rows to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed for reproducible output"
    )
    args = parser.parse_args()

    # generate_stress_test_batch carves its own small fixed number of
    # unmatched-image rows out of whatever total it's given (see
    # NUM_UNMATCHED_IMAGES), so ask for count + that many extra to get
    # exactly --count main rows out the other end.
    batch = generate_stress_test_batch(
        args.count + NUM_UNMATCHED_IMAGES, seed=args.seed
    )

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    csv_rows: list[dict] = []
    report_rows: list[tuple[str, str, str, str | None, str]] = (
        []
    )  # filename, sample_id, bucket, corrupted_field, outcome

    for i, row in enumerate(batch.main_rows, start=1):
        outcome = expected_outcome(row.sample_id, row.bucket)
        filename = f"label_{outcome}_{i:03d}.png"
        (IMAGES_DIR / filename).write_bytes(batch.image_bytes[row.filename])
        csv_rows.append({"filename": filename, **row.application_data})
        report_rows.append(
            (filename, row.sample_id, row.bucket, row.corrupted_field, outcome)
        )

    # --- Edge case: images with no matching CSV row ---
    unmatched_image_names = []
    for i, internal_filename in enumerate(batch.unmatched_image_filenames, start=1):
        filename = f"label_{len(batch.main_rows) + i:03d}_unmatched_image.png"
        (IMAGES_DIR / filename).write_bytes(batch.image_bytes[internal_filename])
        unmatched_image_names.append(filename)

    # The two edge cases below are CSV-import-only concerns (no image
    # involved, or a plain key collision) that generate_stress_test_batch
    # doesn't model — reusing its RNG stream isn't possible since it's
    # internal to that call, so this starts a fresh one seeded the same way.
    # Statistically equivalent (uniform, correctly weighted) but no longer
    # byte-for-byte identical output to a pre-refactor run at the same --seed.
    rng = random.Random(args.seed)
    samples = load_golden_samples()

    # --- Edge case: CSV rows with no matching image ---
    unmatched_row_names = []
    idx = len(batch.main_rows) + len(unmatched_image_names)
    for _ in range(NUM_UNMATCHED_ROWS):
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
    total_images = len(batch.main_rows) + len(unmatched_image_names)
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
        f"  {len(unmatched_image_names)} image(s) with no CSV row -> expected SKIPPED: {', '.join(unmatched_image_names)}"
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
