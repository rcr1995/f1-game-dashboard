"""Application router for the public dashboard and protected Admin area."""

from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="F1 Game Dashboard",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

navigation = st.navigation([dashboard, admin], position="sidebar", expanded=False)
navigation.run()
