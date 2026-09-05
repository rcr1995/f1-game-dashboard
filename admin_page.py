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
import hosted_settings
import review_draft_recovery
import ui_preferences


APP_VERSION = "v49"
PUBLIC_DASHBOARD_URL = hosted_settings.dashboard_url()
# admin_auth.logout() clears every key with the race_import_ prefix.
REMOTE_STATE_KEY = "race_import_remote_workbook"
DOWNLOAD_STATE_KEY = "race_import_download_workbook"

LANGUAGE_NAMES = ui_preferences.LANGUAGE_NAMES

COPY = {
    "en": {
        "disabled": (
            "Admin is disabled",
            "Race importing is not enabled for this deployment.",
        ),
        "unconfigured": (
            "Admin is unavailable",
            "Authentication is not fully configured. The area is closed by default.",
        ),
        "anonymous": ("Admin sign-in", "Sign in to manage race results."),
        "forbidden": (
            "Access denied",
            "This signed-in identity is not authorized to administer race results.",
        ),
        "expired": (
            "Session expired",
            "Sign out, then sign in again before continuing.",
        ),
        "password": "Admin password",
        "sign_in": "Sign in",
        "sign_out": "Sign out",
        "too_many": "Too many failed attempts. Try again in {seconds} seconds.",
        "incorrect": "Incorrect password.",
        "administrator": "Administrator",
        "signed_in": "Signed in as {identity}",
        "authorization_expired": "Admin authorization expired. Sign out, then sign in again.",
        "loading_latest": "Loading the latest workbook from GitHub…",
        "private_updater": "Private updater · phone or computer",
        "open_dashboard": "Open dashboard",
        "updates_unavailable": "Updates are temporarily unavailable. No data can be changed.",
        "secure_config": "secure GitHub configuration required",
        "load_latest": "↻ Load latest workbook",
        "prepare_download": "↓ Get latest Excel",
        "download_workbook": "Download {filename}",
        "download_workbook_help": (
            "Download the exact workbook version fetched from GitHub for this download."
        ),
        "download_workbook_error": "The latest GitHub workbook could not be prepared for download. No data was changed.",
        "workbook_load_error": "The GitHub workbook could not be loaded. Try again later; no data was changed.",
        "workbook_validation_error": "The remote workbook did not pass validation. No data can be published.",
        "footer": "private updater",
        "clearing_review": "Clearing the saved review securely…",
    },
    "pt": {
        "disabled": (
            "Administração desativada",
            "A importação de corridas não está ativa nesta instalação.",
        ),
        "unconfigured": (
            "Administração indisponível",
            "A autenticação não está totalmente configurada. A área permanece fechada por segurança.",
        ),
        "anonymous": (
            "Iniciar sessão na administração",
            "Inicia sessão para gerir os resultados das corridas.",
        ),
        "forbidden": (
            "Acesso recusado",
            "A identidade autenticada não está autorizada a administrar resultados.",
        ),
        "expired": (
            "Sessão expirada",
            "Termina a sessão e volta a entrar antes de continuar.",
        ),
        "password": "Palavra-passe de administração",
        "sign_in": "Iniciar sessão",
        "sign_out": "Terminar sessão",
        "too_many": "Demasiadas tentativas falhadas. Tenta novamente dentro de {seconds} segundos.",
        "incorrect": "Palavra-passe incorreta.",
        "administrator": "Administrador",
        "signed_in": "Sessão iniciada como {identity}",
        "authorization_expired": "A autorização de administração expirou. Termina a sessão e volta a entrar.",
        "loading_latest": "A carregar o Excel mais recente do GitHub…",
        "private_updater": "Atualizador privado · telemóvel ou computador",
        "open_dashboard": "Abrir dashboard",
        "updates_unavailable": "As atualizações estão temporariamente indisponíveis. Nenhum dado pode ser alterado.",
        "secure_config": "configuração segura do GitHub obrigatória",
        "load_latest": "↻ Carregar Excel mais recente",
        "prepare_download": "↓ Obter Excel mais recente",
        "download_workbook": "Descarregar {filename}",
        "download_workbook_help": (
            "Descarrega a versão exata do Excel obtida do GitHub para esta transferência."
        ),
        "download_workbook_error": "Não foi possível preparar o Excel mais recente do GitHub para transferência. Nenhum dado foi alterado.",
        "workbook_load_error": "Não foi possível carregar o Excel do GitHub. Tenta novamente mais tarde; nenhum dado foi alterado.",
        "workbook_validation_error": "O Excel remoto não passou a validação. Nenhum dado pode ser publicado.",
        "footer": "atualizador privado",
        "clearing_review": "A eliminar com segurança a revisão guardada…",
    },
}


