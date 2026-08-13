from __future__ import annotations

import io
import os
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image, features
import streamlit as st
from streamlit.testing.v1 import AppTest

import race_import_ui
import race_ocr
import admin_auth


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def encoded_image(image_format: str, *, size: tuple[int, int] = (32, 18)) -> bytes:
    """Create a small real image without relying on committed fixture files."""
    mode = "RGB" if image_format in {"JPEG", "WEBP"} else "RGBA"
    color = (25, 50, 75) if mode == "RGB" else (25, 50, 75, 255)
    with io.BytesIO() as output:
        Image.new(mode, size, color).save(output, format=image_format)
        return output.getvalue()


class ScreenshotValidationTests(unittest.TestCase):
    def test_accepts_valid_png_and_jpeg(self):
        for image_format in ("PNG", "JPEG"):
            with self.subTest(image_format=image_format):
                race_ocr.validate_image_upload(encoded_image(image_format))

    @unittest.skipUnless(features.check("webp"), "Pillow was built without WebP support")
    def test_accepts_valid_webp_when_supported(self):
        race_ocr.validate_image_upload(encoded_image("WEBP"))

    def test_rejects_malformed_image(self):
        with self.assertRaisesRegex(race_ocr.InvalidScreenshotError, "not a valid"):
            race_ocr.validate_image_upload(b"not actually an image")

    def test_rejects_oversized_upload_before_image_decoding(self):
        oversized = b"x" * (race_ocr.MAX_IMAGE_BYTES + 1)

        with mock.patch("PIL.Image.open") as image_open:
            with self.assertRaisesRegex(race_ocr.InvalidScreenshotError, "12 MB"):
                race_ocr.validate_image_upload(oversized)

        image_open.assert_not_called()

    def test_rejects_image_over_pixel_limit(self):
        width = 5_001
        height = 5_000
        self.assertGreater(
            width * height,
            race_ocr.MAX_IMAGE_PIXELS,
        )
        # A one-bit PNG keeps this real over-limit fixture small and fast.
        with io.BytesIO() as output:
            Image.new("1", (width, height), 0).save(output, format="PNG")
            over_pixel_limit = output.getvalue()

        with self.assertRaisesRegex(race_ocr.InvalidScreenshotError, "25-megapixel"):
            race_ocr.validate_image_upload(over_pixel_limit)


class HostedStreamlitSafetyTests(unittest.TestCase):
    def test_admin_app_direct_route_fails_closed_without_auth(self):
        admin = AppTest.from_file(
            str(PROJECT_ROOT / "admin_app.py"),
            default_timeout=60,
        )
        admin.secrets = {}

        with mock.patch("race_github.fetch_remote_workbook") as fetch_remote:
            admin.run()

        self.assertFalse(admin.exception)
        fetch_remote.assert_not_called()
        self.assertFalse(admin.get("file_uploader"))
        self.assertNotIn(
            "Publicar resultados",
            [str(button.label) for button in admin.button],
        )

    def test_authorized_admin_fails_closed_without_github_secrets(self):
        admin = AppTest.from_file(
            str(PROJECT_ROOT / "admin_app.py"),
            default_timeout=60,
        )
        admin.secrets = {}

        with (
            mock.patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.AUTHORIZED,
            ),
            mock.patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            mock.patch("admin_auth.is_current_admin", return_value=True),
            mock.patch("race_github.fetch_remote_workbook") as fetch_remote,
        ):
            admin.run()

        self.assertFalse(admin.exception)
        self.assertTrue(admin.error)
        self.assertIn(
            "Nenhum dado pode ser alterado",
            "\n".join(str(item.value) for item in admin.error),
        )
        fetch_remote.assert_not_called()
        self.assertFalse(admin.get("file_uploader"))

    def test_public_router_points_to_the_protected_admin_route(self):
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('title="Admin"', source)
        self.assertIn('url_path="admin"', source)
        self.assertNotIn("PRIVATE_UPDATER_URL", source)

    @unittest.skipUnless(
        hasattr(st, "iframe"),
        "Public dashboard AppTest requires the project's pinned Streamlit 1.59 runtime",
    )
    def test_public_app_has_no_importer_or_local_write_controls(self):
        dashboard = AppTest.from_file(
            str(PROJECT_ROOT / "app.py"),
            default_timeout=60,
        )

        with mock.patch.dict(os.environ, {"F1_ENABLE_RACE_IMPORT": "1"}):
            dashboard.run()

        self.assertFalse(dashboard.exception)
        labels = [tab.label for tab in dashboard.tabs]
        self.assertEqual(len(labels), 4)
        self.assertFalse(dashboard.get("file_uploader"))
        button_labels = [str(button.label) for button in dashboard.button]
        self.assertNotIn("Extract standings", button_labels)
        self.assertNotIn("Update workbook", button_labels)


if __name__ == "__main__":
    unittest.main()
