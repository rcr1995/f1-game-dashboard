from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

import race_import as race
import race_import_ui as ui
import race_ocr


def image_bytes(*, color: str = "red", image_format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format=image_format)
    return buffer.getvalue()


def result(position: int, driver: str, source: str) -> race.ExtractedResult:
    return race.ExtractedResult(
        position=position,
        raw_text=f"{position} {driver}",
        driver=driver,
        suggested_driver=driver,
        confidence=0.95,
        sources=[source],
        match_method="exact",
        issues=[],
    )


class ScreenshotIntakeTests(unittest.TestCase):
    def test_hosted_and_local_modes_both_recheck_exact_admin(self):
        for hosted in (True, False):
            with self.subTest(hosted=hosted), patch(
                "race_import_ui.admin_auth.is_current_admin", return_value=True
            ) as is_admin:
                self.assertTrue(ui._require_local_admin(hosted=hosted, expired=True))
                is_admin.assert_called_once_with()

    def test_failed_local_admin_recheck_stops_the_action(self):
        with (
            patch("race_import_ui.admin_auth.is_current_admin", return_value=False),
            patch("race_import_ui.st.error") as error,
            patch("race_import_ui.st.stop") as stop,
        ):
            self.assertFalse(ui._require_local_admin(hosted=True, expired=True))

        error.assert_called_once_with("Admin authorization expired. Sign in again.")
        stop.assert_called_once_with()

    def test_only_two_three_or_four_images_are_accepted(self):
        for count in (0, 1, 5):
            with self.subTest(count=count):
                self.assertFalse(ui.valid_screenshot_count(count))
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.assertTrue(ui.valid_screenshot_count(count))

    def test_blank_review_is_only_allowed_with_zero_attached_images(self):
        self.assertTrue(ui.blank_review_allowed(0))
        for count in (1, 2, 3, 4, 5):
            with self.subTest(count=count):
                self.assertFalse(ui.blank_review_allowed(count))

    def test_valid_sets_accept_two_three_and_four_distinct_rasters(self):
        uploads = [image_bytes(color=color) for color in ("red", "green", "blue", "yellow")]
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.assertEqual(ui.validate_screenshot_set(uploads[:count]), [])

    def test_invalid_count_duplicate_and_spoofed_files_are_rejected(self):
        one = image_bytes()
        self.assertTrue(ui.validate_screenshot_set([one]))
        duplicate_errors = ui.validate_screenshot_set([one, one])
        self.assertTrue(any("identical duplicate" in error for error in duplicate_errors))
        invalid_errors = ui.validate_screenshot_set([one, b"not really an image"])
        self.assertTrue(any("not a valid" in error for error in invalid_errors))

    def test_ocr_receives_every_image_with_stable_source_labels(self):
        roster = [race.DriverEntry("Alice", "Red"), race.DriverEntry("Bob", "Blue")]
        uploads = [image_bytes(color=color) for color in ("red", "green", "blue", "yellow")]
        calls: list[str] = []

        def fake_extract(_value: bytes, source: str, *, grid_size: int | None = None):
            self.assertEqual(grid_size, len(roster))
            calls.append(source)
            return []

        with patch("race_import_ui.race_ocr.extract_tokens", side_effect=fake_extract):
            rows, token_count = ui._draft_from_ocr(uploads, roster)

        self.assertEqual(calls, ["Screenshot 1", "Screenshot 2", "Screenshot 3", "Screenshot 4"])
        self.assertEqual(token_count, 0)
        self.assertEqual(len(rows), len(roster))

    def test_four_image_overlap_chain_reconciles_all_sources(self):
        sets = [
            [result(1, "Alice", "Screenshot 1")],
            [result(1, "Alice", "Screenshot 2"), result(2, "Bob", "Screenshot 2")],
            [result(2, "Bob", "Screenshot 3"), result(3, "Charlie", "Screenshot 3")],
            [result(3, "Charlie", "Screenshot 4")],
        ]
        merged = race.merge_screenshot_results(sets)
        by_position = {item.position: item for item in merged}
        self.assertEqual(by_position[1].sources, ["Screenshot 1", "Screenshot 2"])
        self.assertEqual(by_position[2].sources, ["Screenshot 2", "Screenshot 3"])
        self.assertEqual(by_position[3].sources, ["Screenshot 3", "Screenshot 4"])

    def test_raster_magic_validation_accepts_supported_formats(self):
        for image_format in ("PNG", "JPEG", "WEBP"):
            with self.subTest(image_format=image_format):
                race_ocr.validate_image_upload(image_bytes(image_format=image_format))

    def test_jpeg_validation_accepts_trailing_phone_metadata(self):
        payload = image_bytes(image_format="JPEG") + b"Image_UTC_Data\x00SEFH\x00\x00SEFT"

        race_ocr.validate_image_upload(payload)

    def test_jpeg_validation_rejects_missing_eoi_and_truncated_image_data(self):
        payload = image_bytes(image_format="JPEG")

        for truncated in (payload[:-2], payload[:-100]):
            with self.subTest(bytes_removed=len(payload) - len(truncated)):
                with self.assertRaises(race_ocr.InvalidScreenshotError):
                    race_ocr.validate_image_upload(truncated)

    def test_decompression_bomb_is_reported_as_invalid_upload(self):
        payload = image_bytes()
        with (
            patch("PIL.Image.open", side_effect=Image.DecompressionBombError("too many pixels")),
            self.assertRaises(race_ocr.InvalidScreenshotError),
        ):
            race_ocr.validate_image_upload(payload)

    def test_decompression_bomb_blocks_the_complete_upload_set(self):
        uploads = [image_bytes(color="red"), image_bytes(color="blue")]
        with patch(
            "PIL.Image.open",
            side_effect=Image.DecompressionBombError("too many pixels"),
        ):
            errors = ui.validate_screenshot_set(uploads)

        self.assertEqual(len(errors), 2)
        self.assertTrue(all("not a valid" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