def _preferred_language_name(state: object) -> str:
    """Use the public dashboard language as the cross-page authority."""

    try:
        dashboard_value = state.get("app_lang")  # type: ignore[attr-defined]
        admin_value = state.get("admin_language")  # type: ignore[attr-defined]
    except Exception:
        dashboard_value = admin_value = None
    if dashboard_value in LANGUAGE_NAMES:
        return str(dashboard_value)
    legacy_admin = {
        "English": "English",
        "Português": "Português (Portugal)",
        "Português (Portugal)": "Português (Portugal)",
    }
    if admin_value in legacy_admin:
        return legacy_admin[str(admin_value)]
    return "English"


def _language_code(language_name: str) -> str:
    return "pt" if language_name == "Português (Portugal)" else "en"


def _copy(lang: str, key: str) -> str:
    value = COPY.get(lang, COPY["en"]).get(key, COPY["en"].get(key, key))
    return str(value)


def _render_password_sign_in(lang: str) -> None:
    with st.form("admin_password_sign_in", clear_on_submit=True):
        password = st.text_input(
            _copy(lang, "password"),
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(_copy(lang, "sign_in"), type="primary")

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
            _copy(lang, "too_many").format(seconds=seconds),
            icon=":material/lock_clock:",
        )
    else:
        st.error(_copy(lang, "incorrect"), icon=":material/error:")


def _render_closed_state(state: admin_auth.AdminState, lang: str) -> None:
    title, message = COPY.get(lang, COPY["en"])[state.value]
    st.title(title)
    st.info(message, icon=":material/lock:")
    if state is admin_auth.AdminState.ANONYMOUS:
        if admin_auth.password_mode_enabled():
            _render_password_sign_in(lang)
        elif st.button(_copy(lang, "sign_in"), type="primary", icon=":material/login:"):
            admin_auth.login()
    elif state in {
        admin_auth.AdminState.FORBIDDEN,
        admin_auth.AdminState.EXPIRED,
    }:
        if st.button(_copy(lang, "sign_out"), icon=":material/logout:"):
            admin_auth.logout()


# This is the route's capability boundary.  Keep every GitHub/OCR/workbook
# import below it so a direct request cannot construct those capabilities.
language_name = _preferred_language_name(st.session_state)
lang = _language_code(language_name)
state = admin_auth.current_admin_state()
pending_clear_reason = review_draft_recovery.pending_clear_reason(st.session_state)
if pending_clear_reason is not None:
    st.caption(_copy(lang, "clearing_review"))
    clear_complete = review_draft_recovery.render_pending_clear(st.session_state)
    if clear_complete:
        review_draft_recovery.finish_pending_clear(st.session_state)
        if pending_clear_reason == "logout":
            admin_auth.logout()
        st.rerun()
    st.stop()

if state is not admin_auth.AdminState.AUTHORIZED:
    _render_closed_state(state, lang)
    st.stop()

with st.sidebar:
    if admin_auth.password_mode_enabled():
        identity = _copy(lang, "administrator")
    else:
        claims = admin_auth.current_claims()
        identity = claims.get("email") or claims.get("name") or _copy(lang, "administrator")
    st.caption(_copy(lang, "signed_in").format(identity=identity))
    if st.button(_copy(lang, "sign_out"), icon=":material/logout:", key="admin_logout"):
        review_draft_recovery.request_browser_clear(st.session_state, "logout")
        st.rerun()

