"""Server-side authorization for the race-import administration area.

Authentication is delegated to Streamlit's native OpenID Connect support.  This
module adds the authorization decision that OIDC deliberately does not provide:
only one configured issuer/subject identity is allowed to use the importer.

The allow-list lives in ``st.secrets["admin_auth"]``.  No identity values or
credentials have defaults, so a missing or malformed configuration fails closed.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Any


FEATURE_FLAG = "F1_ENABLE_RACE_IMPORT"
SESSION_STATE_PREFIX = "race_import_"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_MISSING = object()
_OIDC_REQUIRED_FIELDS = (
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
)


class AdminState(str, Enum):
    """The complete set of externally useful admin authorization states."""

    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"
    ANONYMOUS = "anonymous"
    FORBIDDEN = "forbidden"
    EXPIRED = "expired"
    AUTHORIZED = "authorized"


@dataclass(frozen=True, slots=True)
class AdminAuthConfig:
    """Exact OIDC identity allow-list loaded from Streamlit secrets."""

    allowed_issuer: str
    allowed_subject: str
    allowed_email: str | None = None


def _mapping_value(mapping: object, key: str, default: Any = _MISSING) -> Any:
    """Read a mapping-like Streamlit secrets object without attribute access."""

    if not isinstance(mapping, Mapping):
        return default
    try:
        return mapping[key]
    except Exception:
        # Streamlit's secrets proxy can raise StreamlitSecretNotFoundError (not
        # KeyError) when no secrets source exists.  Configuration reads are a
        # trust boundary, so any lookup failure must resolve to "not configured".
        return default


def _is_exact_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_example_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return normalized.startswith("YOUR-") or normalized.startswith("GENERATE-")


def oidc_is_configured(secrets: object) -> bool:
    """Validate the unnamed OIDC provider without exposing any secret values."""

    section = _mapping_value(secrets, "auth")
    if not isinstance(section, Mapping):
        return False
    for field in _OIDC_REQUIRED_FIELDS:
        value = _mapping_value(section, field)
        if not _is_exact_nonempty_string(value) or _is_example_placeholder(value):
            return False
    cookie_secret = _mapping_value(section, "cookie_secret")
    if len(cookie_secret) < 32:
        return False
    # Access/refresh tokens are unnecessary for identity-only authorization.
    # Refuse an accidental opt-in instead of making powerful tokens available
    # to application code or the session state surface.
    if _mapping_value(section, "expose_tokens", False) is not False:
        return False
    return True


def load_admin_config(secrets: object) -> AdminAuthConfig | None:
    """Parse ``[admin_auth]`` from a secrets mapping, or fail closed.

    Required configuration::

        [admin_auth]
        allowed_issuer = "https://issuer.example"
        allowed_subject = "provider-stable-user-id"

    ``allowed_email`` may be added as a second exact identity constraint.  When
    it is configured, :func:`evaluate_admin_state` also requires the OIDC claim
    ``email_verified`` to be the boolean value ``true``.
    """

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
    if email is not None and not _is_exact_nonempty_string(email):
        return None

    return AdminAuthConfig(
        allowed_issuer=issuer,
        allowed_subject=subject,
        allowed_email=email,
    )


def _flag_value_is_enabled(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _TRUE_VALUES
    # Accept the conventional integer 1, but do not accept arbitrary truthy
    # objects or floats from a malformed secrets configuration.
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


def race_import_enabled(
    *,
    environ: Mapping[str, str] | None = None,
    secrets: object = None,
) -> bool:
    """Return whether the importer was explicitly enabled.

    An environment value takes precedence when present.  Otherwise the same
    key may be set at the top level of ``st.secrets``.  Missing, false, and
    malformed values all disable the feature.
    """

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
    """Validate an OIDC NumericDate without treating booleans as numbers."""

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
    """Make a deterministic, fail-closed admin authorization decision.

    ``exp`` is required and is expired at its exact NumericDate boundary.
    ``nbf`` is optional per OIDC/JWT conventions, but when supplied it must be
    a valid NumericDate that is no later than ``now``.  There is intentionally
    no application-level clock-skew grace period.
    """

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


def _streamlit() -> Any:
    """Return Streamlit at the single mockable boundary used by wrappers."""

    import streamlit as st

    return st


def _runtime_secrets(st: object) -> object:
    try:
        return getattr(st, "secrets")
    except Exception:
        # Streamlit raises when no secrets file/configuration exists.  At this
        # trust boundary, every such failure must leave the admin gate closed.
        return None


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


def current_admin_state() -> AdminState:
    """Evaluate the current request/session using only server-side state."""

    st = _streamlit()
    secrets = _runtime_secrets(st)
    if not race_import_enabled(secrets=secrets):
        return AdminState.DISABLED

    config = load_admin_config(secrets)
    if config is None or not oidc_is_configured(secrets):
        return AdminState.UNCONFIGURED

    try:
        user = getattr(st, "user")
    except Exception:
        claims: Mapping[str, object] = {}
    else:
        claims = _claims_from_user(user)

    return evaluate_admin_state(
        enabled=True,
        config=config,
        claims=claims,
        now=time.time(),
    )


def is_current_admin() -> bool:
    """Return true only for the exactly authorized current OIDC identity."""

    return current_admin_state() is AdminState.AUTHORIZED


def login() -> None:
    """Start Streamlit's native OIDC login flow."""

    _streamlit().login()


def clear_race_import_state(session_state: MutableMapping[object, object]) -> tuple[str, ...]:
    """Delete all importer-owned session values and return their string keys."""

    keys = tuple(
        key
        for key in list(session_state.keys())
        if isinstance(key, str) and key.startswith(SESSION_STATE_PREFIX)
    )
    for key in keys:
        del session_state[key]
    return keys


def logout() -> None:
    """Clear sensitive importer state, then end the native OIDC session."""

    st = _streamlit()
    clear_race_import_state(st.session_state)
    st.logout()
