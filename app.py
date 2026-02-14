import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_OK = True
except Exception:
    PLOTLY_OK = False

st.set_page_config(
    page_title="F1 Game Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DEFAULT_POINTS = {1:25,2:18,3:15,4:12,5:10,6:8,7:6,8:4,9:2,10:1}

@st.cache_data(show_spinner=False)
def load_data_from_excel(file):
    df = pd.read_excel(file, sheet_name=0)
    df.columns = [c.strip() for c in df.columns]

    required = {"Game","Season","League Name","Round","GP Name","Driver","Team","Finish Pos","Points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in Excel: {sorted(missing)}")

    df["Season"] = pd.to_numeric(df["Season"], errors="coerce").astype("Int64")
    df["Round"] = pd.to_numeric(df["Round"], errors="coerce").astype("Int64")
    df["Finish Pos"] = pd.to_numeric(df["Finish Pos"], errors="coerce").astype("Int64")
    df["Points"] = pd.to_numeric(df["Points"], errors="coerce").fillna(0.0)

    return df.dropna(subset=["Season","Round"])

def find_excel():
    for p in Path(".").rglob("*.xlsx"):
        if not p.name.startswith("~$"):
            return str(p)
    return None

st.title("F1 Game Dashboard")

with st.sidebar:
    uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    if uploaded is None:
        bundled = find_excel()
        if bundled is None:
            st.warning("Upload your Excel file.")
            st.stop()
        raw = load_data_from_excel(bundled)
    else:
        raw = load_data_from_excel(uploaded)

def standings(df, entity):
    col = "Driver" if entity == "Drivers" else "Team"
    g = df.groupby(col, as_index=False).agg(
        Points=("Points","sum"),
        Wins=("Finish Pos", lambda s: int((s==1).sum())),
        Podiums=("Finish Pos", lambda s: int((s<=3).sum())),
        AvgFinish=("Finish Pos", lambda s: float(np.nanmean(s.astype("float")))),
    )
    g["AvgFinish"] = g["AvgFinish"].round(1)
    g = g.sort_values(["Points","Wins","Podiums","AvgFinish",col], ascending=[False,False,False,True,True])
    g.insert(0,"Pos",range(1,len(g)+1))
    return g

entity = st.radio("Standings Type",["Drivers","Constructors"],horizontal=True)
table = standings(raw, entity)

st.subheader("Standings")
st.dataframe(table, use_container_width=True, hide_index=True)

st.subheader("Notes")
st.markdown("""
- Make sure your GitHub repo contains:
  - app.py
  - requirements.txt
  - runtime.txt
  - .streamlit/config.toml

- requirements.txt must include openpyxl.
- runtime.txt must contain: python-3.11
""")