# These modules construct the remote publication, OCR, and workbook-write
# capabilities.  They must remain after the authorization boundary above.
import race_metadata

# A Streamlit hot reload may retain the pre-managed workbook module. Refresh
# it before any publisher/correction module can bind exception classes or
# writer functions, and fail closed if the managed API is still unavailable.
try:
    race_metadata.ensure_current_race_workbook()
except RuntimeError:
    st.error(_copy(lang, "updates_unavailable"))
    st.stop()

import dashboard_core as core
import admin_management_ui
import race_github as github_store


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

    config = github_store.GitHubAppConfig(
        app_id=_secret_identifier(values, "app_id"),
        installation_id=installation_id,
        private_key=_secret_text(values, "private_key"),
        owner=_secret_text(values, "owner"),
        repository=_repository_name(values),
        branch=_secret_text(values, "branch"),
        workbook_path=_secret_text(values, "workbook_path"),
    )
    hosted_settings.validate_publisher_target(config)
    return config


def _require_current_admin() -> None:
    """Recheck authorization immediately before a protected callback."""

    if not admin_auth.is_current_admin():
        st.error(_copy(lang, "authorization_expired"))
        st.stop()


def _load_remote(config: github_store.GitHubAppConfig) -> dict[str, object]:
    _require_current_admin()
    with st.spinner(_copy(lang, "loading_latest")):
        remote = github_store.fetch_remote_workbook(config)
    return asdict(remote)


def _clear_remote_snapshot() -> None:
    st.session_state.pop(REMOTE_STATE_KEY, None)


def _validated_download_snapshot(
    config: github_store.GitHubAppConfig,
) -> dict[str, object]:
    """Fetch and validate a fresh, read-only workbook download candidate."""

    snapshot = _load_remote(config)
    content = snapshot.get("content")
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("invalid download content")
    with TemporaryDirectory(prefix="f1-workbook-download-") as temporary_directory:
        candidate_path = Path(temporary_directory) / Path(config.workbook_path).name
        candidate_path.write_bytes(bytes(content))
        core.validate_workbook(candidate_path)
    return snapshot


def _sync_dashboard_language() -> None:
    ui_preferences.select_from_widget("admin_language")


# The public dashboard selection is authoritative on page entry. The Admin
# selector writes back to that same preference so subsequent page changes
# remain synchronized in both directions.
language_name = _preferred_language_name(st.session_state)
st.session_state["admin_language"] = language_name
language_name = st.selectbox(
    "Idioma / Language",
    LANGUAGE_NAMES,
    key="admin_language",
    on_change=_sync_dashboard_language,
)
lang = _language_code(language_name)

header_columns = st.columns([3, 1])
header_columns[0].title("🏁 F1 Race Updater")
header_columns[0].caption(_copy(lang, "private_updater"))
header_columns[1].link_button(
    _copy(lang, "open_dashboard"),
    PUBLIC_DASHBOARD_URL,
    use_container_width=True,
)

try:
    config = github_config_from_secrets()
except (github_store.GitHubConfigurationError, ValueError, TypeError):
    st.error(_copy(lang, "updates_unavailable"))
    st.caption(f"{APP_VERSION} · {_copy(lang, 'secure_config')}")
    st.stop()

workbook_actions = st.columns(2)
refresh_clicked = workbook_actions[0].button(
    _copy(lang, "load_latest"),
    use_container_width=True,
)
prepare_download_clicked = workbook_actions[1].button(
    _copy(lang, "prepare_download"),
    icon=":material/download:",
    use_container_width=True,
)
if refresh_clicked:
    # Clear the remote snapshot together with drafts, approvals, upload state,
    # and other importer-owned values before constructing a fresh review.
    admin_auth.clear_race_import_state(st.session_state)
    review_draft_recovery.request_browser_clear(st.session_state, "refresh")
    st.rerun()

