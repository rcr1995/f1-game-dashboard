"""The container launcher must never put runtime credentials in source/logs."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import vercel_start as launcher


# Entirely synthetic fixtures; not values from any account or deployment.
FAKE_SECRET = "synthetic-never-log-this-value"
VALID_TOML = f'''[auth]
client_secret = "{FAKE_SECRET}"
cookie_secret = "synthetic-cookie-012345678901234567890123456789"
redirect_uri = "https://example.invalid/oauth2callback"
client_id = "synthetic-client"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
expose_tokens = false
[admin_auth]
mode = "oidc"
allowed_issuer = "https://accounts.google.com"
allowed_subject = "synthetic-subject"
[github]
owner = "synthetic-owner"
repository = "synthetic-repo"
installation_id = 123
private_key = """synthetic-line-one
synthetic-line-two"""
'''


class VercelStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="f1-launch-test-")
        self.addCleanup(self.temp.cleanup)
        self.temp_patch = patch.object(launcher.tempfile, "gettempdir", return_value=self.temp.name)
        self.temp_patch.start()
        self.addCleanup(self.temp_patch.stop)

    def test_no_secret_preserves_closed_default_and_creates_no_file(self) -> None:
        plan = launcher.prepare_launch({})
        self.assertIsNone(plan.secret_file)
        self.assertEqual(plan.environment[launcher.FEATURE_FLAG], "0")
        self.assertFalse(any(arg.startswith("--secrets.files") for arg in plan.command))
        self.assertIn("--server.port=80", plan.command)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_secret_is_runtime_only_and_removed_from_both_environments(self) -> None:
        environment = {
            launcher.SECRETS_ENV: VALID_TOML, launcher.FEATURE_FLAG: "1", "PORT": "8080",
            "VERCEL_OIDC_TOKEN": "synthetic-other-secret-not-for-plan-repr",
        }
        plan = launcher.prepare_launch(environment)
        self.addCleanup(launcher.cleanup_secret_file, plan.secret_file)
        self.assertNotIn(launcher.SECRETS_ENV, environment)
        self.assertNotIn(launcher.SECRETS_ENV, plan.environment)
        self.assertEqual(plan.environment[launcher.FEATURE_FLAG], "1")
        self.assertNotIn(FAKE_SECRET, str(plan))
        self.assertNotIn("synthetic-other-secret-not-for-plan-repr", str(plan))
        self.assertIsNotNone(plan.secret_file)
        self.assertFalse(plan.secret_file.is_relative_to(launcher.SOURCE_ROOT))
        self.assertEqual(plan.secret_file.read_bytes(), VALID_TOML.encode("utf-8"))
        self.assertIn(f"--secrets.files={plan.secret_file}", plan.command)
        self.assertIn("--server.port=8080", plan.command)
        self.assertNotIn("sh", plan.command)
        self.assertFalse(any("enableXsrfProtection" in arg or "enableCORS" in arg for arg in plan.command))

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits are enforced in the Linux container")
    def test_runtime_secret_permission_bits(self) -> None:
        plan = launcher.prepare_launch({launcher.SECRETS_ENV: VALID_TOML})
        self.addCleanup(launcher.cleanup_secret_file, plan.secret_file)
        self.assertEqual(stat.S_IMODE(plan.secret_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(plan.secret_file.parent.stat().st_mode), 0o700)

    def test_invalid_secrets_fail_before_any_file_and_do_not_echo_values(self) -> None:
        invalid_values = (
            "", "   ", "# comment only", f'[auth]\nclient_secret = "{FAKE_SECRET}',
            VALID_TOML + "\n\x00", "x" * (launcher.MAX_SECRET_BYTES + 1),
            '[auth]\nclient_secret="' + "é" * launcher.MAX_SECRET_BYTES + '"',
            'client_secret="' + FAKE_SECRET + '"', '[server]\nenableCORS=false',
            'auth="' + FAKE_SECRET + '"', "[auth]", "[auth]\nnumber=nan",
            "[auth]\nnumber=inf", "[auth]\nexpires=2026-09-04", "[auth]\na=1\na=2",
            "[auth]\nx=" + "[" * (launcher.MAX_DEPTH + 2) + "1" + "]" * (launcher.MAX_DEPTH + 2),
            "[auth]\nx=[" + ",".join("1" for _ in range(launcher.MAX_ITEMS + 1)) + "]",
            "[auth]\n" + "\n".join(f"key_{i}=1" for i in range(launcher.MAX_ITEMS + 1)),
            '[auth]\n"bad key"="' + FAKE_SECRET + '"',
            '[auth]\nclient_secret="' + "x" * (launcher.MAX_VALUE_BYTES + 1) + '"',
            '[auth]\nclient_secret="\\u0000"', '[auth]\nclient_secret="\ud800"',
            'F1_ENABLE_RACE_IMPORT=[]\n[auth]\nclient_secret="synthetic"',
            # Valid TOML 1.0 but rejected by Streamlit's legacy parser. Reject
            # it here, before that parser could log the actual setting value.
            '[auth]\nmixed=[1,"synthetic"]',
        )
        for raw in invalid_values:
            with self.subTest(case=invalid_values.index(raw)):
                environment = {launcher.SECRETS_ENV: raw}
                with self.assertRaises(launcher.ConfigurationError) as caught:
                    launcher.prepare_launch(environment)
                self.assertEqual(str(caught.exception), launcher.CONFIGURATION_ERROR)
                self.assertNotIn(launcher.SECRETS_ENV, environment)
                self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_port_is_bounded_and_cannot_inject_shell_or_cli_options(self) -> None:
        for port in ("0", "65536", "-1", "1; echo nope", "80 --server.enableCORS=false", " 80", "８０"):
            with self.subTest(port=port):
                with self.assertRaises(launcher.ConfigurationError):
                    launcher.prepare_launch({"PORT": port, launcher.SECRETS_ENV: VALID_TOML})
        for port in ("1", "65535", ""):
            with self.subTest(port=port):
                plan = launcher.prepare_launch({"PORT": port})
                self.assertIn(f"--server.port={port or '80'}", plan.command)

    def test_runtime_temp_directory_cannot_be_inside_app_sources(self) -> None:
        with patch.object(launcher.tempfile, "gettempdir", return_value=str(launcher.SOURCE_ROOT)):
            with patch.object(launcher.tempfile, "mkdtemp") as mkdir:
                with self.assertRaises(launcher.ConfigurationError):
                    launcher.prepare_launch({launcher.SECRETS_ENV: VALID_TOML})
                mkdir.assert_not_called()

    def test_write_failure_cleans_exact_private_directory(self) -> None:
        with patch.object(launcher.os, "fdopen", side_effect=OSError(FAKE_SECRET)):
            with self.assertRaises(launcher.ConfigurationError) as caught:
                launcher.prepare_launch({launcher.SECRETS_ENV: VALID_TOML})
        self.assertEqual(str(caught.exception), launcher.CONFIGURATION_ERROR)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_main_exec_inherits_no_secret_and_no_shell(self) -> None:
        environment = {launcher.SECRETS_ENV: VALID_TOML, launcher.FEATURE_FLAG: "1"}
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(launcher.os, "execve") as execute:
                self.assertEqual(launcher.main(), 0)
                executable, command, child_environment = execute.call_args.args
                self.assertEqual(executable, launcher.sys.executable)
                self.assertEqual(command[:4], (executable, "-m", "vercel_upload_gate", "run"))
                self.assertNotIn(launcher.SECRETS_ENV, os.environ)
                self.assertNotIn(launcher.SECRETS_ENV, child_environment)
                self.assertNotIn(FAKE_SECRET, str(command))
                secret_file = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--secrets.files=")))
                self.assertTrue(secret_file.exists())  # real exec must retain it
                launcher.cleanup_secret_file(secret_file)

    def test_main_invalid_input_and_exec_failures_are_generic_and_cleaned(self) -> None:
        for raw, error in ((FAKE_SECRET, launcher.CONFIGURATION_ERROR), (VALID_TOML, launcher.STARTUP_ERROR)):
            with self.subTest(error=error):
                output = io.StringIO()
                with patch.dict(os.environ, {launcher.SECRETS_ENV: raw}, clear=True):
                    with patch.object(launcher.os, "execve", side_effect=OSError(FAKE_SECRET)):
                        with contextlib.redirect_stderr(output):
                            self.assertEqual(launcher.main(), 1)
                    self.assertNotIn(launcher.SECRETS_ENV, os.environ)
                self.assertEqual(output.getvalue(), error + "\n")
                self.assertNotIn(FAKE_SECRET, output.getvalue())
                self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_pinned_streamlit_exposes_secrets_files_cli_option(self) -> None:
        try:
            from streamlit import config
            from streamlit.web.cli import _convert_config_option_to_click_option
        except ImportError:
            self.skipTest("Install requirements.txt for Streamlit CLI compatibility verification")
        option = config._config_options_template["secrets.files"]
        click_option = _convert_config_option_to_click_option(option)
        self.assertEqual(click_option["option"], "--secrets.files")
        self.assertTrue(click_option["multiple"])
        self.assertIs(click_option["type"], str)

    def test_pinned_streamlit_parses_launch_command_and_private_file(self) -> None:
        from click.testing import CliRunner
        from streamlit.runtime.secrets import Secrets
        from streamlit.web import cli

        plan = launcher.prepare_launch({launcher.SECRETS_ENV: VALID_TOML})
        self.addCleanup(launcher.cleanup_secret_file, plan.secret_file)
        with patch.object(cli, "_main_run") as start:
            result = CliRunner().invoke(cli.main, list(plan.command[3:]))
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(start.call_args.kwargs["flag_options"]["secrets_files"], (str(plan.secret_file),))
        parsed, found = Secrets()._parse_toml_file(str(plan.secret_file))
        self.assertTrue(found)
        self.assertEqual(parsed["auth"]["client_secret"], FAKE_SECRET)
        self.assertEqual(parsed["admin_auth"]["allowed_subject"], "synthetic-subject")

    def test_legacy_toml_flag_cannot_override_explicit_deployment_gate(self) -> None:
        from streamlit import config
        from streamlit.runtime.secrets import Secrets

        for toml_flag, deployment_flag in (("1", "0"), ("0", "1")):
            with self.subTest(deployment_flag=deployment_flag):
                plan = launcher.prepare_launch({
                    launcher.SECRETS_ENV: f'F1_ENABLE_RACE_IMPORT="{toml_flag}"\n' + VALID_TOML,
                    launcher.FEATURE_FLAG: deployment_flag,
                })
                self.addCleanup(launcher.cleanup_secret_file, plan.secret_file)
                self.assertNotIn("F1_ENABLE_RACE_IMPORT", plan.secret_file.read_text(encoding="utf-8"))
                with patch.dict(os.environ, plan.environment, clear=True):
                    with patch.object(config, "get_option", return_value=[str(plan.secret_file)]):
                        secrets = Secrets()
                        with patch.object(Secrets, "_maybe_install_file_watchers"):
                            # Access uses the actual parser AND root export path.
                            self.assertEqual(secrets["admin_auth"]["mode"], "oidc")
                        self.assertEqual(os.environ[launcher.FEATURE_FLAG], deployment_flag)
                        self.assertNotIn(launcher.SECRETS_ENV, os.environ)


if __name__ == "__main__":
    unittest.main()
