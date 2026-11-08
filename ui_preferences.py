"""Browser-local, non-sensitive display preferences shared by every page.

The registered Streamlit v2 components exchange allowlisted language codes and
public league catalog keys and sorting codes. They never receive identity or authentication data.
An initial browser read is acknowledged before any write is allowed, so a new
Streamlit session cannot replace a remembered choice with the default language.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import logging
from typing import Any
from uuid import uuid4

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


CIRCUITS_COMPONENT_KEY = "ui_browser_circuits"
CIRCUITS_READY_KEY = "ui_circuits_ready"
CIRCUITS_VALUE_KEY = "ui_circuits_selection"
CIRCUITS_OPTIONS_KEY = "ui_circuits_options"
CIRCUITS_WRITE_KEY = "ui_circuits_write"
SORT_COMPONENT_KEY = "ui_browser_circuits_sort"
SORT_READY_KEY = "ui_circuits_sort_ready"
SORT_VALUE_KEY = "ui_circuits_sort_selection"
SORT_OPTIONS_KEY = "ui_circuits_sort_options"
SORT_WRITE_KEY = "ui_circuits_sort_write"
SORT_OPTIONS = ("name", "country", "races")

CIRCUITS_COMPONENT_JS = r"""
const written = new Set();
export default function ({data, setStateValue}) {
    const sorting = data.kind === "sort";
    const storageKey = sorting ? "f1puskasleague.circuits.sort.v1" : "f1puskasleague.circuits.league.v1";
    const valid = value => typeof value === "string" && data.options.includes(value);
    // Only an explicit selection creates a write. A rerun in an older tab must
    // not keep replacing a choice made more recently elsewhere in this browser.
    if (data.write && valid(data.selection)) {
        if (!written.has(data.write)) {
            written.add(data.write);
            try { window.localStorage.setItem(storageKey, data.selection); } catch (_) {}
        }
        return;
    }
    if (data.ready) return;
    let selection = sorting ? "name" : "all";
    try {
        const saved = window.localStorage.getItem(storageKey);
        if (valid(saved)) selection = saved;
    } catch (_) {}
    // A fresh session reads before writing, including when storage is blocked.
    setStateValue("preference", selection);
}
"""


def _circuit_preference_keys(sort):
    if sort:
        return (SORT_COMPONENT_KEY, SORT_READY_KEY, SORT_VALUE_KEY, SORT_OPTIONS_KEY,
                SORT_WRITE_KEY, "circuits_sort", "name")
    return (CIRCUITS_COMPONENT_KEY, CIRCUITS_READY_KEY, CIRCUITS_VALUE_KEY, CIRCUITS_OPTIONS_KEY,
            CIRCUITS_WRITE_KEY, "circuits_league", "all")


def hydrate_circuits(state: MutableMapping[str, Any], value: object, *, sort=False) -> None:
    """Restore once; a native selection always wins over delayed browser state."""
    _, ready_key, value_key, options_key, _, widget_key, default = _circuit_preference_keys(sort)
    if state.get(ready_key):
        return
    options = state.get(options_key, (default,))
    selected = value if isinstance(value, str) and value in options else default
    state[value_key] = selected
    state[widget_key] = selected
    state[ready_key] = True


def _receive_circuits_preference(*, sort=False) -> None:
    import streamlit as st
    component_key = _circuit_preference_keys(sort)[0]
    result = st.session_state.get(component_key, {})
    if hasattr(result, "get") and result.get("preference") is not None:
        hydrate_circuits(st.session_state, result["preference"], sort=sort)


def select_circuits_from_widget(*, sort=False) -> None:
    """Commit an explicit selection separately from the disposable widget key."""
    import streamlit as st
    state = st.session_state
    _, ready_key, value_key, options_key, write_key, widget_key, _ = _circuit_preference_keys(sort)
    value = state.get(widget_key)
    if not isinstance(value, str) or value not in state.get(options_key, ()):
        return
    state[value_key] = value
    state[ready_key] = True
    state[write_key] = uuid4().hex


def mount_circuits_preference(options: list[str], *, sort=False) -> None:
    """Restore before the selectbox is instantiated; never block page rendering."""
    import streamlit as st
    state = st.session_state
    component_key, ready_key, value_key, options_key, write_key, widget_key, default = _circuit_preference_keys(sort)
    state[options_key] = tuple(options)
    selected = state.get(value_key, state.get(widget_key, default))
    if not isinstance(selected, str) or selected not in options:
        selected = default
        # A removed catalog entry must never be sent back as a pending write.
        state.pop(write_key, None)
    state[value_key] = selected
    state[widget_key] = selected
    component = st.components.v2.component(
        "f1_circuits_sort_preference" if sort else "f1_circuits_preference", js=CIRCUITS_COMPONENT_JS)
    data = {"options": options, "ready": state.get(ready_key) is True,
            "selection": selected, "write": state.get(write_key)}
    if sort:
        data["kind"] = "sort"
    result = component(
        key=component_key, data=data,
        on_preference_change=_receive_circuits_sort_preference if sort else _receive_circuits_preference,
        height=0, width="stretch",
    )
    # A reconnect may replay a result without invoking its callback.
    if hasattr(result, "get") and result.get("preference") is not None:
        hydrate_circuits(state, result["preference"], sort=sort)


def hydrate_circuits_sort(state: MutableMapping[str, Any], value: object) -> None:
    hydrate_circuits(state, value, sort=True)


def _receive_circuits_sort_preference() -> None:
    _receive_circuits_preference(sort=True)


def select_circuits_sort_from_widget() -> None:
    select_circuits_from_widget(sort=True)


def mount_circuits_sort_preference() -> None:
    mount_circuits_preference(list(SORT_OPTIONS), sort=True)


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
