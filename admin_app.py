"""Compatibility entrypoint for the same protected Admin route.

Deployments that historically launched ``admin_app.py`` keep working, but this
file deliberately constructs no GitHub, OCR, or workbook capability itself.
The routed page owns the exact OIDC authorization boundary.
"""

from __future__ import annotations

import streamlit as st

import ui_preferences


st.set_page_config(
    page_title="F1 League Administration",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ui_preferences.mount_browser_language()
if not st.session_state.get(ui_preferences.READY_KEY):
    st.caption("Loading / A carregar…")
    st.stop()

admin_page = st.Page(
    "admin_page.py",
    title="Admin",
    icon=":material/admin_panel_settings:",
    default=True,
)
st.navigation([admin_page], position="hidden").run()
