"""Application router for the public dashboard and protected Admin area."""

from __future__ import annotations

import streamlit as st

import ui_preferences


st.set_page_config(
    page_title="F1 Game Dashboard",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ui_preferences.mount_browser_language()
if not st.session_state.get(ui_preferences.READY_KEY):
    st.caption("Loading / A carregar…")
    st.stop()

dashboard = st.Page(
    "dashboard_page.py",
    title="Dashboard",
    icon="🏁",
    default=True,
)
admin = st.Page(
    "admin_page.py",
    title="Admin",
    icon=":material/admin_panel_settings:",
    url_path="admin",
)

navigation = st.navigation([dashboard, admin], position="hidden")
navigation.run()
