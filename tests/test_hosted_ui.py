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
                race_import_ui.validate_screenshot_bytes(encoded_image(image_format))

    @unittest.skipUnless(features.check("webp"), "Pillow was built without WebP support")
    def test_accepts_valid_webp_when_supported(self):
        race_import_ui.validate_screenshot_bytes(encoded_image("WEBP"))

    def test_rejects_malformed_image(self):
        with self.assertRaisesRegex(ValueError, "invalid screenshot image"):
            race_import_ui.validate_screenshot_bytes(b"not actually an image")

    def test_rejects_oversized_upload_before_image_decoding(self):
        oversized = b"x" * (race_import_ui.MAX_SCREENSHOT_BYTES + 1)

        with mock.patch.object(race_import_ui.Image, "open") as image_open:
            with self.assertRaisesRegex(ValueError, "invalid screenshot size"):
                race_import_ui.validate_screenshot_bytes(oversized)

        image_open.assert_not_called()

    def test_rejects_image_over_pixel_limit(self):
        width = 5_001
        height = 5_000
        self.assertGreater(
            width * height,
            race_import_ui.MAX_SCREENSHOT_PIXELS,
        )
        # A one-bit PNG keeps this real over-limit fixture small and fast.
        with io.BytesIO() as output:
            Image.new("1", (width, height), 0).save(output, format="PNG")
            over_pixel_limit = output.getvalue()

        with self.assertRaisesRegex(ValueError, "invalid screenshot dimensions"):
            race_import_ui.validate_screenshot_bytes(over_pixel_limit)


class HostedStreamlitSafetyTests(unittest.TestCase):
    def test_admin_app_fails_closed_without_secrets(self):
        admin = AppTest.from_file(
            str(PROJECT_ROOT / "admin_app.py"),
            default_timeout=60,
        )
        admin.secrets = {}

        with mock.patch("race_github.fetch_remote_workbook") as fetch_remote:
            admin.run()

        self.assertFalse(admin.exception)
        self.assertTrue(admin.error)
        self.assertIn(
            "Nenhum dado pode ser alterado",
            "\n".join(str(item.value) for item in admin.error),
        )
        fetch_remote.assert_not_called()
        self.assertNotIn(
            "Publicar resultados",
            [str(button.label) for button in admin.button],
        )

    def test_public_app_points_to_the_private_hosted_updater(self):
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn(
            'PRIVATE_UPDATER_URL = "https://f1-game-dashboard-update.streamlit.app/"',
            source,
        )
        # One prominent shortcut plus the fifth-tab call to action must use it.
        self.assertGreaterEqual(source.count("PRIVATE_UPDATER_URL"), 3)

    @unittest.skipUnless(
        hasattr(st, "iframe"),
        "Public dashboard AppTest requires the project's pinned Streamlit 1.59 runtime",
    )
    def test_public_app_renders_private_updater_without_local_write_controls(self):
        dashboard = AppTest.from_file(
            str(PROJECT_ROOT / "app.py"),
            default_timeout=60,
        )

        with mock.patch.dict(os.environ, {"F1_ENABLE_RACE_IMPORT": ""}):
            dashboard.run()

        self.assertFalse(dashboard.exception)
        labels = [tab.label for tab in dashboard.tabs]
        self.assertEqual(len(labels), 5)
        self.assertIn("Import", labels[-1])
        self.assertTrue(dashboard.info, "The hosted updater safety notice was not rendered")
        button_labels = [str(button.label) for button in dashboard.button]
        self.assertNotIn("Extract standings", button_labels)
        self.assertNotIn("Update workbook", button_labels)


if __name__ == "__main__":
    unittest.main()
