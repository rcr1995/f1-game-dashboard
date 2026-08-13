from __future__ import annotations

import os
import unittest
from collections.abc import Iterator, Mapping
from unittest.mock import patch

import admin_auth as auth


NOW = 2_000.0


def configured_secrets(*, email: str | None = None) -> dict[str, object]:
    section: dict[str, object] = {
        "allowed_issuer": "https://issuer.example",
        "allowed_subject": "admin-subject-123",
    }
    if email is not None:
        section["allowed_email"] = email
    return {
        "auth": {
            "redirect_uri": "https://dashboard.example/oauth2callback",
            "cookie_secret": "a-secure-random-cookie-secret-with-32-chars",
            "expose_tokens": False,
            "client_id": "oidc-client-id",
            "client_secret": "oidc-client-secret",
            "server_metadata_url": "https://issuer.example/.well-known/openid-configuration",
        },
        "admin_auth": section,
    }


def valid_config(*, email: str | None = None) -> auth.AdminAuthConfig:
    return auth.AdminAuthConfig(
        allowed_issuer="https://issuer.example",
        allowed_subject="admin-subject-123",
        allowed_email=email,
    )


def valid_claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "is_logged_in": True,
        "iss": "https://issuer.example",
        "sub": "admin-subject-123",
        "exp": NOW + 100,
    }
    claims.update(overrides)
    return claims


class FakeUser:
    def __init__(self, claims: dict[str, object], *, logged_in: object = True):
        self._claims = claims
        self.is_logged_in = logged_in

    def to_dict(self) -> dict[str, object]:
        return dict(self._claims)


class FakeStreamlit:
    def __init__(
        self,
        *,
        secrets: dict[str, object] | None = None,
        user: object | None = None,
        session_state: dict[object, object] | None = None,
    ):
        self.secrets = {} if secrets is None else secrets
        self.user = FakeUser({}, logged_in=False) if user is None else user
        self.session_state = {} if session_state is None else session_state
        self.login_calls = 0
        self.logout_calls = 0

    def login(self) -> None:
        self.login_calls += 1

    def logout(self) -> None:
        self.logout_calls += 1


class BrokenSecretsStreamlit:
    user = FakeUser({}, logged_in=False)

    @property
    def secrets(self) -> object:
        raise RuntimeError("no secrets configured")


