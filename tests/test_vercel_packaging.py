"""Keep the isolated container trial's source upload and image secret-free."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MODULES = {
    "app", "admin_app", "admin_page", "admin_auth", "admin_management_ui",
    "dashboard_page", "dashboard_core", "puskas_html", "league_config",
    "league_runtime", "league_workbook", "race_correction", "race_github",
    "race_import", "race_import_ui", "race_metadata", "race_ocr", "race_workbook",
    "ui_preferences", "public_workbook", "hosted_settings", "vercel_start", "vercel_upload_gate",
}
PUBLIC_ASSET_SOURCES = {
    "assets/hero_banner.webp", "assets/helmets/", "assets/tracks/",
}


class VercelPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dockerfile = (ROOT / "Dockerfile.vercel").read_text(encoding="utf-8")
        cls.copy_sources = {
            source
            for line in cls.dockerfile.splitlines()
            if line.startswith("COPY ")
            for source in json.loads(line.removeprefix("COPY "))[:-1]
        }

    def test_image_uses_only_explicit_runtime_sources(self) -> None:
        expected = {f"{name}.py" for name in RUNTIME_MODULES} | {
            "requirements.txt", "requirements-import.txt", "F1_Standings.xlsx",
            ".streamlit/config.toml",
        } | PUBLIC_ASSET_SOURCES
        self.assertEqual(self.copy_sources, expected)
        for source in self.copy_sources:
            with self.subTest(source=source):
                self.assertTrue((ROOT / source).exists())
                self.assertNotIn("*", source)
                self.assertNotIn(source, {".", "./", ".streamlit/"})
        self.assertFalse(any(line.startswith("ADD ") for line in self.dockerfile.splitlines()))

    def test_all_local_runtime_imports_are_packaged(self) -> None:
        for module in RUNTIME_MODULES:
            tree = ast.parse((ROOT / f"{module}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imported = []
                if isinstance(node, ast.Import):
                    imported = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = [node.module.split(".")[0]]
                for dependency in imported:
                    if (ROOT / f"{dependency}.py").is_file():
                        with self.subTest(module=module, dependency=dependency):
                            self.assertIn(dependency, RUNTIME_MODULES)

    def test_public_asset_directories_have_no_symlinks_or_unexpected_files(self) -> None:
        # COPY accepts asset directories, so guard their present contents too.
        # In particular, an image-named symlink must not escape this workspace.
        for directory, suffixes in (
            ("assets/helmets", {".webp"}),
            ("assets/tracks", {".webp", ".jpg", ".png"}),
        ):
            assets = list((ROOT / directory).iterdir())
            self.assertTrue(assets)
            for asset in assets:
                with self.subTest(asset=asset.relative_to(ROOT)):
                    self.assertFalse(asset.is_symlink())
                    self.assertTrue(asset.is_file())
                    self.assertIn(asset.suffix, suffixes)
                    self.assertTrue(asset.resolve().is_relative_to(ROOT.resolve()))

    def test_runtime_defaults_keep_admin_disabled_and_follow_port_contract(self) -> None:
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        # Fail closed: never let an unconfigured project serve Python sources as
        # a static deployment if platform autodetection changes.
        self.assertEqual(config["framework"], "container")
        self.assertIn("FROM python:3.11-slim-bookworm", self.dockerfile)
        self.assertIn("F1_ENABLE_RACE_IMPORT=0", self.dockerfile)
        command_line = next(line for line in self.dockerfile.splitlines() if line.startswith("CMD "))
        command = json.loads(command_line.removeprefix("CMD "))
        self.assertEqual(command, ["python", "vercel_start.py"])
        self.assertIn("F1_PUBLIC_GITHUB_SYNC=1", self.dockerfile)
        launcher = (ROOT / "vercel_start.py").read_text(encoding="utf-8")
        self.assertIn("--server.address=0.0.0.0", launcher)
        self.assertIn('--server.port={port}', launcher)
        self.assertNotIn("--server.enableXsrfProtection=false", launcher)
        self.assertNotIn("--server.enableCORS=false", launcher)
        for prohibited in ("PRIVATE KEY-----", "client_secret=", "password_hash=", "ARG "):
            self.assertNotIn(prohibited, self.dockerfile)

    def test_upload_and_build_are_deny_by_default(self) -> None:
        for filename in (".dockerignore", ".vercelignore"):
            patterns = [
                line.strip()
                for line in (ROOT / filename).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
            with self.subTest(filename=filename):
                self.assertEqual(patterns[0], "*")
                for module in RUNTIME_MODULES:
                    self.assertIn(f"!{module}.py", patterns)
                for source in ("requirements.txt", "requirements-import.txt", "F1_Standings.xlsx", ".streamlit/config.toml"):
                    self.assertIn(f"!{source}", patterns)
                allowed_nonmodules = {
                    "Dockerfile.vercel", ".dockerignore", ".vercelignore", "vercel.json",
                    "requirements.txt", "requirements-import.txt", "F1_Standings.xlsx",
                    ".streamlit", ".streamlit/config.toml", "assets", "assets/hero_banner.webp",
                    "assets/helmets", "assets/helmets/*.webp", "assets/tracks",
                    "assets/tracks/*.webp", "assets/tracks/*.png", "assets/tracks/*.jpg",
                }
                if filename == ".vercelignore":
                    allowed_nonmodules.add(r"assets\\tracks\\Portimão.webp")
                allowed = {pattern[1:] for pattern in patterns if pattern.startswith("!")}
                self.assertLessEqual(allowed, {f"{name}.py" for name in RUNTIME_MODULES} | allowed_nonmodules)
                for secret_exclusion in ("**/.env*", "**/secrets*", "**/*.pem", "**/*.key", "**/.codex*"):
                    self.assertIn(secret_exclusion, patterns)
                    self.assertGreater(patterns.index(secret_exclusion), max(i for i, value in enumerate(patterns) if value.startswith("!")))

    def test_directory_exceptions_allow_traversal_but_not_arbitrary_children(self) -> None:
        # Vercel CLI checks directory names without a trailing slash before
        # traversing. Docker applies a matching parent exception to children.
        # Reopen each directory, then immediately re-exclude its descendants;
        # only the subsequent explicit file exceptions can admit any content.
        for filename in (".dockerignore", ".vercelignore"):
            patterns = [
                line.strip()
                for line in (ROOT / filename).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
            for directory, first_allowed_file in (
                (".streamlit", ".streamlit/config.toml"),
                ("assets", "assets/hero_banner.webp"),
                ("assets/helmets", "assets/helmets/*.webp"),
                ("assets/tracks", "assets/tracks/*.webp"),
            ):
                with self.subTest(filename=filename, directory=directory):
                    index = patterns.index(f"!{directory}")
                    self.assertEqual(patterns[index + 1], f"{directory}/**")
                    self.assertLess(index + 1, patterns.index(f"!{first_allowed_file}"))
                    self.assertNotIn(f"!{directory}/", patterns)

    def test_windows_unicode_asset_has_exact_upload_exception(self) -> None:
        patterns = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
        exception = r"!assets\\tracks\\Portimão.webp"
        self.assertIn(exception, patterns)
        self.assertTrue((ROOT / "assets/tracks/Portimão.webp").is_file())
        self.assertLess(patterns.index(exception), patterns.index("**/secrets*"))
        self.assertNotIn("!*Portimão.webp", patterns)


if __name__ == "__main__":
    unittest.main()
