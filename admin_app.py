"""Private, phone-friendly race-results updater for Streamlit Community Cloud."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

import dashboard_core as core
import race_github as github_store
import race_import_ui


APP_VERSION = "v41"
PUBLIC_DASHBOARD_URL = "https://f1-game-dashboard.streamlit.app/"
REMOTE_STATE_KEY = "admin_remote_workbook"


st.set_page_config(
    page_title="F1 Race Updater",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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


def _secret_value(values: object, name: str, fallback: str | None = None) -> object:
    try:
        value = values[name]  # type: ignore[index]
    except (KeyError, TypeError):
        if fallback is None:
            raise github_store.GitHubConfigurationError("The private updater is not configured.")
        return fallback
    return value


def github_config_from_secrets() -> github_store.GitHubAppConfig:
    """Build a fail-closed GitHub configuration without exposing secret values."""
    try:
        values = st.secrets["github"]
    except (KeyError, FileNotFoundError) as exc:
        raise github_store.GitHubConfigurationError("The private updater is not configured.") from exc
    repository = _secret_value(values, "repository", _secret_value(values, "repo", "f1-game-dashboard"))
    return github_store.GitHubAppConfig(
        app_id=str(_secret_value(values, "app_id")),
        installation_id=int(_secret_value(values, "installation_id")),
        private_key=str(_secret_value(values, "private_key")),
        owner=str(_secret_value(values, "owner", "rcr1995")),
        repository=str(repository),
        branch=str(_secret_value(values, "branch", "main")),
        workbook_path=str(_secret_value(values, "workbook_path", "F1_Standings.xlsx")),
    )


def _load_remote(config: github_store.GitHubAppConfig) -> dict[str, object]:
    with st.spinner("A carregar o Excel mais recente do GitHub…"):
        remote = github_store.fetch_remote_workbook(config)
    return asdict(remote)


language_name = st.selectbox("Idioma / Language", ["Português", "English"], key="admin_language")
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
    st.caption(f"{APP_VERSION} · secure configuration required")
    st.stop()

refresh_clicked = st.button(
    "↻ Carregar Excel mais recente" if lang == "pt" else "↻ Load latest workbook",
    use_container_width=True,
)
if refresh_clicked:
    st.session_state.pop(REMOTE_STATE_KEY, None)
    st.session_state.pop("race_import_draft", None)

try:
    if REMOTE_STATE_KEY not in st.session_state:
        st.session_state[REMOTE_STATE_KEY] = _load_remote(config)
    remote_state = st.session_state[REMOTE_STATE_KEY]
    remote_content = bytes(remote_state["content"])
    remote_blob_sha = str(remote_state["blob_sha"])
except (github_store.GitHubPersistenceError, KeyError, TypeError, ValueError):
    st.error(
        "Não foi possível carregar o Excel do GitHub. Tenta novamente mais tarde; nenhum dado foi alterado."
        if lang == "pt"
        else "The GitHub workbook could not be loaded. Try again later; no data was changed."
    )
    st.stop()


def _clear_remote_snapshot() -> None:
    st.session_state.pop(REMOTE_STATE_KEY, None)


def _publish(
    metadata,
    rows: list[dict],
    scoring_profile: dict[int, float],
    expected_source_version: str,
    approved: bool,
):
    return github_store.publish_race_import(
        config,
        metadata=metadata,
        rows=rows,
        scoring_profile=scoring_profile,
        expected_blob_sha=expected_source_version,
        approved=approved,
        commit_message=f"Import {metadata.event_type} results: {metadata.gp_name} (round {metadata.round_number})",
    )


with TemporaryDirectory(prefix="f1-race-review-") as temporary_directory:
    workbook_path = Path(temporary_directory) / "F1_Standings.xlsx"
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
