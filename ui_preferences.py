"""Browser-local, non-sensitive display preferences shared by every page.

The registered Streamlit v2 component only exchanges the allowlisted language
code. It never receives session, identity, authentication, or workbook data.
An initial browser read is acknowledged before any write is allowed, so a new
Streamlit session cannot replace a remembered choice with the default language.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

LANGUAGES = {"English": "en", "Português (Portugal)": "pt"}
LANGUAGE_NAMES = tuple(LANGUAGES)
DEFAULT_LANGUAGE = "Português (Portugal)"
COMPONENT_KEY = "ui_browser_language"
READY_KEY = "ui_browser_language_ready"

# Inline assets need no third-party CDN, iframe protocol, or additional package.
# Only this fixed, app-owned key is read/written; browser storage can be blocked
# without preventing the app (or its native language selector) from working.
LANGUAGE_COMPONENT_JS = r"""
const storageKey = "f1puskasleague.language.v1";
const valid = (value) => value === "en" || value === "pt";

export default function ({ data, setStateValue }) {
    if (data?.ready === true && valid(data?.language)) {
        try {
            if (window.localStorage.getItem(storageKey) !== data.language) {
                window.localStorage.setItem(storageKey, data.language);
            }
        } catch (_) {
            // Private/blocked storage: keep using the live session preference.
        }
        return;
    }

    let language = "pt";
    try {
        const stored = window.localStorage.getItem(storageKey);
        if (valid(stored)) language = stored;
    } catch (_) {
        // No persistent storage is required to use the dashboard.
    }
    setStateValue("preference", language);
}
"""


def language_name(state: MutableMapping[str, Any]) -> str:
    value = state.get("app_lang")
    return value if isinstance(value, str) and value in LANGUAGES else DEFAULT_LANGUAGE


def select_language(state: MutableMapping[str, Any], selected: object) -> None:
    """Apply an explicit native-widget choice before the script reruns."""

    if not isinstance(selected, str) or selected not in LANGUAGES:
        return
    state["app_lang"] = selected
    state["app_lang_selector"] = selected
    state["admin_language"] = selected
    state[READY_KEY] = True


def hydrate_language(state: MutableMapping[str, Any], code: object) -> None:
    """Accept initial browser state only once; never override a newer click."""

    if state.get(READY_KEY) is True:
        return
    name = next((name for name, value in LANGUAGES.items() if code == value), DEFAULT_LANGUAGE)
    select_language(state, name)


def select_from_widget(widget_key: str) -> None:
    import streamlit as st

    select_language(st.session_state, st.session_state.get(widget_key))


def _receive_browser_language() -> None:
    import streamlit as st

    result = st.session_state.get(COMPONENT_KEY, {})
    code = result.get("preference") if hasattr(result, "get") else None
    hydrate_language(st.session_state, code)


def mount_browser_language() -> None:
    """Mount in the entrypoint so Dashboard and direct Admin visits share it."""

    import streamlit as st

    # Re-register the identical definition in the current runtime. Streamlit's
    # registry is runtime-scoped (not process-scoped); keeping a module-global
    # callable can otherwise reference an old registry after runtime recreation.
    # Identical definitions are idempotent in the pinned Streamlit 1.59 runtime.
    language_component = st.components.v2.component(
        "f1_browser_language",
        js=LANGUAGE_COMPONENT_JS,
    )
    ready = st.session_state.get(READY_KEY) is True
    language_component(
        key=COMPONENT_KEY,
        data={"ready": ready, "language": LANGUAGES[language_name(st.session_state)] if ready else None},
        on_preference_change=_receive_browser_language,
        height=0,
        width="stretch",
    )
