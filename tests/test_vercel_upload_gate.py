"""Exercise the pinned native HTTP routes with synthetic signed identities."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient
import streamlit
from streamlit.runtime.app_session import AppSession
from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager
from streamlit.web.server.starlette import starlette_app, starlette_routes
from streamlit.web.server.starlette.starlette_app_utils import create_signed_value, generate_xsrf_token_string
from streamlit.web.server.starlette.starlette_server_config import USER_COOKIE_NAME, XSRF_COOKIE_NAME

import vercel_upload_gate as gate


ORIGIN = "https://example.invalid"
SIGNING_SECRET = "synthetic-signing-secret-only-for-local-tests-0123456789"
NOW = 1_800_000_000.0
ADMIN = {
    "iss": "https://accounts.google.com", "sub": "synthetic-admin-subject",
    "email": "admin@example.invalid", "email_verified": True,
    "is_logged_in": True, "exp": NOW + 3600,
}
SETTINGS = {
    "admin_auth": {
        "mode": "oidc", "allowed_issuer": ADMIN["iss"],
        "allowed_subject": ADMIN["sub"], "allowed_email": ADMIN["email"],
    },
    "auth": {
        "redirect_uri": ORIGIN + "/oauth2callback", "cookie_secret": SIGNING_SECRET,
        "client_id": "synthetic-client-id", "client_secret": "synthetic-client-secret",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "expose_tokens": False,
    },
}


class VercelUploadGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patches = [
            patch.dict(os.environ, {"F1_ENABLE_RACE_IMPORT": "1"}),
            patch("streamlit.runtime.secrets.secrets_singleton", deepcopy(SETTINGS)),
            patch("streamlit.auth_util.get_origin_from_redirect_uri", return_value=ORIGIN),
            patch("streamlit.web.server.starlette.starlette_websocket.get_cookie_secret", return_value=SIGNING_SECRET),
            patch.object(starlette_routes, "is_xsrf_enabled", return_value=True),
            patch.object(gate.time, "time", return_value=NOW),
            patch.object(starlette_app, "create_upload_routes", starlette_routes.create_upload_routes),
            patch.object(gate, "_installed", False),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.admin_session = SimpleNamespace(_user_info=dict(ADMIN))
        self.sessions = {
            "admin-session": SimpleNamespace(client=object(), session=self.admin_session),
            "public-session": SimpleNamespace(client=object(), session=SimpleNamespace(_user_info={})),
        }
        self.runtime = SimpleNamespace(
            _session_mgr=SimpleNamespace(get_active_session_info=self.sessions.get),
            is_active_session=lambda session_id: session_id in self.sessions,
        )
        self.uploads = MemoryUploadedFileManager("/_stcore/upload_file")
        gate.install_upload_gate()
        routes = starlette_app.create_upload_routes(self.runtime, self.uploads, "")
        self.client = TestClient(Starlette(routes=routes), base_url=ORIGIN)
        self.addCleanup(self.client.close)
        self.xsrf = generate_xsrf_token_string(timestamp=int(NOW))
        self.client.cookies.set(XSRF_COOKIE_NAME, self.xsrf)
        self.client.headers.update({"X-Xsrftoken": self.xsrf, "Origin": ORIGIN})
        self.sign_in()

    def sign_in(self, claims=None, *, key=SIGNING_SECRET, origin=ORIGIN) -> None:
        payload = dict(ADMIN if claims is None else claims, origin=origin)
        signed = create_signed_value(key, USER_COOKIE_NAME, json.dumps(payload)).decode("ascii")
        self.client.cookies.set(USER_COOKIE_NAME, signed)

    def put(self, session="admin-session", file="screenshot-1", **kwargs):
        return self.client.put(
            f"/_stcore/upload_file/{session}/{file}",
            files={"file": ("synthetic.png", b"synthetic-image-bytes", "image/png")}, **kwargs,
        )

    def assert_denied_before_body(self, session="admin-session", **kwargs) -> None:
        with patch.object(Request, "form", new_callable=AsyncMock) as parse_body:
            response = self.put(session, **kwargs)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, gate.DENIED_MESSAGE)
        parse_body.assert_not_awaited()
        self.assertFalse(self.uploads.get_files(session, ["screenshot-1"]))

    def test_authenticated_two_three_four_file_flow_retains_native_storage_and_delete(self) -> None:
        for count in (2, 3, 4):
            with self.subTest(count=count):
                ids = [f"set-{count}-{i}" for i in range(count)]
                for file_id in ids:
                    self.assertEqual(self.put(file=file_id).status_code, 204)
                self.assertEqual(len(self.uploads.get_files("admin-session", ids)), count)
                for file_id in ids:
                    response = self.client.delete(f"/_stcore/upload_file/admin-session/{file_id}")
                    self.assertEqual(response.status_code, 204)
                self.assertFalse(self.uploads.get_files("admin-session", ids))

    def test_public_active_session_denied_even_with_admin_cookie(self) -> None:
        self.assert_denied_before_body("public-session")

    def test_public_cookie_and_spoofed_body_cannot_create_authorization(self) -> None:
        self.client.cookies.delete(USER_COOKIE_NAME)
        self.assert_denied_before_body("public-session")
        self.assert_denied_before_body()  # knowledge of an Admin session id is insufficient

    def test_tampered_unsigned_wrong_key_and_wrong_origin_cookies_are_denied(self) -> None:
        valid = self.client.cookies.get(USER_COOKIE_NAME)
        for value in (valid + "x", json.dumps(dict(ADMIN, origin=ORIGIN)), "garbage"):
            with self.subTest(value_type=value[:10]):
                self.client.cookies.set(USER_COOKIE_NAME, value)
                self.assert_denied_before_body()
        self.sign_in(key="synthetic-wrong-key")
        self.assert_denied_before_body()
        self.sign_in(origin="https://another.example.invalid")
        self.assert_denied_before_body()

    def test_native_chunked_cookie_is_verified_and_missing_or_tampered_chunk_is_denied(self) -> None:
        from streamlit.auth_util import set_cookie_with_chunks

        payload = dict(ADMIN, origin=ORIGIN, note="".join(
            hashlib.sha256(str(index).encode("ascii")).hexdigest() for index in range(180)
        ))
        generated = {}

        def set_cookie(name, value):
            generated[name] = create_signed_value(SIGNING_SECRET, name, value).decode("ascii")

        set_cookie_with_chunks(
            set_cookie, lambda name, value: create_signed_value(SIGNING_SECRET, name, value),
            USER_COOKIE_NAME, payload, cookie_attr_size=128,
        )
        self.assertGreater(len(generated), 1)
        for name, value in generated.items():
            self.client.cookies.set(name, value)
        self.assertEqual(self.put(file="chunked-cookie-success").status_code, 204)
        chunk = next(name for name in generated if name != USER_COOKIE_NAME)
        self.client.cookies.set(chunk, generated[chunk] + "tampered")
        self.assert_denied_before_body()
        self.client.cookies.delete(chunk)
        self.assert_denied_before_body()

    def test_cookie_or_live_session_expiry_forbidden_identity_and_logged_out_are_denied(self) -> None:
        for overrides in (
            {"exp": NOW}, {"exp": "tomorrow"}, {"sub": "another-subject"},
            {"iss": "https://evil.invalid"}, {"email_verified": False}, {"is_logged_in": False},
        ):
            with self.subTest(overrides=overrides):
                self.sign_in(dict(ADMIN, **overrides))
                self.assert_denied_before_body()
                self.sign_in()
                self.admin_session._user_info = dict(ADMIN, **overrides)
                self.assert_denied_before_body()
                self.admin_session._user_info = dict(ADMIN)

    def test_native_logout_clears_live_identity_immediately_even_with_retained_cookie(self) -> None:
        AppSession.clear_user_info(self.admin_session)
        self.assert_denied_before_body()
        response = self.client.delete("/_stcore/upload_file/admin-session/screenshot-1")
        self.assertEqual(response.status_code, 403)

    def test_unknown_disconnected_or_incompatible_session_denied(self) -> None:
        self.assert_denied_before_body("missing-session")
        self.sessions["admin-session"].client = None
        self.assert_denied_before_body()
        self.sessions["admin-session"].client = object()
        self.admin_session._user_info = "not-a-mapping"
        self.assert_denied_before_body()

    def test_disabled_missing_invalid_and_password_configuration_denied(self) -> None:
        with patch.dict(os.environ, {"F1_ENABLE_RACE_IMPORT": "0"}):
            self.assert_denied_before_body()
        for settings in ({}, {"auth": SETTINGS["auth"]}, dict(SETTINGS, admin_auth={"mode": "password"})):
            with self.subTest(settings_keys=list(settings)):
                with patch("streamlit.runtime.secrets.secrets_singleton", settings):
                    self.assert_denied_before_body()

    def test_cross_origin_or_host_mismatch_denied(self) -> None:
        self.assert_denied_before_body(headers={"Origin": "https://evil.invalid"})
        self.assert_denied_before_body(headers={"Host": "other.example.invalid"})

    def test_valid_admin_still_requires_native_xsrf(self) -> None:
        with patch.object(Request, "form", new_callable=AsyncMock) as parse_body:
            response = self.put(headers={"X-Xsrftoken": "invalid"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("XSRF", response.text)
        parse_body.assert_not_awaited()

    def test_valid_admin_still_has_native_payload_limit(self) -> None:
        with patch.object(Request, "form", new_callable=AsyncMock) as parse_body:
            response = self.put(headers={"Content-Length": str(300 * 1024 * 1024)})
        self.assertEqual(response.status_code, 413)
        parse_body.assert_not_awaited()

    def test_options_keeps_native_cors_headers_without_uploading(self) -> None:
        self.client.cookies.delete(USER_COOKIE_NAME)
        response = self.client.options("/_stcore/upload_file/public-session/screenshot-1")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["Access-Control-Allow-Methods"], "PUT, OPTIONS, DELETE")
        self.assertEqual(response.headers["Access-Control-Allow-Credentials"], "true")
        self.assertFalse(self.uploads.get_files("public-session", ["screenshot-1"]))

    def test_installation_is_idempotent_but_version_or_factory_changes_stop_startup(self) -> None:
        installed = starlette_app.create_upload_routes
        gate.install_upload_gate()
        self.assertIs(starlette_app.create_upload_routes, installed)
        with patch.object(streamlit, "__version__", "1.60.0"):
            with self.assertRaisesRegex(RuntimeError, "Server startup stopped"):
                gate.install_upload_gate()
        with patch.object(starlette_app, "create_upload_routes", lambda: None):
            with self.assertRaisesRegex(RuntimeError, "Server startup stopped"):
                gate.install_upload_gate()

    def test_unknown_route_factory_shape_stops_before_serving(self) -> None:
        with patch.object(gate, "_installed", False):
            def changed(runtime, upload_mgr, base_url):
                return []
            with patch.object(starlette_routes, "create_upload_routes", changed):
                with patch.object(starlette_app, "create_upload_routes", changed):
                    gate.install_upload_gate()
                    with self.assertRaisesRegex(RuntimeError, "Server startup stopped"):
                        starlette_app.create_upload_routes(self.runtime, self.uploads, "")

    def test_gate_startup_failure_is_generic(self) -> None:
        with patch.object(gate, "install_upload_gate", side_effect=RuntimeError("synthetic-private-value")):
            with patch("sys.stderr", new_callable=io.StringIO) as output:
                with self.assertRaises(SystemExit) as exit_error:
                    gate.main()
        self.assertEqual(exit_error.exception.code, 1)
        self.assertEqual(output.getvalue(), gate.STARTUP_ERROR + "\n")


class VercelUploadServerStartupTests(unittest.TestCase):
    def test_real_pinned_server_installs_gate_before_serving_any_upload(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="f1-gate-startup-test-") as temporary:
            # A fresh minimal environment plus an explicitly nonexistent secret
            # path: no deployed credentials are read or passed to this server.
            environment = {
                key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE")
                if key in os.environ
            }
            environment.update({"F1_ENABLE_RACE_IMPORT": "0", "F1_PUBLIC_GITHUB_SYNC": "0"})
            command = [
                sys.executable, "-m", "vercel_upload_gate", "run", str(root / "app.py"),
                "--server.address=127.0.0.1", f"--server.port={port}",
                "--server.headless=true", "--browser.gatherUsageStats=false",
                f"--secrets.files={Path(temporary) / 'not-configured.toml'}",
            ]
            server = subprocess.Popen(
                command, cwd=root, env=environment, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.monotonic() + 20
                healthy = False
                while time.monotonic() < deadline and server.poll() is None:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                            healthy = response.status == 200
                        if healthy:
                            break
                    except (URLError, TimeoutError):
                        time.sleep(0.1)
                if not healthy and server.poll() is not None:
                    self.fail("The credential-free test server exited: " + server.stderr.read())
                self.assertTrue(healthy, "The pinned server did not become healthy with the upload gate installed.")
                request = UrlRequest(
                    f"http://127.0.0.1:{port}/_stcore/upload_file/public-session/test-file",
                    data=b"synthetic-upload-content", method="PUT",
                )
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=2)
                self.assertEqual(caught.exception.code, 403)
                self.assertEqual(caught.exception.read().decode("utf-8"), gate.DENIED_MESSAGE)
                caught.exception.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                server.stderr.close()


if __name__ == "__main__":
    unittest.main()
