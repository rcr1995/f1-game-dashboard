"""Fail-closed server-side authorization for the race-import Admin area.

Two explicit authentication modes are supported:

* ``oidc`` delegates authentication to Streamlit's native OpenID Connect flow
  and authorizes one exact issuer/subject identity.
* ``password`` verifies one high-entropy administrator password against a
  server-side Argon2id hash, with a process-global brute-force limiter and a
  short-lived, server-side Streamlit session grant.

There is deliberately no automatic fallback between modes. Missing, malformed,
placeholder, or weak configuration always leaves Admin closed.
"""

from __future__ import annotations

from base64 import b64decode
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from hashlib import sha256
import math
import os
import re
from numbers import Real
from threading import RLock
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


FEATURE_FLAG = "F1_ENABLE_RACE_IMPORT"
SESSION_STATE_PREFIX = "race_import_"
ADMIN_SESSION_STATE_PREFIX = "admin_auth_"
PASSWORD_GRANT_KEY = f"{ADMIN_SESSION_STATE_PREFIX}password_grant"

DEFAULT_SESSION_TTL_SECONDS = 1_800
DEFAULT_IDLE_TTL_SECONDS = 900
DEFAULT_MAX_FAILED_ATTEMPTS = 5
DEFAULT_FAILURE_WINDOW_SECONDS = 900
DEFAULT_LOCKOUT_SECONDS = 900

_MIN_SESSION_TTL_SECONDS = 300
_MAX_SESSION_TTL_SECONDS = 28_800
_MIN_IDLE_TTL_SECONDS = 60
_MIN_MAX_FAILED_ATTEMPTS = 3
_MAX_MAX_FAILED_ATTEMPTS = 10
_MIN_FAILURE_WINDOW_SECONDS = 60
_MAX_FAILURE_WINDOW_SECONDS = 3_600
_MIN_LOCKOUT_SECONDS = 60
_MAX_LOCKOUT_SECONDS = 3_600

_MIN_ARGON2_MEMORY_KIB = 65_536
_MAX_ARGON2_MEMORY_KIB = 262_144
_MIN_ARGON2_TIME_COST = 3
_MAX_ARGON2_TIME_COST = 10
_MIN_ARGON2_PARALLELISM = 1
_MAX_ARGON2_PARALLELISM = 8
_MIN_ARGON2_SALT_BYTES = 16
_MIN_ARGON2_HASH_BYTES = 32
_MAX_PASSWORD_UTF8_BYTES = 4_096

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_MISSING = object()
_OIDC_REQUIRED_FIELDS = (
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
)
_ARGON2ID_PATTERN = re.compile(
    r"\$argon2id\$v=(?P<version>\d+)\$"
    r"m=(?P<memory>\d+),t=(?P<time>\d+),p=(?P<parallelism>\d+)\$"
    r"(?P<salt>[A-Za-z0-9+/]+)\$(?P<digest>[A-Za-z0-9+/]+)"
)
_PASSWORD_HASHER = PasswordHasher()


class AdminState(str, Enum):
    """The complete set of externally useful admin authorization states."""

    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"
    ANONYMOUS = "anonymous"
    FORBIDDEN = "forbidden"
    EXPIRED = "expired"
    AUTHORIZED = "authorized"


class AdminAuthMode(str, Enum):
    """Explicitly configured authentication mechanisms."""

    OIDC = "oidc"
    PASSWORD = "password"


@dataclass(frozen=True, slots=True)
class AdminAuthConfig:
    """Exact OIDC identity allow-list loaded from Streamlit secrets."""

    allowed_issuer: str
    allowed_subject: str
    allowed_email: str | None = None


@dataclass(frozen=True, slots=True)
class PasswordAuthConfig:
    """Validated password authentication and session policy."""

    password_hash: str = field(repr=False)
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS
    max_failed_attempts: int = DEFAULT_MAX_FAILED_ATTEMPTS
    failure_window_seconds: int = DEFAULT_FAILURE_WINDOW_SECONDS
    lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS


@dataclass(frozen=True, slots=True)
class PasswordAuthResult:
    """Public, credential-free result of one password attempt."""

    authenticated: bool
    locked: bool
    retry_after_seconds: int = 0


