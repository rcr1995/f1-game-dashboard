"""Browser-local, non-sensitive display preferences shared by every page.

The registered Streamlit v2 component only exchanges the allowlisted language
code. It never receives session, identity, authentication, or workbook data.
An initial browser read is acknowledged before any write is allowed, so a new
Streamlit session cannot replace a remembered choice with the default language.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import logging
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
        // Server reruns must never overwrite a newer browser choice.
        return;
    }

    const linked = new URLSearchParams(window.location.search).get('lang');
    let language = valid(linked) ? linked : "pt";
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
    if code not in ("en", "pt"):
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

    # Language is a display preference, never an authorization prerequisite.
    # Render immediately using a valid URL hint while storage hydrates. Do not
    # mark ready here: the browser's newer saved choice still takes precedence.
    if "app_lang" not in st.session_state:
        linked = getattr(st, "query_params", {}).get("lang")
        for name, code in LANGUAGES.items():
            if linked == code:
                st.session_state["app_lang"] = name
                break

    # Re-register the identical definition in the current runtime. Streamlit's
    # registry is runtime-scoped (not process-scoped); keeping a module-global
    # callable can otherwise reference an old registry after runtime recreation.
    # Identical definitions are idempotent in the pinned Streamlit 1.59 runtime.
    language_component = st.components.v2.component(
        "f1_browser_language",
        js=LANGUAGE_COMPONENT_JS,
    )
    ready = st.session_state.get(READY_KEY) is True
    result = language_component(
        key=COMPONENT_KEY,
        data={"ready": ready, "language": LANGUAGES[language_name(st.session_state)] if ready else None},
        on_preference_change=_receive_browser_language,
        height=0,
        width="stretch",
    )
    # After reconnect the component can replay its value without a change
    # callback. Consume the returned state as well; hydration is idempotent.
    hydrate_language(st.session_state, result.get("preference") if hasattr(result, "get") else None)
    if not st.session_state.get(READY_KEY) and not st.session_state.get("ui_language_pending_logged"):
        logging.getLogger(__name__).info("Language preference pending; rendering without blocking navigation")
        st.session_state["ui_language_pending_logged"] = True


HEADER_JS = r"""
export default function ({parentElement, data, setStateValue}) {
    let root = parentElement.querySelector('.f1-header-root');
    if (!root) {
        root = document.createElement('div');
        root.className = 'f1-header-root';
        parentElement.appendChild(root);
    }
    root.innerHTML = `<header><strong><b>F1</b> PUSKAS LEAGUE</strong><nav aria-label="Language and pages">
      <button data-language="pt" title="Português (Portugal)" aria-label="Português (Portugal)"><svg viewBox="0 0 30 20" aria-hidden="true"><path fill="#d71920" d="M0 0h30v20H0z"/><path fill="#006b3f" d="M0 0h12v20H0z"/><circle cx="12" cy="10" r="4.4" fill="#ffcf00"/><path fill="#fff" stroke="#c71924" stroke-width="1.8" d="M9.7 6.8h4.6v4a2.3 2.3 0 0 1-4.6 0z"/></svg></button>
      <button data-language="en" title="English" aria-label="English"><svg viewBox="0 0 30 20" aria-hidden="true"><path fill="#012169" d="M0 0h30v20H0z"/><path stroke="#fff" stroke-width="4" d="m0 0 30 20M30 0 0 20"/><path stroke="#c8102e" stroke-width="1.5" d="m0 0 30 20M30 0 0 20"/><path stroke="#fff" stroke-width="6" d="M15 0v20M0 10h30"/><path stroke="#c8102e" stroke-width="3.5" d="M15 0v20M0 10h30"/></svg></button>
      <a target="_self"></a></nav></header>`;
    const link = root.querySelector('a');
    link.href = (data.admin ? '/' : '/admin') + '?lang=' + data.language;
    link.textContent = data.admin ? 'Dashboard' : 'Admin';
    root.querySelectorAll('button').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.language === data.language));
        button.onclick = () => {
            const code = button.dataset.language;
            // Persist synchronously: immediately following the page link cannot lose this choice.
            try { window.localStorage.setItem('f1puskasleague.language.v1', code); } catch (_) {}
            setStateValue('selection', code);
        };
    });
}
"""

HEADER_CSS = """
header {display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:58px;border-bottom:1px solid #282c38;font-family:system-ui;color:#fafafa}
strong {font-size:17px;letter-spacing:.07em;white-space:nowrap} strong b {color:#f33;margin-right:6px}
nav {display:flex;align-items:center;gap:6px}
button {background:transparent;border:1px solid transparent;border-radius:6px;padding:6px;cursor:pointer;line-height:0}
button svg {width:25px;height:17px;border-radius:2px}
button[aria-pressed=true] {border-color:#ff5757;background:#ffffff08}
button:focus-visible,a:focus-visible {outline:2px solid #ff5757;outline-offset:2px}
a {color:#fff;text-decoration:none;border:1px solid #383d49;border-radius:8px;padding:8px 12px;font:600 12px system-ui;margin-left:5px}
a:hover {background:#272b35}
@media(max-width:500px) {strong {font-size:12px;letter-spacing:.02em} button {padding:5px} button svg {width:22px;height:15px} nav {gap:2px} a {padding:8px;font-size:11px}}
"""


def _receive_header_language() -> None:
    import streamlit as st
    result = st.session_state.get("ui_page_header", {})
    code = result.get("selection") if hasattr(result, "get") else None
    for name, value in LANGUAGES.items():
        if code == value:
            select_language(st.session_state, name)
            if hasattr(st, 'query_params'):
                st.query_params['lang'] = code
            break


def render_page_header(*, admin: bool = False) -> None:
    """Shared public chrome; no identity, secrets or privileged data enter this component."""
    import streamlit as st
    st.html('''<style>
      @import url('https://fonts.googleapis.com/css2?family=Teko:wght@400;600;700&family=Inter:wght@400;600;800&display=swap');
      .stApp,[data-testid="stAppViewContainer"] {background:#0b0b0f!important;color:#fafafa!important}
      [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],
      [data-testid="stHeader"],#MainMenu,footer {display:none!important}
      .stMainBlockContainer {max-width:1660px;padding:1rem 1.5rem 2rem}
      @media(max-width:700px) {.stMainBlockContainer {padding:.5rem .5rem 1rem}}
    </style>''')
    component = st.components.v2.component("f1_page_header", js=HEADER_JS, css=HEADER_CSS)
    component(key="ui_page_header", data={"admin": admin, "language": LANGUAGES[language_name(st.session_state)]},
              on_selection_change=_receive_header_language, height=64, width="stretch")
