from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import admin_auth
import race_github


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GITHUB_SECRETS = {
    "github": {
        "owner": "example-owner",
        "repository": "example-repository",
        "branch": "main",
        "workbook_path": "F1_Standings.xlsx",
        "app_id": "123",
        "installation_id": 456,
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-only\n-----END RSA PRIVATE KEY-----",
    }
}


class AdminPageAccessTests(unittest.TestCase):
    def render(self, state: admin_auth.AdminState) -> AppTest:
        with patch("admin_auth.current_admin_state", return_value=state):
            return AppTest.from_file("admin_page.py", default_timeout=30).run()

    def assert_closed(self, state: admin_auth.AdminState) -> AppTest:
        app = self.render(state)
        self.assertFalse(app.exception)
        self.assertFalse(app.get("file_uploader"))
        self.assertFalse(any("Import one race" in header.value for header in app.header))
        return app

    def test_disabled_direct_route_has_no_admin_capability(self):
        self.assert_closed(admin_auth.AdminState.DISABLED)

    def test_unconfigured_direct_route_has_no_admin_capability(self):
        self.assert_closed(admin_auth.AdminState.UNCONFIGURED)

    def test_anonymous_direct_route_has_sign_in_but_no_uploader(self):
        app = self.assert_closed(admin_auth.AdminState.ANONYMOUS)
        self.assertTrue(any(button.label == "Sign in" for button in app.button))

    def test_authenticated_non_admin_has_logout_but_no_uploader(self):
        app = self.assert_closed(admin_auth.AdminState.FORBIDDEN)
        self.assertTrue(any(button.label == "Sign out" for button in app.button))

    def test_expired_identity_has_no_uploader(self):
        self.assert_closed(admin_auth.AdminState.EXPIRED)

    def test_authorized_admin_reaches_protected_importer(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
            patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            patch("admin_auth.is_current_admin", return_value=True),
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="a" * 40,
                ),
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                header.value in {"Import one race", "Importar uma corrida"}
                for header in app.header
            )
        )
        self.assertEqual(1, len(app.get("file_uploader")))

    def test_authorized_admin_can_logout_from_sidebar(self):
        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
            patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            patch("admin_auth.is_current_admin", return_value=True),
            patch("admin_auth.logout") as logout,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60).run()
            sign_out = next(button for button in app.button if button.label == "Sign out")
            sign_out.click().run()

        logout.assert_called_once_with()

    def test_logout_button_calls_server_side_logout(self):
        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.FORBIDDEN),
            patch("admin_auth.logout") as logout,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()
            sign_out = next(button for button in app.button if button.label == "Sign out")
            sign_out.click().run()

        logout.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