@dataclass(frozen=True, slots=True)
class AdminRecoveryBinding:
    """Opaque identity and key material for an authorized browser recovery copy.

    The key material is derived only on the server and must never be sent to a
    component or included in a persisted draft.
    """

    identity: str
    key_material: bytes = field(repr=False)


def _mapping_value(mapping: object, key: str, default: Any = _MISSING) -> Any:
    """Read a mapping-like Streamlit secrets object without attribute access."""

    if not isinstance(mapping, Mapping):
        return default
    try:
        return mapping[key]
    except Exception:
        # Streamlit's secrets proxy can raise StreamlitSecretNotFoundError (not
        # KeyError) when no secrets source exists. Any failure must fail closed.
        return default


def _is_exact_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_example_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return (
        normalized.startswith("YOUR-")
        or normalized.startswith("YOUR_")
        or normalized.startswith("GENERATE-")
        or normalized.startswith("REPLACE-")
    )


def load_auth_mode(secrets: object) -> AdminAuthMode | None:
    """Return the explicit authentication mode, or ``None`` on any ambiguity."""

    section = _mapping_value(secrets, "admin_auth")
    if not isinstance(section, Mapping):
        return None
    value = _mapping_value(section, "mode")
    if not _is_exact_nonempty_string(value):
        return None
    try:
        return AdminAuthMode(value)
    except ValueError:
        return None


def oidc_is_configured(secrets: object) -> bool:
    """Validate the unnamed OIDC provider without exposing secret values."""

    section = _mapping_value(secrets, "auth")
    if not isinstance(section, Mapping):
        return False
    for required_field in _OIDC_REQUIRED_FIELDS:
        value = _mapping_value(section, required_field)
        if not _is_exact_nonempty_string(value) or _is_example_placeholder(value):
            return False
    cookie_secret = _mapping_value(section, "cookie_secret")
    if len(cookie_secret) < 32:
        return False
    # Access/refresh tokens are unnecessary for identity-only authorization.
    if _mapping_value(section, "expose_tokens", False) is not False:
        return False
    return True


def load_admin_config(secrets: object) -> AdminAuthConfig | None:
    """Parse the exact OIDC allow-list, or fail closed."""

    if load_auth_mode(secrets) is not AdminAuthMode.OIDC:
        return None
    section = _mapping_value(secrets, "admin_auth")
    if not isinstance(section, Mapping):
        return None

    issuer = _mapping_value(section, "allowed_issuer")
    subject = _mapping_value(section, "allowed_subject")
    email = _mapping_value(section, "allowed_email", None)

    if not _is_exact_nonempty_string(issuer) or _is_example_placeholder(issuer):
        return None
    if not _is_exact_nonempty_string(subject) or _is_example_placeholder(subject):
        return None
    if email is not None and (
        not _is_exact_nonempty_string(email) or _is_example_placeholder(email)
    ):
        return None

    return AdminAuthConfig(
        allowed_issuer=issuer,
        allowed_subject=subject,
        allowed_email=email,
    )


def _decode_argon2_segment(value: str) -> bytes | None:
    try:
        return b64decode(value + ("=" * (-len(value) % 4)), validate=True)
    except (TypeError, ValueError):
        return None


def _argon2id_hash_is_secure(value: object) -> bool:
    if not _is_exact_nonempty_string(value) or _is_example_placeholder(value):
        return False
    match = _ARGON2ID_PATTERN.fullmatch(value)
    if match is None:
        return False
    try:
        version = int(match.group("version"))
        memory_cost = int(match.group("memory"))
        time_cost = int(match.group("time"))
        parallelism = int(match.group("parallelism"))
    except (TypeError, ValueError):
        return False

    salt = _decode_argon2_segment(match.group("salt"))
    digest = _decode_argon2_segment(match.group("digest"))
    return bool(
        version == 19
        and _MIN_ARGON2_MEMORY_KIB <= memory_cost <= _MAX_ARGON2_MEMORY_KIB
        and _MIN_ARGON2_TIME_COST <= time_cost <= _MAX_ARGON2_TIME_COST
        and _MIN_ARGON2_PARALLELISM <= parallelism <= _MAX_ARGON2_PARALLELISM
        and salt is not None
        and len(salt) >= _MIN_ARGON2_SALT_BYTES
        and digest is not None
        and len(digest) >= _MIN_ARGON2_HASH_BYTES
    )


