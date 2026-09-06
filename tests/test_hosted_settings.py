from __future__ import annotations

from types import SimpleNamespace
import unittest

import hosted_settings
import public_workbook


class HostedSettingsTests(unittest.TestCase):
    def publisher(self, **changes):
        return SimpleNamespace(
            **{"owner": "rcr1995", "repository": "f1-game-dashboard", "branch": "main",
               "workbook_path": "F1_Standings.xlsx", **changes}
        )

    def test_default_url_preserves_streamlit_workflow(self):
        self.assertEqual(hosted_settings.dashboard_url({}), "https://f1puskasleague.vercel.app/")

    def test_configured_dashboard_url_is_normalized(self):
        for value in ("https://f1puskasleague.vercel.app", "https://f1puskasleague.vercel.app/"):
            self.assertEqual(hosted_settings.dashboard_url({"F1_PUBLIC_DASHBOARD_URL": value}),
                             "https://f1puskasleague.vercel.app/")

    def test_invalid_dashboard_origins_fall_back_without_crashing(self):
        for value in (
            "http://f1puskasleague.vercel.app", "//f1puskasleague.vercel.app", "javascript:alert(1)",
            "https://user:password@example.com", "https://example.com/admin", "https://example.com/?token=x",
            "https://example.com/#private", "https://example.com ", " https://example.com", "https://[",
            "https://example.com:wrong", "https://example.com:99999", "https://exam\nple.com",
            "https://example.com\t", "https://example.com\\escape",
        ):
            with self.subTest(url=value):
                self.assertEqual(hosted_settings.dashboard_url({"F1_PUBLIC_DASHBOARD_URL": value}),
                                 hosted_settings.DEFAULT_DASHBOARD_URL)

    def test_disabled_reader_does_not_change_existing_publisher_validation(self):
        hosted_settings.validate_publisher_target(self.publisher(repository="manual-other-repo"), {})

    def test_same_public_reader_and_admin_writer_are_accepted(self):
        hosted_settings.validate_publisher_target(self.publisher(), {"F1_PUBLIC_GITHUB_SYNC": "1"})

    def test_github_owner_and_repo_match_case_insensitively(self):
        hosted_settings.validate_publisher_target(self.publisher(owner="RCR1995", repository="F1-GAME-DASHBOARD"),
                                                  {"F1_PUBLIC_GITHUB_SYNC": "1"})

    def test_different_publisher_targets_fail_closed(self):
        for field, value in (("owner", "someone-else"), ("repository", "different-repo"),
                             ("branch", "MAIN"), ("workbook_path", "f1_standings.xlsx")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    hosted_settings.validate_publisher_target(self.publisher(**{field: value}),
                                                              {"F1_PUBLIC_GITHUB_SYNC": "1"})

    def test_missing_publisher_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            hosted_settings.validate_publisher_target(object(), {"F1_PUBLIC_GITHUB_SYNC": "1"})

    def test_explicit_nested_workbook_source_must_match_exactly(self):
        env = {"F1_PUBLIC_GITHUB_SYNC": "1", "F1_PUBLIC_GITHUB_BRANCH": "codex/test-data",
               "F1_PUBLIC_GITHUB_WORKBOOK_PATH": "data/Standings.xlsx"}
        hosted_settings.validate_publisher_target(
            self.publisher(branch="codex/test-data", workbook_path="data/Standings.xlsx"), env)
        with self.assertRaises(ValueError):
            hosted_settings.validate_publisher_target(self.publisher(), env)

    def test_invalid_public_reader_configuration_fails_closed(self):
        with self.assertRaises(public_workbook.PublicWorkbookError):
            hosted_settings.validate_publisher_target(self.publisher(),
                {"F1_PUBLIC_GITHUB_SYNC": "1", "F1_PUBLIC_GITHUB_BRANCH": "../main"})


if __name__ == "__main__":
    unittest.main()