if prepare_download_clicked:
    try:
        st.session_state[DOWNLOAD_STATE_KEY] = _validated_download_snapshot(config)
    except (github_store.GitHubPersistenceError, core.WorkbookValidationError, OSError, TypeError, ValueError):
        st.session_state.pop(DOWNLOAD_STATE_KEY, None)
        st.error(_copy(lang, "download_workbook_error"))

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
    st.error(_copy(lang, "workbook_load_error"))
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


def _publish_league_setup(
    draft,
    expected_source_version: str,
    approved: bool,
):
    """Recheck Admin authorization and rebuild one reviewed setup mutation."""

    _require_current_admin()
    if str(draft.get("source_version") or "") != expected_source_version:
        raise github_store.GitHubConflictError(
            "The reviewed league setup is not bound to this workbook version."
        )
    mutation = admin_management_ui.build_setup_publication(
        draft,
        str(workbook_path),
        standings,
    )
    try:
        return github_store.publish_league_workbook_update(
            config,
            mutation=mutation,
            expected_blob_sha=expected_source_version,
            approved=approved,
            commit_message="Create or update protected league configuration",
        )
    except github_store.GitHubConflictError:
        _clear_remote_snapshot()
        raise


def _publish_correction(
    request,
    expected_source_version: str,
    approved: bool,
):
    """Adapt the reviewed UI request to the correction publication boundary."""

    _require_current_admin()
    if str(request.get("source_version") or "") != expected_source_version:
        raise github_store.GitHubConflictError(
            "The reviewed correction is not bound to this workbook version."
    )
    import race_import
    import race_metadata

    event = request.get("event", {})
    metadata = race_metadata.from_event_mapping(event)
    roster = [
        race_import.DriverEntry(
            str(row.get("Driver") or "").strip(),
            str(row.get("Team") or "").strip(),
        )
        for row in request.get("authoritative_roster", ())
    ]
    scoring = {
        int(position): float(points)
        for position, points in dict(
            request.get("authoritative_scoring") or {}
        ).items()
    }
    try:
        return github_store.publish_event_correction(
            config,
            metadata=metadata,
            action=str(request.get("operation") or ""),
            expected_event_digest=str(request.get("expected_event_digest") or ""),
            expected_blob_sha=expected_source_version,
            approved=approved,
            rows=request.get("new_rows", ()),
            authoritative_roster=roster,
            authoritative_scoring=scoring,
            commit_message=(
                f"{str(request.get('operation') or 'correct').title()} "
                f"{metadata.event_type} results: {metadata.gp_name} "
                f"(round {metadata.round_number})"
            ),
        )
    except github_store.GitHubConflictError:
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
        st.error(_copy(lang, "workbook_validation_error"))
        st.stop()

    download_state = st.session_state.get(DOWNLOAD_STATE_KEY)
    if isinstance(download_state, dict):
        download_content = download_state.get("content")
        download_blob_sha = download_state.get("blob_sha")
        if (
            isinstance(download_content, (bytes, bytearray))
            and isinstance(download_blob_sha, str)
        ):
            # Register bytes only after a fresh authenticated fetch and full
            # workbook validation. ``ignore`` avoids disturbing an in-progress
            # result review when the browser starts the download.
            _require_current_admin()
            download_name = Path(config.workbook_path).name
            st.download_button(
                _copy(lang, "download_workbook").format(filename=download_name),
                data=bytes(download_content),
                file_name=download_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help=_copy(lang, "download_workbook_help"),
                icon=":material/download:",
                on_click="ignore",
                use_container_width=True,
            )

    admin_management_ui.render_admin_management(
        str(workbook_path),
        standings,
        calendar,
        lang=lang,
        clear_data_cache=_clear_remote_snapshot,
        source_version=remote_blob_sha,
        import_publisher=_publish,
        setup_publisher=_publish_league_setup,
        correction_publisher=_publish_correction,
        dashboard_url=PUBLIC_DASHBOARD_URL,
    )

st.caption(f"{APP_VERSION} · {_copy(lang, 'footer')}")
