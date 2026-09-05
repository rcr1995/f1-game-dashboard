from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest

import admin_auth
import race_github
import review_draft_recovery


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORT_TITLES = {"Import one event", "Importar um evento"}
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
        self.assertFalse(app.get("download_button"))
        self.assertFalse(any(header.value in IMPORT_TITLES for header in app.header))
        return app

    def test_disabled_direct_route_has_no_admin_capability(self):
        self.assert_closed(admin_auth.AdminState.DISABLED)

    def test_excel_upload_action_is_protected_and_next_to_download(self):
        with patch("workbook_upload.render") as upload:
            self.assert_closed(admin_auth.AdminState.ANONYMOUS)
            upload.assert_not_called()
            with (
                patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
                patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
                patch("admin_auth.is_current_admin", return_value=True),
                patch("race_github.fetch_remote_workbook", return_value=race_github.RemoteWorkbook(
                    content=(PROJECT_ROOT / "F1_Standings.xlsx").read_bytes(), blob_sha="a" * 40)),
            ):
                app = AppTest.from_file("admin_page.py", default_timeout=60)
                app.secrets = GITHUB_SECRETS
                app.run()
                labels = [button.label for button in app.button]
                self.assertEqual(labels.index("Upload latest Excel"), labels.index("Download latest Excel") + 1)
                next(button for button in app.button if button.label == "Upload latest Excel").click()
                app.run()
                self.assertFalse(app.exception)
                upload.assert_called_once()

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
            patch("browser_download.render_excel_download") as download,
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="a" * 40,
                ),
            ) as fetch_remote,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.run()
            self.assertFalse(app.get("download_button"))
            next(
                button for button in app.button if button.label == "Download latest Excel"
            ).click()
            app.run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                header.value in IMPORT_TITLES
                for header in app.header
            )
        )
        self.assertEqual(1, len(app.get("file_uploader")))
        self.assertEqual(2, fetch_remote.call_count)
        self.assertEqual(
            "a" * 40,
            app.session_state["race_import_download_workbook"]["blob_sha"],
        )
        download.assert_called_once()
        self.assertEqual((workbook_content, "F1_Standings.xlsx"), download.call_args.args)
        self.assertEqual("Download F1_Standings.xlsx", download.call_args.kwargs["label"])
        self.assertIn("fetched from GitHub", download.call_args.kwargs["help_text"])
        self.assertFalse(app.get("download_button"))

    def test_authorized_admin_download_label_follows_portuguese_preference(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
            patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            patch("admin_auth.is_current_admin", return_value=True),
            patch("browser_download.render_excel_download") as download,
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="c" * 40,
                ),
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.session_state["app_lang"] = "Português (Portugal)"
            app.run()
            next(
                button
                for button in app.button
                if button.label == "Descarregar Excel mais recente"
            ).click()
            app.run()

        self.assertFalse(app.exception)
        download.assert_called_once()
        self.assertEqual("Descarregar F1_Standings.xlsx", download.call_args.kwargs["label"])
        self.assertIn("versão exata", download.call_args.kwargs["help_text"])

    def test_invalid_fresh_github_workbook_is_not_offered_for_download(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
            patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            patch("admin_auth.is_current_admin", return_value=True),
            patch(
                "race_github.fetch_remote_workbook",
                side_effect=[
                    race_github.RemoteWorkbook(
                        content=workbook_content,
                        blob_sha="d" * 40,
                    ),
                    race_github.RemoteWorkbook(
                        content=b"not an Excel workbook",
                        blob_sha="e" * 40,
                    ),
                ],
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.run()
            next(
                button for button in app.button if button.label == "Download latest Excel"
            ).click()
            app.run()

        self.assertFalse(app.exception)
        self.assertFalse(app.get("download_button"))
        self.assertNotIn("race_import_download_workbook", app.session_state)
        self.assertTrue(
            any("could not be prepared for download" in error.value for error in app.error)
        )

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
                header.value in IMPORT_TITLES
                for header in app.header
            )
        )
        self.assertEqual(1, len(app.get("file_uploader")))

    def test_authorized_admin_can_logout_from_sidebar(self):
        events: list[str] = []

        def acknowledge_clear(state: object) -> bool:
            self.assertEqual(
                review_draft_recovery.pending_clear_reason(state),  # type: ignore[arg-type]
                "logout",
            )
            events.append("browser-cleared")
            return True

        def logout_after_clear() -> None:
            events.append("logout")

        with (
            patch("admin_auth.current_admin_state", return_value=admin_auth.AdminState.AUTHORIZED),
            patch("admin_auth.current_claims", return_value={"email": "admin@example.com"}),
            patch("admin_auth.is_current_admin", return_value=True),
            patch("admin_auth.logout", side_effect=logout_after_clear) as logout,
            patch(
                "review_draft_recovery.render_pending_clear",
                side_effect=acknowledge_clear,
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60).run()
            sign_out = next(button for button in app.button if button.label == "Sign out")
            sign_out.click().run()

        logout.assert_called_once_with()
        self.assertEqual(events, ["browser-cleared", "logout"])
        self.assertNotIn(
            review_draft_recovery.CLEAR_PENDING_KEY,
            app.session_state,
        )

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
            patch("review_draft_recovery.render_pending_clear", return_value=True),
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
            patch("review_draft_recovery.request_browser_clear") as clear_recovery,
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=30).run()
            sign_out = next(button for button in app.button if button.label == "Sign out")
            sign_out.click().run()

        logout.assert_called_once_with()
        # This closed-state button renews an expired/forbidden identity. The
        # opaque browser token stays available to the same allowed Admin, while
        # identity binding prevents the current unauthorized identity using it.
        clear_recovery.assert_not_called()


if __name__ == "__main__":
    unittest.main()
