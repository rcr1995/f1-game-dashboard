from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest
from collections.abc import Iterator, Mapping
from unittest.mock import patch

from argon2 import PasswordHasher

import admin_auth as auth


NOW = 2_000.0
TEST_PASSWORD = "test-only-high-entropy-password-7Cqv0w8f"
TEST_PASSWORD_HASH = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
).hash(TEST_PASSWORD)


def configured_secrets(*, email: str | None = None) -> dict[str, object]:
    section: dict[str, object] = {
        "mode": "oidc",
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


def password_secrets(**overrides: object) -> dict[str, object]:
    section: dict[str, object] = {
        "mode": "password",
        "password_hash": TEST_PASSWORD_HASH,
    }
    section.update(overrides)
    return {
        auth.FEATURE_FLAG: True,
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
        self.rerun_calls = 0

    def login(self) -> None:
        self.login_calls += 1

    def logout(self) -> None:
        self.logout_calls += 1

    def rerun(self) -> None:
        self.rerun_calls += 1


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

    def test_authentication_mode_must_be_explicit_and_exact(self):
        self.assertIs(
            auth.load_auth_mode({"admin_auth": {"mode": "oidc"}}),
            auth.AdminAuthMode.OIDC,
        )
        self.assertIs(
            auth.load_auth_mode({"admin_auth": {"mode": "password"}}),
            auth.AdminAuthMode.PASSWORD,
        )
        for mode in (None, "", "OIDC", " oidc", "password ", True, "fallback"):
            section = {} if mode is None else {"mode": mode}
            with self.subTest(mode=mode):
                self.assertIsNone(auth.load_auth_mode({"admin_auth": section}))

    def test_loads_required_exact_identity_and_optional_email(self):
        without_email = auth.load_admin_config(configured_secrets())
        self.assertEqual(without_email, valid_config())

        with_email = auth.load_admin_config(configured_secrets(email="admin@example.com"))
        self.assertEqual(with_email, valid_config(email="admin@example.com"))

    def test_missing_malformed_or_wrong_mode_oidc_config_fails_closed(self):
        invalid_sections: list[object] = [
            {},
            {"admin_auth": None},
            {"admin_auth": "not-a-table"},
            {"admin_auth": {"allowed_issuer": "https://issuer.example", "allowed_subject": "x"}},
            {"admin_auth": {"mode": "password", "allowed_issuer": "https://issuer.example", "allowed_subject": "x"}},
            {"admin_auth": {"mode": "oidc", "allowed_subject": "admin-subject-123"}},
            {"admin_auth": {"mode": "oidc", "allowed_issuer": "https://issuer.example"}},
            {
                "admin_auth": {
                    "mode": "oidc",
                    "allowed_issuer": "",
                    "allowed_subject": "admin-subject-123",
                }
            },
            {
                "admin_auth": {
                    "mode": "oidc",
                    "allowed_issuer": " https://issuer.example",
                    "allowed_subject": "admin-subject-123",
                }
            },
            {
                "admin_auth": {
                    "mode": "oidc",
                    "allowed_issuer": "https://issuer.example",
                    "allowed_subject": 123,
                }
            },
            {
                "admin_auth": {
                    "mode": "oidc",
                    "allowed_issuer": "https://issuer.example",
                    "allowed_subject": "admin-subject-123",
                    "allowed_email": "YOUR-ADMIN-EMAIL",
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

    def test_password_config_accepts_secure_argon2id_and_policy_defaults(self):
        config = auth.load_password_config(password_secrets())
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.session_ttl_seconds, 1_800)
        self.assertEqual(config.idle_ttl_seconds, 900)
        self.assertEqual(config.max_failed_attempts, 5)
        self.assertEqual(config.failure_window_seconds, 900)
        self.assertEqual(config.lockout_seconds, 900)
        self.assertNotIn(TEST_PASSWORD_HASH, repr(config))

    def test_password_config_rejects_missing_placeholder_wrong_mode_and_weak_hash(self):
        weak_memory_hash = TEST_PASSWORD_HASH.replace("m=65536", "m=8192", 1)
        invalid = [
            {"admin_auth": {"mode": "password"}},
            {"admin_auth": {"mode": "password", "password_hash": "YOUR-ARGON2ID-HASH"}},
            {"admin_auth": {"mode": "oidc", "password_hash": TEST_PASSWORD_HASH}},
            {"admin_auth": {"mode": "password", "password_hash": TEST_PASSWORD_HASH + " "}},
            {"admin_auth": {"mode": "password", "password_hash": weak_memory_hash}},
            {"admin_auth": {"mode": "password", "password_hash": TEST_PASSWORD_HASH.replace("argon2id", "argon2i", 1)}},
        ]
        for secrets in invalid:
            with self.subTest(secrets=secrets):
                self.assertIsNone(auth.load_password_config(secrets))

    def test_password_policy_values_are_bounded_and_idle_cannot_exceed_absolute(self):
        accepted = password_secrets(
            session_ttl_seconds=300,
            idle_ttl_seconds=300,
            max_failed_attempts=3,
            failure_window_seconds=60,
            lockout_seconds=60,
        )
        self.assertIsNotNone(auth.load_password_config(accepted))

        invalid_overrides = [
            {"session_ttl_seconds": 299},
            {"session_ttl_seconds": 28_801},
            {"idle_ttl_seconds": 59},
            {"session_ttl_seconds": 300, "idle_ttl_seconds": 301},
            {"max_failed_attempts": 2},
            {"max_failed_attempts": 11},
            {"failure_window_seconds": 59},
            {"failure_window_seconds": 3_601},
            {"lockout_seconds": 59},
            {"lockout_seconds": 3_601},
            {"session_ttl_seconds": "1800"},
            {"max_failed_attempts": True},
        ]
        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                self.assertIsNone(auth.load_password_config(password_secrets(**overrides)))

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


class PasswordRateLimiterTests(unittest.TestCase):
    def config(self, **changes: object) -> auth.PasswordAuthConfig:
        base = auth.PasswordAuthConfig(password_hash=TEST_PASSWORD_HASH)
        return replace(base, **changes)

    def test_threshold_locks_and_skips_verification_until_deadline(self):
        limiter = auth._PasswordRateLimiter()
        now = [NOW]
        calls: list[int] = []

        def rejected() -> bool:
            calls.append(1)
            return False

        config = self.config(max_failed_attempts=3, lockout_seconds=60)
        self.assertFalse(limiter.attempt(config=config, clock=lambda: now[0], verifier=rejected).locked)
        self.assertFalse(limiter.attempt(config=config, clock=lambda: now[0], verifier=rejected).locked)
        threshold = limiter.attempt(config=config, clock=lambda: now[0], verifier=rejected)
        self.assertTrue(threshold.locked)
        self.assertEqual(threshold.retry_after_seconds, 60)

        now[0] += 10
        blocked = limiter.attempt(config=config, clock=lambda: now[0], verifier=lambda: True)
        self.assertTrue(blocked.locked)
        self.assertEqual(blocked.retry_after_seconds, 50)
        self.assertEqual(len(calls), 3)

        now[0] += 50
        accepted = limiter.attempt(config=config, clock=lambda: now[0], verifier=lambda: True)
        self.assertTrue(accepted.authenticated)

    def test_failure_window_success_and_config_rotation_reset_history(self):
        limiter = auth._PasswordRateLimiter()
        now = [NOW]
        config = self.config(
            max_failed_attempts=3,
            failure_window_seconds=60,
            lockout_seconds=60,
        )
        reject = lambda: False
        limiter.attempt(config=config, clock=lambda: now[0], verifier=reject)
        now[0] += 61
        limiter.attempt(config=config, clock=lambda: now[0], verifier=reject)
        self.assertFalse(limiter.attempt(config=config, clock=lambda: now[0], verifier=reject).locked)

        self.assertTrue(
            limiter.attempt(config=config, clock=lambda: now[0], verifier=lambda: True).authenticated
        )
        limiter.attempt(config=config, clock=lambda: now[0], verifier=reject)
        self.assertFalse(limiter.attempt(config=config, clock=lambda: now[0], verifier=reject).locked)

        limiter.attempt(config=config, clock=lambda: now[0], verifier=reject)
        self.assertTrue(limiter.attempt(config=config, clock=lambda: now[0], verifier=reject).locked)
        rotated = replace(config, password_hash=TEST_PASSWORD_HASH + "rotated")
        self.assertTrue(
            limiter.attempt(config=rotated, clock=lambda: now[0], verifier=lambda: True).authenticated
        )

    def test_parallel_attempts_are_serialized_under_one_global_threshold(self):
        limiter = auth._PasswordRateLimiter()
        config = self.config(max_failed_attempts=3, lockout_seconds=60)
        verifier_calls: list[int] = []

        def rejected() -> bool:
            verifier_calls.append(1)
            return False

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: limiter.attempt(
                        config=config,
                        clock=lambda: NOW,
                        verifier=rejected,
                    ),
                    range(8),
                )
            )
        self.assertEqual(len(verifier_calls), 3)
        self.assertEqual(sum(result.locked for result in results), 6)


class StreamlitWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        auth._password_rate_limiter.cache_clear()

    def test_current_claims_returns_detached_claims_and_login_attribute(self):
        original = {"iss": "https://issuer.example", "sub": "admin-subject-123"}
        fake = FakeStreamlit(user=FakeUser(original, logged_in=True))
        with patch("admin_auth._streamlit", return_value=fake):
            claims = auth.current_claims()

        self.assertEqual(claims["iss"], "https://issuer.example")
        self.assertIs(claims["is_logged_in"], True)
        claims["iss"] = "changed"
        self.assertEqual(original["iss"], "https://issuer.example")

    def test_current_oidc_state_reads_feature_and_allow_list_from_server_config(self):
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

    def test_recovery_binding_is_stable_opaque_and_authorized_identity_bound(self):
        secrets = configured_secrets()
        secrets[auth.FEATURE_FLAG] = True
        first = FakeStreamlit(
            secrets=secrets,
            user=FakeUser(valid_claims(exp=4_000_000_000), logged_in=True),
        )
        second = FakeStreamlit(
            secrets=secrets,
            user=FakeUser(valid_claims(exp=4_000_000_000), logged_in=True),
        )

        with patch.dict(os.environ, {}, clear=True):
            with patch("admin_auth._streamlit", return_value=first):
                first_binding = auth.current_admin_recovery_binding()
            with patch("admin_auth._streamlit", return_value=second):
                second_binding = auth.current_admin_recovery_binding()

        self.assertIsNotNone(first_binding)
        self.assertEqual(first_binding, second_binding)
        assert first_binding is not None
        self.assertRegex(first_binding.identity, r"^[0-9a-f]{64}$")
        self.assertEqual(len(first_binding.key_material), 32)
        self.assertNotIn(secrets["auth"]["cookie_secret"], repr(first_binding))
        self.assertNotIn(first_binding.key_material.hex(), repr(first_binding))

        forbidden = FakeStreamlit(
            secrets=secrets,
            user=FakeUser(
                valid_claims(sub="another-identity", exp=4_000_000_000),
                logged_in=True,
            ),
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=forbidden),
        ):
            self.assertIsNone(auth.current_admin_recovery_binding())

    def test_password_recovery_binding_survives_new_authorized_server_session(self):
        first = FakeStreamlit(secrets=password_secrets())
        second = FakeStreamlit(secrets=password_secrets())

        bindings = []
        for fake in (first, second):
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("admin_auth._streamlit", return_value=fake),
                patch("admin_auth._monotonic_time", return_value=NOW),
            ):
                self.assertTrue(auth.authenticate_password(TEST_PASSWORD).authenticated)
                bindings.append(auth.current_admin_recovery_binding())

        self.assertIsNotNone(bindings[0])
        self.assertEqual(bindings[0], bindings[1])

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

    def test_disabled_and_unconfigured_states_clear_sensitive_server_state(self):
        for secrets, environ, expected in (
            (configured_secrets(), {}, auth.AdminState.DISABLED),
            ({auth.FEATURE_FLAG: True}, {}, auth.AdminState.UNCONFIGURED),
        ):
            state = {
                auth.PASSWORD_GRANT_KEY: {"secret": "stale"},
                "race_import_remote_workbook": b"sensitive",
                "public_language": "pt",
            }
            fake = FakeStreamlit(secrets=secrets, session_state=state)
            with (
                patch.dict(os.environ, environ, clear=True),
                patch("admin_auth._streamlit", return_value=fake),
            ):
                self.assertIs(auth.current_admin_state(), expected)
            self.assertEqual(state, {"public_language": "pt"})

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

    def test_login_uses_streamlit_native_oidc_only_when_fully_configured(self):
        secrets = configured_secrets()
        secrets[auth.FEATURE_FLAG] = True
        fake = FakeStreamlit(secrets=secrets)
        with patch("admin_auth._streamlit", return_value=fake):
            auth.login()
        self.assertEqual(fake.login_calls, 1)

        password_fake = FakeStreamlit(secrets=password_secrets())
        with (
            patch("admin_auth._streamlit", return_value=password_fake),
            self.assertRaisesRegex(RuntimeError, "not configured"),
        ):
            auth.login()
        self.assertEqual(password_fake.login_calls, 0)

    def test_password_mode_enabled_requires_feature_mode_hash_and_policy(self):
        for secrets, expected in (
            (password_secrets(), True),
            ({**password_secrets(), auth.FEATURE_FLAG: False}, False),
            ({auth.FEATURE_FLAG: True, "admin_auth": {"mode": "password"}}, False),
            ({auth.FEATURE_FLAG: True, "admin_auth": {"mode": "oidc", "password_hash": TEST_PASSWORD_HASH}}, False),
        ):
            fake = FakeStreamlit(secrets=secrets)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("admin_auth._streamlit", return_value=fake),
            ):
                self.assertIs(auth.password_mode_enabled(), expected)

    def test_password_authentication_installs_no_plaintext_or_hash_in_session(self):
        fake = FakeStreamlit(
            secrets=password_secrets(),
            session_state={"race_import_draft": {"sensitive": True}},
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
            patch("admin_auth._monotonic_time", return_value=NOW),
        ):
            result = auth.authenticate_password(TEST_PASSWORD)
            self.assertTrue(result.authenticated)
            self.assertIs(auth.current_admin_state(), auth.AdminState.AUTHORIZED)

        serialized = repr(fake.session_state)
        self.assertNotIn(TEST_PASSWORD, serialized)
        self.assertNotIn(TEST_PASSWORD_HASH, serialized)
        self.assertNotIn("race_import_draft", fake.session_state)
        self.assertIn(auth.PASSWORD_GRANT_KEY, fake.session_state)

    def test_wrong_password_is_generic_clears_stale_grant_and_rate_limits(self):
        secrets = password_secrets(
            max_failed_attempts=3,
            lockout_seconds=60,
        )
        fake = FakeStreamlit(
            secrets=secrets,
            session_state={
                auth.PASSWORD_GRANT_KEY: {"stale": True},
                "race_import_files": [b"sensitive"],
            },
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
            patch("admin_auth._monotonic_time", return_value=NOW),
        ):
            first = auth.authenticate_password("wrong-one")
            second = auth.authenticate_password("wrong-two")
            third = auth.authenticate_password("wrong-three")
            blocked_correct = auth.authenticate_password(TEST_PASSWORD)

        self.assertEqual(first, auth.PasswordAuthResult(False, False, 0))
        self.assertEqual(second, auth.PasswordAuthResult(False, False, 0))
        self.assertTrue(third.locked)
        self.assertTrue(blocked_correct.locked)
        self.assertFalse(blocked_correct.authenticated)
        self.assertNotIn(auth.PASSWORD_GRANT_KEY, fake.session_state)
        self.assertFalse(any(str(key).startswith("race_import_") for key in fake.session_state))
        self.assertNotIn("wrong", repr((first, second, third, blocked_correct)))

    def test_password_sessions_are_isolated(self):
        first = FakeStreamlit(secrets=password_secrets())
        second = FakeStreamlit(secrets=password_secrets())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._monotonic_time", return_value=NOW),
            patch("admin_auth._streamlit", return_value=first),
        ):
            self.assertTrue(auth.authenticate_password(TEST_PASSWORD).authenticated)
            self.assertIs(auth.current_admin_state(), auth.AdminState.AUTHORIZED)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._monotonic_time", return_value=NOW),
            patch("admin_auth._streamlit", return_value=second),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.ANONYMOUS)

    def test_password_grant_idle_absolute_and_config_rotation_expire_and_clear(self):
        cases = (
            (password_secrets(session_ttl_seconds=300, idle_ttl_seconds=60), 60.0),
            (password_secrets(session_ttl_seconds=300, idle_ttl_seconds=300), 300.0),
        )
        for secrets, elapsed in cases:
            with self.subTest(elapsed=elapsed):
                auth._password_rate_limiter.cache_clear()
                fake = FakeStreamlit(secrets=secrets)
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("admin_auth._streamlit", return_value=fake),
                    patch("admin_auth._monotonic_time", return_value=NOW),
                ):
                    self.assertTrue(auth.authenticate_password(TEST_PASSWORD).authenticated)
                fake.session_state["race_import_remote_workbook"] = b"sensitive"
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("admin_auth._streamlit", return_value=fake),
                    patch("admin_auth._monotonic_time", return_value=NOW + elapsed),
                ):
                    self.assertIs(auth.current_admin_state(), auth.AdminState.EXPIRED)
                self.assertEqual(fake.session_state, {})

        auth._password_rate_limiter.cache_clear()
        fake = FakeStreamlit(secrets=password_secrets())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
            patch("admin_auth._monotonic_time", return_value=NOW),
        ):
            self.assertTrue(auth.authenticate_password(TEST_PASSWORD).authenticated)
        fake.secrets = password_secrets(idle_ttl_seconds=600)
        fake.session_state["race_import_draft"] = {"sensitive": True}
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("admin_auth._streamlit", return_value=fake),
            patch("admin_auth._monotonic_time", return_value=NOW + 1),
        ):
            self.assertIs(auth.current_admin_state(), auth.AdminState.EXPIRED)
        self.assertEqual(fake.session_state, {})

    def test_clear_state_helpers_remove_owned_keys_only(self):
        state: dict[object, object] = {
            "race_import_files": ["one.png"],
            "race_import_review": {"approved": False},
            auth.PASSWORD_GRANT_KEY: {"issued_at": NOW},
            "admin_auth_form": "owned",
            "dashboard_filter": "2026",
            7: "non-string-key",
        }
        removed_imports = auth.clear_race_import_state(state)
        removed_auth = auth.clear_admin_session_state(state)
        self.assertCountEqual(removed_imports, ("race_import_files", "race_import_review"))
        self.assertCountEqual(removed_auth, (auth.PASSWORD_GRANT_KEY, "admin_auth_form"))
        self.assertEqual(state, {"dashboard_filter": "2026", 7: "non-string-key"})

    def test_oidc_logout_clears_all_sensitive_state_before_native_logout(self):
        secrets = configured_secrets()
        state: dict[object, object] = {
            "race_import_files": [b"sensitive screenshot"],
            auth.PASSWORD_GRANT_KEY: {"stale": True},
            "public_language": "pt",
        }
        fake = FakeStreamlit(secrets=secrets, session_state=state)

        def assert_cleared_then_logout() -> None:
            self.assertEqual(fake.session_state, {"public_language": "pt"})
            fake.logout_calls += 1

        fake.logout = assert_cleared_then_logout  # type: ignore[method-assign]
        with patch("admin_auth._streamlit", return_value=fake):
            auth.logout()

        self.assertEqual(fake.logout_calls, 1)
        self.assertEqual(fake.rerun_calls, 0)

    def test_password_logout_clears_grant_importer_and_reruns_without_oidc(self):
        state: dict[object, object] = {
            auth.PASSWORD_GRANT_KEY: {"issued_at": NOW},
            "admin_auth_transient": "owned",
            "race_import_remote_workbook": b"sensitive",
            "public_language": "pt",
        }
        fake = FakeStreamlit(secrets=password_secrets(), session_state=state)
        with patch("admin_auth._streamlit", return_value=fake):
            auth.logout()

        self.assertEqual(fake.session_state, {"public_language": "pt"})
        self.assertEqual(fake.rerun_calls, 1)
        self.assertEqual(fake.logout_calls, 0)


if __name__ == "__main__":
    unittest.main()
