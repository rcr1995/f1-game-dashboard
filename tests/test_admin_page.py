from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
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
        with patch("admin_auth.password_mode_enabled", return_value=False):
            app = self.assert_closed(admin_auth.AdminState.ANONYMOUS)
        self.assertTrue(any(button.label == "Sign in" for button in app.button))
        self.assertFalse(app.text_input)

    def test_anonymous_password_mode_has_masked_form_but_no_uploader(self):
        with (
            patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.ANONYMOUS,
            ),
            patch("admin_auth.password_mode_enabled", return_value=True),
            patch("admin_auth.authenticate_password") as authenticate,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()

        self.assertFalse(app.exception)
        self.assertEqual(1, len(app.text_input))
        self.assertEqual("Admin password", app.text_input[0].label)
        self.assertEqual(TextInputProto.PASSWORD, app.text_input[0].proto.type)
        self.assertTrue(any(button.label == "Sign in" for button in app.button))
        self.assertFalse(app.get("file_uploader"))
        authenticate.assert_not_called()

    def test_wrong_password_stays_closed(self):
        result = admin_auth.PasswordAuthResult(
            authenticated=False,
            locked=False,
            retry_after_seconds=0,
        )
        with (
            patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.ANONYMOUS,
            ),
            patch("admin_auth.password_mode_enabled", return_value=True),
            patch("admin_auth.authenticate_password", return_value=result) as authenticate,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()
            app.text_input[0].input("wrong password")
            next(button for button in app.button if button.label == "Sign in").click()
            app.run()

        authenticate.assert_called_once_with("wrong password")
        self.assertFalse(app.exception)
        self.assertTrue(any("Incorrect password" in error.value for error in app.error))
        self.assertFalse(app.get("file_uploader"))

    def test_locked_password_attempt_stays_closed(self):
        result = admin_auth.PasswordAuthResult(
            authenticated=False,
            locked=True,
            retry_after_seconds=37,
        )
        with (
            patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.ANONYMOUS,
            ),
            patch("admin_auth.password_mode_enabled", return_value=True),
            patch("admin_auth.authenticate_password", return_value=result),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()
            app.text_input[0].input("another wrong password")
            next(button for button in app.button if button.label == "Sign in").click()
            app.run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any("Try again in 37 seconds" in error.value for error in app.error)
        )
        self.assertFalse(app.get("file_uploader"))

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

    def test_correct_password_rechecks_state_before_reaching_importer(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        authenticated = False

        def current_state() -> admin_auth.AdminState:
            return (
                admin_auth.AdminState.AUTHORIZED
                if authenticated
                else admin_auth.AdminState.ANONYMOUS
            )

        def authenticate(candidate: str) -> admin_auth.PasswordAuthResult:
            nonlocal authenticated
            self.assertEqual("correct horse battery staple", candidate)
            authenticated = True
            return admin_auth.PasswordAuthResult(
                authenticated=True,
                locked=False,
                retry_after_seconds=0,
            )

        with (
            patch("admin_auth.current_admin_state", side_effect=current_state),
            patch("admin_auth.password_mode_enabled", return_value=True),
            patch("admin_auth.authenticate_password", side_effect=authenticate),
            patch("admin_auth.is_current_admin", return_value=True),
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="b" * 40,
                ),
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.run()
            app.text_input[0].input("correct horse battery staple")
            next(button for button in app.button if button.label == "Sign in").click()
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

    def test_password_admin_can_logout_from_sidebar(self):
        authenticated = True

        def current_state() -> admin_auth.AdminState:
            return (
                admin_auth.AdminState.AUTHORIZED
                if authenticated
                else admin_auth.AdminState.ANONYMOUS
            )

        def logout_and_rerun() -> None:
            nonlocal authenticated
            authenticated = False
            import streamlit as st

            st.rerun()

        with (
            patch("admin_auth.current_admin_state", side_effect=current_state),
            patch("admin_auth.password_mode_enabled", return_value=True),
            patch("admin_auth.logout", side_effect=logout_and_rerun) as logout,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()
            sign_out = next(button for button in app.button if button.label == "Sign out")
            sign_out.click().run()

        logout.assert_called_once_with()
        self.assertFalse(app.exception)
        self.assertEqual(1, len(app.text_input))
        self.assertFalse(app.get("file_uploader"))

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
