from app.services.stress_test_generator import (
    NUM_UNMATCHED_IMAGES,
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