def _bounded_policy_integer(
    section: object,
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int | None:
    value = _mapping_value(section, name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if minimum <= value <= maximum else None


def load_password_config(secrets: object) -> PasswordAuthConfig | None:
    """Parse a strong Argon2id password configuration, or fail closed."""

    if load_auth_mode(secrets) is not AdminAuthMode.PASSWORD:
        return None
    section = _mapping_value(secrets, "admin_auth")
    if not isinstance(section, Mapping):
        return None
    password_hash = _mapping_value(section, "password_hash")
    if not _argon2id_hash_is_secure(password_hash):
        return None

    session_ttl = _bounded_policy_integer(
        section,
        "session_ttl_seconds",
        default=DEFAULT_SESSION_TTL_SECONDS,
        minimum=_MIN_SESSION_TTL_SECONDS,
        maximum=_MAX_SESSION_TTL_SECONDS,
    )
    idle_ttl = _bounded_policy_integer(
        section,
        "idle_ttl_seconds",
        default=DEFAULT_IDLE_TTL_SECONDS,
        minimum=_MIN_IDLE_TTL_SECONDS,
        maximum=_MAX_SESSION_TTL_SECONDS,
    )
    max_attempts = _bounded_policy_integer(
        section,
        "max_failed_attempts",
        default=DEFAULT_MAX_FAILED_ATTEMPTS,
        minimum=_MIN_MAX_FAILED_ATTEMPTS,
        maximum=_MAX_MAX_FAILED_ATTEMPTS,
    )
    failure_window = _bounded_policy_integer(
        section,
        "failure_window_seconds",
        default=DEFAULT_FAILURE_WINDOW_SECONDS,
        minimum=_MIN_FAILURE_WINDOW_SECONDS,
        maximum=_MAX_FAILURE_WINDOW_SECONDS,
    )
    lockout = _bounded_policy_integer(
        section,
        "lockout_seconds",
        default=DEFAULT_LOCKOUT_SECONDS,
        minimum=_MIN_LOCKOUT_SECONDS,
        maximum=_MAX_LOCKOUT_SECONDS,
    )
    if (
        session_ttl is None
        or idle_ttl is None
        or idle_ttl > session_ttl
        or max_attempts is None
        or failure_window is None
        or lockout is None
    ):
        return None

    return PasswordAuthConfig(
        password_hash=password_hash,
        session_ttl_seconds=session_ttl,
        idle_ttl_seconds=idle_ttl,
        max_failed_attempts=max_attempts,
        failure_window_seconds=failure_window,
        lockout_seconds=lockout,
    )


def _flag_value_is_enabled(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _TRUE_VALUES
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


def race_import_enabled(
    *,
    environ: Mapping[str, str] | None = None,
    secrets: object = None,
) -> bool:
    """Return whether the importer was explicitly enabled."""

    environment = os.environ if environ is None else environ
    try:
        if FEATURE_FLAG in environment:
            return _flag_value_is_enabled(environment[FEATURE_FLAG])
    except (KeyError, TypeError):
        return False

    secret_value = _mapping_value(secrets, FEATURE_FLAG)
    if secret_value is _MISSING:
        return False
    return _flag_value_is_enabled(secret_value)


def _numeric_date(value: object) -> float | None:
    """Validate a finite NumericDate without treating booleans as numbers."""

    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def evaluate_admin_state(
    *,
    enabled: bool,
    config: AdminAuthConfig | None,
    claims: Mapping[str, object] | None,
    now: Real,
) -> AdminState:
    """Make a deterministic, fail-closed OIDC authorization decision."""

    if not enabled:
        return AdminState.DISABLED
    if config is None:
        return AdminState.UNCONFIGURED
    if not isinstance(claims, Mapping) or claims.get("is_logged_in") is not True:
        return AdminState.ANONYMOUS

    if claims.get("iss") != config.allowed_issuer:
        return AdminState.FORBIDDEN
    if claims.get("sub") != config.allowed_subject:
        return AdminState.FORBIDDEN

    if config.allowed_email is not None:
        if claims.get("email") != config.allowed_email:
            return AdminState.FORBIDDEN
        if claims.get("email_verified") is not True:
            return AdminState.FORBIDDEN

    current_time = _numeric_date(now)
    expires_at = _numeric_date(claims.get("exp"))
    if current_time is None or expires_at is None:
        return AdminState.FORBIDDEN
    if current_time >= expires_at:
        return AdminState.EXPIRED

    if "nbf" in claims:
        not_before = _numeric_date(claims.get("nbf"))
        if not_before is None or current_time < not_before:
            return AdminState.FORBIDDEN

    return AdminState.AUTHORIZED


def _password_config_fingerprint(config: PasswordAuthConfig) -> str:
    policy = (
        "password-grant-v1",
        config.password_hash,
        str(config.session_ttl_seconds),
        str(config.idle_ttl_seconds),
        str(config.max_failed_attempts),
        str(config.failure_window_seconds),
        str(config.lockout_seconds),
    )
    return sha256("\0".join(policy).encode("utf-8")).hexdigest()


class _PasswordRateLimiter:
    """Thread-safe, process-global limiter for the single admin credential."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._fingerprint: str | None = None
        self._failures: list[float] = []
        self._locked_until = 0.0

    def attempt(
        self,
        *,
        config: PasswordAuthConfig,
        clock: Callable[[], float],
        verifier: Callable[[], bool],
    ) -> PasswordAuthResult:
        fingerprint = _password_config_fingerprint(config)
        with self._lock:
            now = _numeric_date(clock())
            if now is None:
                return PasswordAuthResult(False, True, config.lockout_seconds)
            if fingerprint != self._fingerprint:
                self._fingerprint = fingerprint
                self._failures.clear()
                self._locked_until = 0.0

            if now < self._locked_until:
                return PasswordAuthResult(
                    False,
                    True,
                    max(1, math.ceil(self._locked_until - now)),
                )

            cutoff = now - config.failure_window_seconds
            self._failures = [attempt for attempt in self._failures if attempt > cutoff]

            if verifier():
                self._failures.clear()
                self._locked_until = 0.0
                return PasswordAuthResult(True, False, 0)

            self._failures.append(now)
            if len(self._failures) >= config.max_failed_attempts:
                self._failures.clear()
                self._locked_until = now + config.lockout_seconds
                return PasswordAuthResult(False, True, config.lockout_seconds)
            return PasswordAuthResult(False, False, 0)


@lru_cache(maxsize=1)
def _password_rate_limiter() -> _PasswordRateLimiter:
    return _PasswordRateLimiter()


def _streamlit() -> Any:
    """Return Streamlit at the single mockable boundary used by wrappers."""

    import streamlit as st

    return st


def _runtime_secrets(st: object) -> object:
    try:
        return getattr(st, "secrets")
    except Exception:
        return None


def _runtime_session_state(st: object) -> MutableMapping[object, object] | None:
    try:
        state = getattr(st, "session_state")
    except Exception:
        return None
    return state if isinstance(state, MutableMapping) else None


def _monotonic_time() -> float:
    return time.monotonic()


def _claims_from_user(user: object) -> dict[str, object]:
    raw_claims: object
    try:
        to_dict = getattr(user, "to_dict", None)
        raw_claims = to_dict() if callable(to_dict) else user
    except Exception:
        return {}

    try:
        claims = dict(raw_claims) if isinstance(raw_claims, Mapping) else {}
    except (TypeError, ValueError):
        claims = {}

    try:
        logged_in = getattr(user, "is_logged_in")
    except Exception:
        logged_in = claims.get("is_logged_in", False)
    claims["is_logged_in"] = logged_in
    return claims


def current_claims() -> dict[str, object]:
    """Return a detached copy of the current Streamlit OIDC claims."""

    st = _streamlit()
    try:
        user = getattr(st, "user")
    except Exception:
        return {}
    return _claims_from_user(user)


def current_admin_recovery_binding() -> AdminRecoveryBinding | None:
    """Return a stable, identity-bound recovery key for the current Admin.

    Recovery is deliberately unavailable unless the normal authorization gate
    succeeds.  OIDC mode derives its key from Streamlit's private cookie secret
    and the exact allowed identity. Password mode derives it from the validated
    Argon2 verifier. Neither source value is exposed to the browser.
    """

    if current_admin_state() is not AdminState.AUTHORIZED:
        return None

    st = _streamlit()
    secrets = _runtime_secrets(st)
    mode = load_auth_mode(secrets)
    if mode is AdminAuthMode.OIDC:
        config = load_admin_config(secrets)
        auth_section = _mapping_value(secrets, "auth")
        cookie_secret = _mapping_value(auth_section, "cookie_secret")
        if config is None or not isinstance(cookie_secret, str) or not cookie_secret:
            return None
        identity_source = (
            f"oidc\0{config.allowed_issuer}\0{config.allowed_subject}"
        ).encode("utf-8")
        secret_source = cookie_secret.encode("utf-8")
    elif mode is AdminAuthMode.PASSWORD:
        config = load_password_config(secrets)
        if config is None:
            return None
        fingerprint = _password_config_fingerprint(config)
        identity_source = f"password\0{fingerprint}".encode("ascii")
        secret_source = config.password_hash.encode("utf-8")
    else:
        return None

    identity = sha256(
        b"f1-admin-review-identity-v1\0" + identity_source
    ).hexdigest()
    key_material = sha256(
        b"f1-admin-review-encryption-v1\0" + secret_source
    ).digest()
    return AdminRecoveryBinding(identity=identity, key_material=key_material)


def clear_race_import_state(
    session_state: MutableMapping[object, object],
) -> tuple[str, ...]:
    """Delete all importer-owned session values and return their string keys."""

    keys = tuple(
        key
        for key in list(session_state.keys())
        if isinstance(key, str) and key.startswith(SESSION_STATE_PREFIX)
    )
    for key in keys:
        del session_state[key]
    return keys


def clear_admin_session_state(
    session_state: MutableMapping[object, object],
) -> tuple[str, ...]:
    """Delete password grants and other authentication-owned session values."""

    keys = tuple(
        key
        for key in list(session_state.keys())
        if isinstance(key, str) and key.startswith(ADMIN_SESSION_STATE_PREFIX)
    )
    for key in keys:
        del session_state[key]
    return keys


def _clear_sensitive_session_state(
    session_state: MutableMapping[object, object],
) -> None:
    clear_race_import_state(session_state)
    clear_admin_session_state(session_state)


def _password_grant_state(
    *,
    config: PasswordAuthConfig,
    grant: object,
    now: Real,
) -> AdminState:
    if grant is _MISSING:
        return AdminState.ANONYMOUS
    if not isinstance(grant, Mapping):
        return AdminState.EXPIRED
    if grant.get("fingerprint") != _password_config_fingerprint(config):
        return AdminState.EXPIRED

    current = _numeric_date(now)
    issued_at = _numeric_date(grant.get("issued_at"))
    last_seen_at = _numeric_date(grant.get("last_seen_at"))
    if current is None or issued_at is None or last_seen_at is None:
        return AdminState.EXPIRED
    if current < issued_at or last_seen_at < issued_at or current < last_seen_at:
        return AdminState.EXPIRED
    if current >= issued_at + config.session_ttl_seconds:
        return AdminState.EXPIRED
    if current >= last_seen_at + config.idle_ttl_seconds:
        return AdminState.EXPIRED
    return AdminState.AUTHORIZED


def current_admin_state() -> AdminState:
    """Evaluate the current request/session using only server-side state."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    if not race_import_enabled(secrets=secrets):
        session_state = _runtime_session_state(st)
        if session_state is not None:
            _clear_sensitive_session_state(session_state)
        return AdminState.DISABLED

    mode = load_auth_mode(secrets)
    if mode is AdminAuthMode.OIDC:
        config = load_admin_config(secrets)
        if config is None or not oidc_is_configured(secrets):
            session_state = _runtime_session_state(st)
            if session_state is not None:
                _clear_sensitive_session_state(session_state)
            return AdminState.UNCONFIGURED
        try:
            user = getattr(st, "user")
        except Exception:
            claims: Mapping[str, object] = {}
        else:
            claims = _claims_from_user(user)
        state = evaluate_admin_state(
            enabled=True,
            config=config,
            claims=claims,
            now=time.time(),
        )
        if state is not AdminState.AUTHORIZED:
            session_state = _runtime_session_state(st)
            if session_state is not None:
                _clear_sensitive_session_state(session_state)
        return state

    if mode is AdminAuthMode.PASSWORD:
        config = load_password_config(secrets)
        session_state = _runtime_session_state(st)
        if config is None or session_state is None:
            if session_state is not None:
                _clear_sensitive_session_state(session_state)
            return AdminState.UNCONFIGURED

        grant = session_state.get(PASSWORD_GRANT_KEY, _MISSING)
        now = _monotonic_time()
        state = _password_grant_state(
            config=config,
            grant=grant,
            now=now,
        )
        if state is AdminState.AUTHORIZED:
            # Replace rather than mutate an untrusted/malformed mapping object.
            session_state[PASSWORD_GRANT_KEY] = {
                "fingerprint": _password_config_fingerprint(config),
                "issued_at": grant["issued_at"],  # type: ignore[index]
                "last_seen_at": now,
            }
        elif state is AdminState.ANONYMOUS:
            clear_race_import_state(session_state)
        else:
            _clear_sensitive_session_state(session_state)
        return state

    session_state = _runtime_session_state(st)
    if session_state is not None:
        _clear_sensitive_session_state(session_state)
    return AdminState.UNCONFIGURED


def is_current_admin() -> bool:
    """Return true only for the currently authorized server-side identity."""

    return current_admin_state() is AdminState.AUTHORIZED


def password_mode_enabled() -> bool:
    """Return whether a complete, explicitly enabled password mode is active."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    return race_import_enabled(secrets=secrets) and load_password_config(secrets) is not None


def _verify_password(config: PasswordAuthConfig, candidate: object) -> bool:
    if not isinstance(candidate, str):
        return False
    try:
        encoded = candidate.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if not encoded or len(encoded) > _MAX_PASSWORD_UTF8_BYTES:
        return False
    try:
        return _PASSWORD_HASHER.verify(config.password_hash, candidate) is True
    except (InvalidHashError, VerificationError):
        return False


def authenticate_password(candidate: str) -> PasswordAuthResult:
    """Verify one candidate and install an expiring server-side grant on success."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    session_state = _runtime_session_state(st)
    if (
        not race_import_enabled(secrets=secrets)
        or session_state is None
        or (config := load_password_config(secrets)) is None
    ):
        return PasswordAuthResult(False, False, 0)

    result = _password_rate_limiter().attempt(
        config=config,
        clock=_monotonic_time,
        verifier=lambda: _verify_password(config, candidate),
    )
    if not result.authenticated:
        session_state.pop(PASSWORD_GRANT_KEY, None)
        clear_race_import_state(session_state)
        return result

    now = _monotonic_time()
    clear_race_import_state(session_state)
    session_state[PASSWORD_GRANT_KEY] = {
        "fingerprint": _password_config_fingerprint(config),
        "issued_at": now,
        "last_seen_at": now,
    }
    return result


def login() -> None:
    """Start Streamlit's native OIDC flow only in explicit OIDC mode."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    if (
        not race_import_enabled(secrets=secrets)
        or load_admin_config(secrets) is None
        or not oidc_is_configured(secrets)
    ):
        raise RuntimeError("OIDC authentication is not configured.")
    st.login()


def logout() -> None:
    """Clear sensitive state, then end the configured authentication session."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    mode = load_auth_mode(secrets)
    session_state = _runtime_session_state(st)
    if session_state is not None:
        _clear_sensitive_session_state(session_state)

    if mode is AdminAuthMode.PASSWORD:
        st.rerun()
        return
    st.logout()