class ExplodingSecrets(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("secrets source is unavailable")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


class ConfigParsingTests(unittest.TestCase):
    def test_state_values_are_stable(self):
        self.assertEqual(
            [state.value for state in auth.AdminState],
            [
                "disabled",
                "unconfigured",
                "anonymous",
                "forbidden",
                "expired",
                "authorized",
            ],
        )

    def test_loads_required_exact_identity_and_optional_email(self):
        without_email = auth.load_admin_config(configured_secrets())
        self.assertEqual(without_email, valid_config())

        with_email = auth.load_admin_config(configured_secrets(email="admin@example.com"))
        self.assertEqual(with_email, valid_config(email="admin@example.com"))

    def test_missing_or_malformed_config_fails_closed(self):
        invalid_sections: list[object] = [
            {},
            {"admin_auth": None},
            {"admin_auth": "not-a-table"},
            {"admin_auth": {"allowed_subject": "admin-subject-123"}},
            {"admin_auth": {"allowed_issuer": "https://issuer.example"}},
            {
                "admin_auth": {
                    "allowed_issuer": "",
                    "allowed_subject": "admin-subject-123",
                }
            },
            {
                "admin_auth": {
                    "allowed_issuer": " https://issuer.example",
                    "allowed_subject": "admin-subject-123",
                }
            },
            {
                "admin_auth": {
                    "allowed_issuer": "https://issuer.example",
                    "allowed_subject": 123,
                }
            },
            {
                "admin_auth": {
                    "allowed_issuer": "https://issuer.example",
                    "allowed_subject": "admin-subject-123",
                    "allowed_email": " ",
                }
            },
        ]
        for secrets in invalid_sections:
            with self.subTest(secrets=secrets):
                self.assertIsNone(auth.load_admin_config(secrets))

        self.assertIsNone(auth.load_admin_config(ExplodingSecrets()))

    def test_oidc_config_is_complete_strong_and_token_hidden(self):
        valid = configured_secrets()
        self.assertTrue(auth.oidc_is_configured(valid))

        invalid_sections = [
            {},
            {"auth": {}},
            {"auth": {**valid["auth"], "cookie_secret": "too-short"}},
            {"auth": {**valid["auth"], "client_secret": "YOUR-OIDC-CLIENT-SECRET"}},
            {"auth": {**valid["auth"], "expose_tokens": True}},
        ]
        for secrets in invalid_sections:
            with self.subTest(secrets=secrets):
                self.assertFalse(auth.oidc_is_configured(secrets))

    def test_feature_flag_must_be_explicitly_enabled(self):
        false_values: list[object] = [None, False, 0, 2, -1, "", "0", "false", "enabled", 1.0]
        for value in false_values:
            secrets = {} if value is None else {auth.FEATURE_FLAG: value}
            with self.subTest(value=value):
                self.assertFalse(auth.race_import_enabled(environ={}, secrets=secrets))

        true_values: list[object] = [True, 1, "1", " true ", "YES", "on"]
        for value in true_values:
            with self.subTest(value=value):
                self.assertTrue(
                    auth.race_import_enabled(
                        environ={},
                        secrets={auth.FEATURE_FLAG: value},
                    )
                )

    def test_environment_flag_takes_precedence_over_secret(self):
        self.assertFalse(
            auth.race_import_enabled(
                environ={auth.FEATURE_FLAG: "false"},
                secrets={auth.FEATURE_FLAG: True},
            )
        )
        self.assertTrue(
            auth.race_import_enabled(
                environ={auth.FEATURE_FLAG: "true"},
                secrets={auth.FEATURE_FLAG: False},
            )
        )


class AuthorizationDecisionTests(unittest.TestCase):
    def evaluate(
        self,
        claims: dict[str, object] | None,
        *,
        config: auth.AdminAuthConfig | None = None,
        enabled: bool = True,
    ) -> auth.AdminState:
        return auth.evaluate_admin_state(
            enabled=enabled,
            config=valid_config() if config is None else config,
            claims=claims,
            now=NOW,
        )

    def test_disabled_state_has_precedence(self):
        self.assertIs(
            self.evaluate(valid_claims(), config=None, enabled=False),
            auth.AdminState.DISABLED,
        )

    def test_unconfigured_state(self):
        self.assertIs(
            auth.evaluate_admin_state(
                enabled=True,
                config=None,
                claims=valid_claims(),
                now=NOW,
            ),
            auth.AdminState.UNCONFIGURED,
        )

    def test_anonymous_state(self):
        for claims in (None, {}, {"is_logged_in": False}, {"is_logged_in": "true"}):
            with self.subTest(claims=claims):
                self.assertIs(self.evaluate(claims), auth.AdminState.ANONYMOUS)

    def test_exact_issuer_and_subject_are_required(self):
        forbidden_claims = [
            valid_claims(iss="https://ISSUER.example"),
            valid_claims(iss="https://issuer.example/"),
            valid_claims(iss=None),
            valid_claims(sub="ADMIN-SUBJECT-123"),
            valid_claims(sub=None),
        ]
        for claims in forbidden_claims:
            with self.subTest(claims=claims):
                self.assertIs(self.evaluate(claims), auth.AdminState.FORBIDDEN)

    def test_valid_exact_identity_is_authorized(self):
        self.assertIs(self.evaluate(valid_claims()), auth.AdminState.AUTHORIZED)

    def test_expiry_is_required_numeric_finite_and_checked_at_boundary(self):
        malformed_expiries: list[object] = [None, True, "2100", float("nan"), float("inf")]
        for expiry in malformed_expiries:
            with self.subTest(expiry=expiry):
                self.assertIs(
                    self.evaluate(valid_claims(exp=expiry)),
                    auth.AdminState.FORBIDDEN,
                )

        for expiry in (NOW - 1, NOW):
            with self.subTest(expiry=expiry):
                self.assertIs(
                    self.evaluate(valid_claims(exp=expiry)),
                    auth.AdminState.EXPIRED,
                )

        self.assertIs(
            self.evaluate(valid_claims(exp=NOW + 0.001)),
            auth.AdminState.AUTHORIZED,
        )

    def test_optional_not_before_is_explicitly_validated(self):
        for not_before in (NOW - 1, NOW):
            with self.subTest(not_before=not_before):
                self.assertIs(
                    self.evaluate(valid_claims(nbf=not_before)),
                    auth.AdminState.AUTHORIZED,
                )

        for not_before in (NOW + 1, True, "1999", float("nan"), None):
            with self.subTest(not_before=not_before):
                self.assertIs(
                    self.evaluate(valid_claims(nbf=not_before)),
                    auth.AdminState.FORBIDDEN,
                )

    def test_configured_email_must_be_exact_and_verified_boolean(self):
        config = valid_config(email="admin@example.com")
        accepted = valid_claims(email="admin@example.com", email_verified=True)
        self.assertIs(self.evaluate(accepted, config=config), auth.AdminState.AUTHORIZED)

        rejected = [
            valid_claims(email_verified=True),
            valid_claims(email="Admin@example.com", email_verified=True),
            valid_claims(email="admin@example.com", email_verified=False),
            valid_claims(email="admin@example.com", email_verified="true"),
            valid_claims(email="admin@example.com"),
        ]
        for claims in rejected:
            with self.subTest(claims=claims):
                self.assertIs(
                    self.evaluate(claims, config=config),
                    auth.AdminState.FORBIDDEN,
                )

    def test_unconfigured_email_does_not_require_email_claims(self):
        claims = valid_claims(email="someone-else@example.com", email_verified=False)
        self.assertIs(self.evaluate(claims), auth.AdminState.AUTHORIZED)


class StreamlitWrapperTests(unittest.TestCase):
    def test_current_claims_returns_detached_claims_and_login_attribute(self):
        original = {"iss": "https://issuer.example", "sub": "admin-subject-123"}
        fake = FakeStreamlit(user=FakeUser(original, logged_in=True))
        with patch("admin_auth._streamlit", return_value=fake):
            claims = auth.current_claims()

        self.assertEqual(claims["iss"], "https://issuer.example")
        self.assertIs(claims["is_logged_in"], True)
        claims["iss"] = "changed"
        self.assertEqual(original["iss"], "https://issuer.example")

    def test_current_state_reads_feature_and_allow_list_from_server_config(self):
        secrets = configured_secrets()
        fake = FakeStreamlit(
            secrets=secrets,
            user=FakeUser(valid_claims(exp=4_000_000_000), logged_in=True),
        )
        with (
            patch.dict(os.environ, {auth.FEATURE_FLAG: "1"}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.AUTHORIZED)
            self.assertTrue(auth.is_current_admin())

    def test_current_state_accepts_top_level_secret_feature_flag(self):
        secrets = configured_secrets()
        secrets[auth.FEATURE_FLAG] = True
        fake = FakeStreamlit(
            secrets=secrets,
            user=FakeUser(valid_claims(exp=4_000_000_000), logged_in=True),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.AUTHORIZED)

    def test_current_state_is_disabled_when_flag_is_absent(self):
        fake = FakeStreamlit(
            secrets=configured_secrets(),
            user=FakeUser(valid_claims(exp=4_000_000_000), logged_in=True),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.DISABLED)

    def test_current_state_is_unconfigured_when_enabled_without_allow_list(self):
        fake = FakeStreamlit(secrets={})
        with (
            patch.dict(os.environ, {auth.FEATURE_FLAG: "true"}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.UNCONFIGURED)

    def test_current_state_is_unconfigured_when_oidc_settings_are_incomplete(self):
        secrets = configured_secrets()
        del secrets["auth"]["client_secret"]
        fake = FakeStreamlit(secrets=secrets)
        with (
            patch.dict(os.environ, {auth.FEATURE_FLAG: "true"}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.UNCONFIGURED)

    def test_missing_streamlit_secrets_fails_closed(self):
        with (
            patch.dict(os.environ, {auth.FEATURE_FLAG: "true"}, clear=True),
            patch("admin_auth._streamlit", return_value=BrokenSecretsStreamlit()),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.UNCONFIGURED)

        fake = FakeStreamlit(secrets=ExplodingSecrets())  # type: ignore[arg-type]
        with (
            patch.dict(os.environ, {auth.FEATURE_FLAG: "true"}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.UNCONFIGURED)

    def test_login_uses_streamlit_native_oidc(self):
        fake = FakeStreamlit()
        with patch("admin_auth._streamlit", return_value=fake):
            auth.login()
        self.assertEqual(fake.login_calls, 1)

    def test_clear_state_removes_every_importer_key_only(self):
        state: dict[object, object] = {
            "race_import_files": ["one.png"],
            "race_import_review": {"approved": False},
            "race_import_": "prefix itself",
            "dashboard_filter": "2026",
            7: "non-string-key",
        }
        removed = auth.clear_race_import_state(state)
        self.assertCountEqual(
            removed,
            ("race_import_files", "race_import_review", "race_import_"),
        )
        self.assertEqual(state, {"dashboard_filter": "2026", 7: "non-string-key"})

    def test_logout_clears_importer_state_before_native_logout(self):
        session_state: dict[object, object] = {
            "race_import_files": [b"sensitive screenshot"],
            "race_import_draft": {"driver": "Alice"},
            "public_language": "pt",
        }
        fake = FakeStreamlit(session_state=session_state)

        def assert_cleared_then_logout() -> None:
            self.assertFalse(
                any(
                    isinstance(key, str) and key.startswith(auth.SESSION_STATE_PREFIX)
                    for key in fake.session_state
                )
            )
            fake.logout_calls += 1

        fake.logout = assert_cleared_then_logout  # type: ignore[method-assign]
        with patch("admin_auth._streamlit", return_value=fake):
            auth.logout()

        self.assertEqual(fake.logout_calls, 1)
        self.assertEqual(fake.session_state, {"public_language": "pt"})


if __name__ == "__main__":
    unittest.main()
