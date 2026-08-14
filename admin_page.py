"""Protected, phone-friendly Admin route for hosted race imports.

Only Streamlit and the small authorization module are imported before the
server-side authentication decision.  GitHub access, OCR, workbook reads, and
workbook writes are therefore unreachable from an anonymous or forbidden
direct route.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

import admin_auth


APP_VERSION = "v41"
PUBLIC_DASHBOARD_URL = "https://f1-game-dashboard.streamlit.app/"
# admin_auth.logout() clears every key with the race_import_ prefix.
REMOTE_STATE_KEY = "race_import_remote_workbook"

COPY = {
    "disabled": (
        "Admin is disabled",
        "Race importing is not enabled for this deployment.",
    ),
    "unconfigured": (
        "Admin is unavailable",
        "Authentication is not fully configured. The area is closed by default.",
    ),
    "anonymous": (
        "Admin sign-in",
        "Sign in to manage race results.",
    ),
    "forbidden": (
        "Access denied",
        "This signed-in identity is not authorized to administer race results.",
    ),
    "expired": (
        "Session expired",
        "Sign out, then sign in again before continuing.",
    ),
}


def _render_password_sign_in() -> None:
    with st.form("admin_password_sign_in", clear_on_submit=True):
        password = st.text_input(
            "Admin password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Sign in", type="primary")

    if not submitted:
        return

    result = admin_auth.authenticate_password(password)
    if result.authenticated:
        # The helper installs the short-lived server-side grant.  Start a
        # fresh script run so the authoritative state check above is repeated
        # before any protected capability is imported.
        st.rerun()
    elif result.locked:
        seconds = max(1, result.retry_after_seconds)
        st.error(
            f"Too many failed attempts. Try again in {seconds} seconds.",
            icon=":material/lock_clock:",
        )
    else:
        st.error("Incorrect password.", icon=":material/error:")


def _render_closed_state(state: admin_auth.AdminState) -> None:
    title, message = COPY[state.value]
    st.title(title)
    st.info(message, icon=":material/lock:")
    if state is admin_auth.AdminState.ANONYMOUS:
        if admin_auth.password_mode_enabled():
            _render_password_sign_in()
        elif st.button("Sign in", type="primary", icon=":material/login:"):
            admin_auth.login()
    elif state in {
        admin_auth.AdminState.FORBIDDEN,
        admin_auth.AdminState.EXPIRED,
    }:
        if st.button("Sign out", icon=":material/logout:"):
            admin_auth.logout()


# This is the route's capability boundary.  Keep every GitHub/OCR/workbook
# import below it so a direct request cannot construct those capabilities.
state = admin_auth.current_admin_state()
if state is not admin_auth.AdminState.AUTHORIZED:
    _render_closed_state(state)
    st.stop()

with st.sidebar:
    if admin_auth.password_mode_enabled():
        identity = "Administrator"
    else:
        claims = admin_auth.current_claims()
        identity = claims.get("email") or claims.get("name") or "Administrator"
    st.caption(f"Signed in as {identity}")
    if st.button("Sign out", icon=":material/logout:", key="admin_logout"):
        admin_auth.logout()

# These modules construct the remote publication, OCR, and workbook-write
# capabilities.  They must remain after the authorization boundary above.
import dashboard_core as core
import race_github as github_store
import race_import_ui


st.markdown(
    """
    <style>
      .stApp { max-width: 1080px; margin: 0 auto; }
      [data-testid="stHeader"] { background: transparent; }
      @media (max-width: 640px) {
        .block-container { padding: 1rem 0.85rem 5rem; }
        h1 { font-size: 1.75rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.55rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _configuration_error() -> github_store.GitHubConfigurationError:
    return github_store.GitHubConfigurationError(
        "The hosted Admin publisher is not configured."
    )


def _secret_value(values: object, name: str) -> object:
    try:
        return values[name]  # type: ignore[index]
    except Exception as exc:
        raise _configuration_error() from exc


def _secret_text(values: object, name: str) -> str:
    value = _secret_value(values, name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise _configuration_error()
    normalized = value.upper()
    if "YOUR-" in normalized or "YOUR_" in normalized or "REPLACE-" in normalized:
        raise _configuration_error()
    return value


def _secret_identifier(values: object, name: str) -> str:
    value = _secret_value(values, name)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise _configuration_error()
    identifier = str(value).strip()
    if not identifier or "YOUR" in identifier.upper() or "REPLACE" in identifier.upper():
        raise _configuration_error()
    return identifier


def _repository_name(values: object) -> str:
    try:
        return _secret_text(values, "repository")
    except github_store.GitHubConfigurationError:
        # Keep compatibility with the upstream updater's documented `repo`
        # alias, while still requiring one explicit repository value.
        return _secret_text(values, "repo")


def github_config_from_secrets() -> github_store.GitHubAppConfig:
    """Build a complete GitHub App configuration or fail closed."""

    try:
        values = st.secrets["github"]
    except Exception as exc:
        raise _configuration_error() from exc

    installation_value = _secret_value(values, "installation_id")
    if isinstance(installation_value, bool):
        raise _configuration_error()
    try:
        installation_id = int(installation_value)
    except (TypeError, ValueError) as exc:
        raise _configuration_error() from exc
    if installation_id <= 0:
        raise _configuration_error()

    return github_store.GitHubAppConfig(
        app_id=_secret_identifier(values, "app_id"),
        installation_id=installation_id,
        private_key=_secret_text(values, "private_key"),
        owner=_secret_text(values, "owner"),
        repository=_repository_name(values),
        branch=_secret_text(values, "branch"),
        workbook_path=_secret_text(values, "workbook_path"),
    )


def _require_current_admin() -> None:
    """Recheck authorization immediately before a protected callback."""

    if not admin_auth.is_current_admin():
        st.error("Admin authorization expired. Sign out, then sign in again.")
        st.stop()


def _load_remote(config: github_store.GitHubAppConfig) -> dict[str, object]:
    _require_current_admin()
    with st.spinner("Loading the latest workbook from GitHub…"):
        remote = github_store.fetch_remote_workbook(config)
    return asdict(remote)


def _clear_remote_snapshot() -> None:
    st.session_state.pop(REMOTE_STATE_KEY, None)


language_name = st.selectbox(
    "Idioma / Language",
    ["Português", "English"],
    key="admin_language",
)
lang = "pt" if language_name == "Português" else "en"

header_columns = st.columns([3, 1])
header_columns[0].title("🏁 F1 Race Updater")
header_columns[0].caption(
    "Atualizador privado · telemóvel ou computador"
    if lang == "pt"
    else "Private updater · phone or computer"
)
header_columns[1].link_button(
    "Abrir dashboard" if lang == "pt" else "Open dashboard",
    PUBLIC_DASHBOARD_URL,
    use_container_width=True,
)

try:
    config = github_config_from_secrets()
except (github_store.GitHubConfigurationError, ValueError, TypeError):
    st.error(
        "As atualizações estão temporariamente indisponíveis. Nenhum dado pode ser alterado."
        if lang == "pt"
        else "Updates are temporarily unavailable. No data can be changed."
    )
    st.caption(f"{APP_VERSION} · secure GitHub configuration required")
    st.stop()

refresh_clicked = st.button(
    "↻ Carregar Excel mais recente" if lang == "pt" else "↻ Load latest workbook",
    use_container_width=True,
)
if refresh_clicked:
    # Clear the remote snapshot together with drafts, approvals, upload state,
    # and other importer-owned values before constructing a fresh review.
    admin_auth.clear_race_import_state(st.session_state)

try:
    if REMOTE_STATE_KEY not in st.session_state:
        st.session_state[REMOTE_STATE_KEY] = _load_remote(config)
    remote_state = st.session_state[REMOTE_STATE_KEY]
    if not isinstance(remote_state, dict):
        raise TypeError("invalid remote state")
    remote_content_value = remote_state["content"]
    if not isinstance(remote_content_value, (bytes, bytearray)):
        raise TypeError("invalid remote content")
    remote_content = bytes(remote_content_value)
    remote_blob_sha = str(remote_state["blob_sha"])
except (github_store.GitHubPersistenceError, KeyError, TypeError, ValueError):
    _clear_remote_snapshot()
    st.error(
        "Não foi possível carregar o Excel do GitHub. Tenta novamente mais tarde; nenhum dado foi alterado."
        if lang == "pt"
        else "The GitHub workbook could not be loaded. Try again later; no data was changed."
    )
    st.stop()


def _publish(
    metadata,
    rows: list[dict],
    scoring_profile: dict[int, float],
    expected_source_version: str,
    approved: bool,
):
    _require_current_admin()
    try:
        return github_store.publish_race_import(
            config,
            metadata=metadata,
            rows=rows,
            scoring_profile=scoring_profile,
            expected_blob_sha=expected_source_version,
            approved=approved,
            commit_message=(
                f"Import {metadata.event_type} results: {metadata.gp_name} "
                f"(round {metadata.round_number})"
            ),
        )
    except github_store.GitHubConflictError:
        # A stale blob must never remain available for another approval click.
        _clear_remote_snapshot()
        raise


with TemporaryDirectory(prefix="f1-race-review-") as temporary_directory:
    workbook_path = Path(temporary_directory) / Path(config.workbook_path).name
    workbook_path.write_bytes(remote_content)
    try:
        for warning in core.validate_workbook(workbook_path):
            st.warning(warning)
        standings = core.load_standings_data(workbook_path)
        calendar = core.load_calendar_data(workbook_path)
    except (core.WorkbookValidationError, OSError, ValueError):
        st.error(
            "O Excel remoto não passou a validação. Nenhum dado pode ser publicado."
            if lang == "pt"
            else "The remote workbook did not pass validation. No data can be published."
        )
        st.stop()

    race_import_ui.render_race_import(
        str(workbook_path),
        standings,
        calendar,
        lang=lang,
        clear_data_cache=_clear_remote_snapshot,
        source_version=remote_blob_sha,
        hosted_publisher=_publish,
        dashboard_url=PUBLIC_DASHBOARD_URL,
    )

st.caption(f"{APP_VERSION} · private updater")
