from app.services.stress_test_generator import (
    NUM_UNMATCHED_IMAGES,
    ExpectedOutcome,
    compute_expected_outcome,
    generate_stress_test_batch,
    split_main_and_unmatched_counts,
)


def test_split_reserves_unmatched_images_up_to_the_fixed_count():
    assert split_main_and_unmatched_counts(20) == (20 - NUM_UNMATCHED_IMAGES, NUM_UNMATCHED_IMAGES)
    assert split_main_and_unmatched_counts(100) == (100 - NUM_UNMATCHED_IMAGES, NUM_UNMATCHED_IMAGES)


def test_split_never_reserves_all_images_as_unmatched():
    # total_count=1 can't afford NUM_UNMATCHED_IMAGES unmatched slots and
    # still have a main row — must leave at least one main row.
    main, unmatched = split_main_and_unmatched_counts(1)
    assert main == 1
    assert unmatched == 0


def test_split_scales_down_unmatched_for_small_totals():
    main, unmatched = split_main_and_unmatched_counts(2)
    assert main + unmatched == 2
    assert main >= 1


def test_generate_batch_produces_requested_total_image_count():
    batch = generate_stress_test_batch(10, seed=1)

    assert len(batch.main_rows) + len(batch.unmatched_image_filenames) == 10
    assert len(batch.image_bytes) == 10


def test_generate_batch_unmatched_images_have_no_application_data_entry():
    batch = generate_stress_test_batch(10, seed=1)

    main_filenames = {row.filename for row in batch.main_rows}
    assert main_filenames.isdisjoint(batch.unmatched_image_filenames)
    # Every generated image (main or unmatched) has PNG bytes...
    for filename in [*main_filenames, *batch.unmatched_image_filenames]:
        assert filename in batch.image_bytes
    # ...but only main rows carry application data to verify against.
    assert len(batch.main_rows) == len(main_filenames)


def test_generate_batch_main_rows_have_all_seven_fields():
    batch = generate_stress_test_batch(10, seed=1)

    expected_keys = {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "bottler_info",
        "country_of_origin",
        "government_warning",
    }
    for row in batch.main_rows:
        assert set(row.application_data.keys()) == expected_keys


def test_generate_batch_is_reproducible_for_a_fixed_seed():
    batch_a = generate_stress_test_batch(10, seed=42)
    batch_b = generate_stress_test_batch(10, seed=42)

    assert [r.application_data for r in batch_a.main_rows] == [
        r.application_data for r in batch_b.main_rows
    ]
    assert batch_a.unmatched_image_filenames == batch_b.unmatched_image_filenames


def test_generate_batch_produces_real_rasterized_png_bytes():
    batch = generate_stress_test_batch(3, seed=1)

    for data in batch.image_bytes.values():
        assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


# --- Ground truth (compute_expected_outcome / expected_outcomes) ---


def test_compute_expected_outcome_approved_for_correct_bucket_on_compliant_sample():
    outcome = compute_expected_outcome("01", "correct", None)
    assert outcome == ExpectedOutcome(status="approved", failing_fields=())


def test_compute_expected_outcome_rejected_for_wrong_field():
    outcome = compute_expected_outcome("01", "wrong_field", "brand_name")
    assert outcome == ExpectedOutcome(status="rejected", failing_fields=("brand_name",))


def test_compute_expected_outcome_rejected_for_missing_field():
    # Unlike the CSV-import script's expected_outcome(), a blank field here is
    # verified (not excluded) and expected to mismatch the label's real text.
    outcome = compute_expected_outcome("01", "missing_field", "net_contents")
    assert outcome == ExpectedOutcome(status="rejected", failing_fields=("net_contents",))


def test_compute_expected_outcome_non_compliant_sample_always_rejected():
    # Samples other than "01" bake a non-compliant government warning into
    # the artwork itself, regardless of application data correctness.
    outcome = compute_expected_outcome("02", "correct", None)
    assert outcome == ExpectedOutcome(status="rejected", failing_fields=("government_warning",))


def test_compute_expected_outcome_non_compliant_sample_with_corrupted_field():
    outcome = compute_expected_outcome("03", "wrong_field", "alcohol_content")
    assert outcome == ExpectedOutcome(
        status="rejected", failing_fields=("alcohol_content", "government_warning")
    )


def test_generate_batch_filenames_bake_in_expected_outcome():
    batch = generate_stress_test_batch(10, seed=1)

    for row in batch.main_rows:
        if row.expected.status == "approved":
            assert "APPROVED" in row.filename
        else:
            assert "REJECTED" in row.filename
            for field_name in row.expected.failing_fields:
                assert field_name in row.filename


def test_generate_batch_expected_outcomes_cover_every_filename():
    batch = generate_stress_test_batch(10, seed=1)

    all_filenames = {row.filename for row in batch.main_rows} | set(
        batch.unmatched_image_filenames
    )
    assert set(batch.expected_outcomes.keys()) == all_filenames
    for filename in batch.unmatched_image_filenames:
        assert batch.expected_outcomes[filename].status == "skipped"
