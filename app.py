import streamlit as st
import pandas as pd
import numpy as np
import json
import re
from pathlib import Path

# Plotly (recommended)
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

# -----------------------------
# i18n (EN / PT)
# -----------------------------
LANGS = {"English": "en", "Português": "pt"}

T = {
    "en": {
        "title": "F1 Game Dashboard",
        "data": "Data",
        "upload": "Upload Excel (.xlsx)",
        "upload_help": "Drag & drop the base Excel file here.",
        "using_bundled": "Using a bundled Excel file found in the repo.",
        "no_bundled": "No bundled Excel file found. Please upload your Excel file in the sidebar.",
        "season_final": "Season Final",
        "points_system_global": "Points system (global)",
        "how_score": "How to score points",
        "use_excel": "Use points from Excel",
        "f1_default": "F1 default (25-18-...)",
        "custom_mapping": "Custom mapping",
        "custom_caption": 'Enter JSON mapping from finishing position to points. Example: {"1":25,"2":18,...}',
        "custom_json": "Custom points JSON",
        "game": "Game",
        "season": "Season",
        "league": "League",
        "tabs": ["🏁 Dashboard", "📊 GP Statistics", "🛣️ Circuits", "🏆 All‑time", "⚙️ Settings"],
        "standings_type": "Standings type",
        "drivers": "Drivers",
        "constructors": "Constructors",
        "overview": "Overview",
        "races": "Races",
        "grid_size": "Grid size",
        "leader": "Leader",
        "leader_points": "Leader points",
        "standings": "Standings",
        "show_form_cols": "Show form columns (last 3/5)",
        "tiebreak": "Tie-breakers: Points → Wins → Podiums → lower Avg Finish.",
        "last_gp_results": "Last GP results",
        "progression": "Season progression (cumulative points)",
        "top_n_lines": "Top N lines",
        "biggest_movers": "Biggest movers (last round)",
        "top_gainers": "Top gainers",
        "top_losers": "Top losers",
        "leader_tracker": "Leader tracker",
        "lead_swaps": "Lead swaps",
        "lead_margin": "Lead margin",
        "round": "Round",
        "matrix_for": "Matrix for",
        "pos_matrix": "Round‑by‑round position matrix",
        "form_table": "Form table",
        "form_help": "Recent performance: points and average finish over the last 3 and last 5 rounds, plus current position and position change since the previous round.",
        "exec_summary": "Executive summary",
        "title_fight": "Title fight gap",
        "most_in_form": "Most in-form (L3)",
        "biggest_mover": "Biggest mover",
        "tension": "Championship tension",
        "gap_p1_p2": "P1-P2 gap",
        "gap_top3": "Top-3 spread",
        "position_delta": "Position delta analytics",
        "momentum_l3": "Momentum (L3)",
        "change": "Change",
        "empty_hint": "Try another Season-League selector, or switch to All (GP-only).",
        "available_gp_rows": "Available GP rows",
        "chart_preset": "Chart preset",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "all_time_title": "All‑time overview (ignores Season filter)",
        "all_time_standings": "All‑time standings",
        "titles_count": "Titles count",
        "champions_list": "Season champions list",
        "champions_timeline": "Champions timeline",
        "all_time_progression": "All‑time progression (cumulative points across seasons)",
        "current_season_only": "Current season league",
        "race_standings": "Race standings",
        "select_race": "Select race",
        "gp_winners_top3": "Top 3 drivers by wins per GP",
        "no_gp_winners": "No GP winner data available.",
        "version": "F1 Game Dashboard • v35",
        "language": "Language",
        "no_rows": "No rows match the current filters.",
        "not_enough": "Not enough data for this view.",
        "download": "Download CSV",
        "view": "View",
        "season_league_gp": "Season — League (GP-only)",
    },
    "pt": {
        "title": "Dashboard F1",
        "data": "Dados",
        "upload": "Carregar Excel (.xlsx)",
        "upload_help": "Arraste e largue aqui o ficheiro Excel base.",
        "using_bundled": "A usar um ficheiro Excel incluído no repositório.",
        "no_bundled": "Não foi encontrado nenhum Excel no repositório. Carregue o Excel na barra lateral.",
        "season_final": "Final da época",
        "points_system_global": "Sistema de pontos (global)",
        "how_score": "Como calcular os pontos",
        "use_excel": "Usar pontos do Excel",
        "f1_default": "F1 padrão (25-18-...)",
        "custom_mapping": "Mapeamento personalizado",
        "custom_caption": 'Introduza um JSON com a pontuação por posição. Ex.: {"1":25,"2":18,...}',
        "custom_json": "JSON de pontos",
        "game": "Jogo",
        "season": "Época",
        "league": "Liga",
        "tabs": ["🏁 Dashboard", "📊 Estatísticas GP", "🛣️ Circuitos", "🏆 Histórico", "⚙️ Definições"],
        "standings_type": "Tipo de classificação",
        "drivers": "Pilotos",
        "constructors": "Construtores",
        "overview": "Resumo",
        "races": "Corridas",
        "grid_size": "Nº participantes",
        "leader": "Líder",
        "leader_points": "Pontos do líder",
        "standings": "Classificação",
        "show_form_cols": "Mostrar colunas de forma (últimas 3/5)",
        "tiebreak": "Desempates: Pontos → Vitórias → Pódios → melhor Média de Posição.",
        "last_gp_results": "Resultados do último GP",
        "progression": "Progressão na época (pontos acumulados)",
        "top_n_lines": "Top N linhas",
        "biggest_movers": "Maiores subidas/descidas (última ronda)",
        "top_gainers": "Maiores subidas",
        "top_losers": "Maiores descidas",
        "leader_tracker": "Evolução do líder",
        "lead_swaps": "Trocas de líder",
        "lead_margin": "Margem",
        "round": "Ronda",
        "matrix_for": "Matriz para",
        "pos_matrix": "Matriz de posições por ronda",
        "form_table": "Tabela de forma",
        "form_help": "Desempenho recente: pontos e média de posição nas últimas 3 e 5 rondas, mais a posição atual e a mudança desde a ronda anterior.",
        "exec_summary": "Resumo executivo",
        "title_fight": "Diferença na luta pelo título",
        "most_in_form": "Mais em forma (L3)",
        "biggest_mover": "Maior subida",
        "tension": "Tensão do campeonato",
        "gap_p1_p2": "Diferença P1-P2",
        "gap_top3": "Diferença Top-3",
        "position_delta": "Análise delta de posições",
        "momentum_l3": "Momento (L3)",
        "change": "Mudança",
        "empty_hint": "Tente outro seletor Época-Liga, ou mude para Todos (apenas GP).",
        "available_gp_rows": "Linhas GP disponíveis",
        "chart_preset": "Predefinição do gráfico",
        "theme": "Tema",
        "theme_dark": "Escuro",
        "theme_light": "Claro",
        "all_time_title": "Histórico (ignora filtro de Época)",
        "all_time_standings": "Classificação histórica",
        "titles_count": "Títulos",
        "champions_list": "Lista de campeões por época",
        "champions_timeline": "Linha temporal de campeões",
        "all_time_progression": "Progressão histórica (pontos acumulados)",
        "current_season_only": "Liga da época atual",
        "race_standings": "Classificação da corrida",
        "select_race": "Selecionar corrida",
        "gp_winners_top3": "Top 3 pilotos por vitórias em cada GP",
        "no_gp_winners": "Sem dados de vencedores de GP disponíveis.",
        "version": "Dashboard F1 • v9",
        "language": "Idioma",
        "no_rows": "Sem dados para os filtros atuais.",
        "not_enough": "Dados insuficientes para esta vista.",
        "download": "Download CSV",
        "view": "Vista",
        "season_league_gp": "Época — Liga (apenas GP)",
    },
}

def tr(lang: str, key: str):
    return T[lang].get(key, key)


def season_final_label() -> str:
    lang = st.session_state.get("_lang", "en")
    return T.get(lang, T["en"]).get("season_final", "Season Final")

def mark_season_final(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    gp = d["GP Name"].astype(str).str.strip().str.lower()
    d["IsSeasonFinal"] = gp.isin({"all", "season total", "final", "season final"})
    return d

def effective_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Avoid double-counting when both GP-level rows and season-total rows exist.

    Rule per (Game, Season, League):
    - if any GP-level rows exist: keep ONLY GP-level rows
    - else: keep season-final rows (one or more)
    """
    if df.empty:
        return df
    d = df.copy()
    if "IsSeasonFinal" not in d.columns:
        d = mark_season_final(d)

    group_cols = [c for c in ["Game", "Season", "League Name"] if c in d.columns]
    if not group_cols:
        group_cols = ["Season"]

    def _pick(g: pd.DataFrame) -> pd.DataFrame:
        has_gp = (~g["IsSeasonFinal"]).any()
        return g[~g["IsSeasonFinal"]] if has_gp else g

    return d.groupby(group_cols, group_keys=False).apply(_pick)


@st.cache_data(show_spinner=False)
def load_data_from_excel(file) -> pd.DataFrame:
    """Load Excel and support mixed granularities.

    - Per-GP rows (normal): GP Name not in season-total markers and Round is numeric
    - Season-total rows ("Season Final"): GP Name in {'All','Season Total','Final','Season Final'}
      OR Round equals 'All' (common in your historical data)

    Season can be numeric (2024) or text ('2019-T1', '2014/15', '2014-2015').

    Adds:
      SeasonLabel (string) for filtering/display
      SeasonNum (numeric) for ordering when available
      IsSeasonFinal (bool)
    """
    df = pd.read_excel(file, sheet_name=0)  # requires openpyxl
    df.columns = [str(c).strip() for c in df.columns]

    required = {"Game","Season","League Name","Round","GP Name","Driver","Team","Finish Pos","Points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in Excel: {sorted(missing)}")

    # Clean strings
    for c in ["Game","Season","League Name","Round","GP Name","Driver","Team"]:
        df[c] = df[c].astype(str).str.strip()

    df["SeasonLabel"] = df["Season"].astype(str).str.strip()

    # Derive numeric season for sorting (first 4-digit year)
    season_num = df["SeasonLabel"].str.extract(r"(\d{4})", expand=False)
    df["SeasonNum"] = pd.to_numeric(season_num, errors="coerce")

    season_direct = pd.to_numeric(df["SeasonLabel"], errors="coerce")
    df.loc[season_direct.notna(), "SeasonNum"] = season_direct[season_direct.notna()]

    season_total_markers = {"all","season total","final","season final"}
    round_raw = df["Round"].astype(str).str.strip()
    gp_raw = df["GP Name"].astype(str).str.strip()

    df["IsSeasonFinal"] = gp_raw.str.lower().isin(season_total_markers) | round_raw.str.lower().isin({"all"})

    # Numeric conversions
    df["Round"] = pd.to_numeric(df["Round"], errors="coerce")
    # Put season-finals at the end of a season timeline
    df.loc[df["IsSeasonFinal"] & df["Round"].isna(), "Round"] = 999
    df["Round"] = df["Round"].astype("Int64")

    df["Finish Pos"] = pd.to_numeric(df["Finish Pos"], errors="coerce").astype("Int64")
    df["Points"] = pd.to_numeric(df["Points"], errors="coerce").fillna(0.0)

    # Drop rows that are truly unusable (no round)
    df = df.dropna(subset=["Round"]).copy()

    # Normalize GP Name / label Season Final
    df["GP Name"] = df["GP Name"].fillna("").astype(str).str.strip()
    df.loc[df["IsSeasonFinal"], "GP Name"] = "Season Final"

    return df


def find_bundled_excel() -> str | None:
    candidates = [
        "F1_Standings.xlsx",
        "data/F1_Standings.xlsx",
        "Data/F1_Standings.xlsx",
        "assets/F1_Standings.xlsx",
        "excel/F1_Standings.xlsx",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for p in Path(".").rglob("*.xlsx"):
        if p.name.lower().startswith("~$"):
            continue
        return str(p)
    return None

DEFAULT_POINTS = {1:25,2:18,3:15,4:12,5:10,6:8,7:6,8:4,9:2,10:1}

def apply_points_override(df: pd.DataFrame, mode: str, custom_map: dict, last_round_multiplier: float = 1.0) -> pd.DataFrame:
    d = df.copy()
    if mode == "Use points from Excel":
        pass
    elif mode == "F1 default (25-18-...)":
        d["Points"] = d["Finish Pos"].map(DEFAULT_POINTS).fillna(0.0)
    else:
        mapping = custom_map or {}
        d["Points"] = d["Finish Pos"].map(mapping).fillna(0.0)
    if last_round_multiplier != 1.0 and not d.empty:
        last_round = d["Round"].max()
        d.loc[d["Round"] == last_round, "Points"] = d.loc[d["Round"] == last_round, "Points"] * float(last_round_multiplier)
    return d


def _season_sort_key(season_label: str) -> int:
    """Sortable key for SeasonLabel like 2019-T01 < 2019-T02 < 2020-T01 etc."""
    s = str(season_label).strip()
    year_m = re.search(r"(\d{4})", s)
    year = int(year_m.group(1)) if year_m else 0
    t_m = re.search(r"[Tt]\s*-?\s*(\d+)", s)
    t = int(t_m.group(1)) if t_m else 0
    return year * 100 + t

def latest_league_slice(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return df filtered to the latest SeasonLabel and its linked League/Game."""
    if df.empty:
        return df.copy(), {"Game":"-", "SeasonLabel":"-", "League Name":"-"}
    d = df.copy()
    labels = d["SeasonLabel"].dropna().unique().tolist()
    labels.sort(key=_season_sort_key)
    latest_label = labels[-1] if labels else str(d["SeasonLabel"].dropna().iloc[0])
    d2 = d[d["SeasonLabel"] == latest_label].copy()
    league = d2["League Name"].mode().iloc[0] if not d2.empty else "-"
    game = d2["Game"].mode().iloc[0] if not d2.empty else "-"
    d2 = d2[(d2["League Name"] == league) & (d2["Game"] == game)].copy()
    return d2, {"Game": game, "SeasonLabel": latest_label, "League Name": league}

def season_totals(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["SeasonLabel", entity_col, "Points"])
    return df.groupby(["SeasonLabel", entity_col], as_index=False)["Points"].sum()

def game_totals(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Game", entity_col, "Points"])
    return df.groupby(["Game", entity_col], as_index=False)["Points"].sum()
def standings_table(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    """
    Standings stats computed on GP-level rows only (exclude Season Final rows).
    Races = number of distinct races per entity, using (Game, SeasonLabel, League Name, Round, GP Name).
    """
    col = "Driver" if entity == "Drivers" else "Team"
    if df.empty:
        return pd.DataFrame(columns=["Pos", col, "Points", "Races", "Wins", "Podiums", "Top5", "AvgFinish", "Consistency", "Pts/Race"])

    d = df.copy()
    if "IsSeasonFinal" not in d.columns:
        d = mark_season_final(d)
    d = d[~d["IsSeasonFinal"]].copy()
    if d.empty:
        return pd.DataFrame(columns=["Pos", col, "Points", "Races", "Wins", "Podiums", "Top5", "AvgFinish", "Consistency", "Pts/Race"])

    d["_RaceID"] = (
        d["Game"].astype(str) + "|" +
        d["SeasonLabel"].astype(str) + "|" +
        d["League Name"].astype(str) + "|" +
        d["Round"].astype(str) + "|" +
        d["GP Name"].astype(str)
    )

    g = d.groupby(col, as_index=False).agg(
        Points=("Points","sum"),
        Races=("_RaceID","nunique"),
        Wins=("Finish Pos", lambda s: int((s==1).sum())),
        Podiums=("Finish Pos", lambda s: int((s<=3).sum())),
        Top5=("Finish Pos", lambda s: int((s<=5).sum())),
        AvgFinish=("Finish Pos", lambda s: float(np.nanmean(s.astype("float")))),
        Consistency=("Finish Pos", lambda s: float(np.nanstd(s.astype("float")))),
    )

    g["AvgFinish"] = g["AvgFinish"].round(1)
    g["Consistency"] = g["Consistency"].round(2)
    g["Pts/Race"] = (g["Points"] / g["Races"].replace(0, np.nan)).fillna(0).round(2)
    g = g.sort_values(["Points","Wins","Podiums","AvgFinish",col], ascending=[False,False,False,True,True])
    g.insert(0, "Pos", range(1, len(g)+1))
    return g

def _season_sort_key(season_label: str) -> int:
    """
    Build a sortable numeric key from SeasonLabel strings like:
    - '2019-T01' -> 201901
    - '2019-T1'  -> 201901
    - '2026'     -> 202600
    - 'S3'       -> 0 (falls back)
    """
    s = str(season_label).strip()
    year_m = re.search(r"(\d{4})", s)
    year = int(year_m.group(1)) if year_m else 0
    t_m = re.search(r"[Tt]\s*-?\s*(\d+)", s)
    t = int(t_m.group(1)) if t_m else 0
    return year * 100 + t

def event_sort_cols(df: pd.DataFrame, all_time: bool) -> pd.DataFrame:
    d = df.copy()
    if all_time:
        # SeasonLabel is the timeline anchor (league-as-timeline: 2019-T01, 2019-T02, ...)
        d["_SeasonKey"] = d["SeasonLabel"].map(_season_sort_key).astype(int)
        d["EventIdx"] = d["_SeasonKey"] * 1000 + d["Round"].astype(int)
        # Make the label more intentional for season totals
        d["EventLabel"] = d["SeasonLabel"].astype(str) + " • R" + d["Round"].astype(str) + " • " + d["GP Name"].astype(str)
        d = d.drop(columns=["_SeasonKey"], errors="ignore")
    else:
        d["EventIdx"] = d["Round"].astype(int)
        d["EventLabel"] = "R" + d["Round"].astype(str) + " • " + d["GP Name"].astype(str)
    return d

def cumulative_points_wide(df: pd.DataFrame, entity_col: str, all_time: bool):

    d = event_sort_cols(df, all_time=all_time).sort_values(["EventIdx","GP Name", entity_col])
    d["CumPoints"] = d.groupby(entity_col)["Points"].cumsum()
    long = d.groupby([entity_col,"EventIdx","EventLabel"], as_index=False)["CumPoints"].max()
    wide = long.pivot_table(index="EventIdx", columns=entity_col, values="CumPoints", aggfunc="max").sort_index()
    return wide, long

def per_round_positions(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    d = event_sort_cols(df, all_time=False).sort_values(["EventIdx","GP Name", entity_col])
    d["CumPoints"] = d.groupby(entity_col)["Points"].cumsum()
    rr = d.groupby([entity_col,"EventIdx","EventLabel"], as_index=False)["CumPoints"].max()
    rr["Position"] = rr.groupby("EventIdx")["CumPoints"].rank(method="min", ascending=False).astype(int)
    rr = rr.sort_values([entity_col,"EventIdx"])
    rr["PrevPos"] = rr.groupby(entity_col)["Position"].shift(1)
    rr["PosChange"] = rr["PrevPos"] - rr["Position"]
    return rr

def lead_swaps_count(leaders_series: pd.Series) -> int:
    if leaders_series.empty:
        return 0
    changes = (leaders_series != leaders_series.shift(1)).sum()
    return int(max(changes - 1, 0))

def last_gp_table(df: pd.DataFrame, entity: str):
    # Exclude season-final rows (GP Name == 'All', etc.)
    if df.empty:
        return pd.DataFrame(), ""
    d0 = df.copy()
    if "IsSeasonFinal" not in d0.columns:
        d0 = mark_season_final(d0)
    d0 = d0[~d0["IsSeasonFinal"]].copy()
    if d0.empty:
        return pd.DataFrame(), ""

    last_round = int(d0["Round"].max())
    gp_mode = d0.loc[d0["Round"] == last_round, "GP Name"].mode()
    gp = gp_mode.iloc[0] if len(gp_mode) else ""
    d = d0[(d0["Round"] == last_round) & (d0["GP Name"] == gp)].copy()

    if entity == "Drivers":
        t = d.groupby(["Driver","Team"], as_index=False).agg(
            FinishPos=("Finish Pos","min"),
            Points=("Points","sum"),
        ).sort_values(["FinishPos","Driver"], ascending=[True,True])
        # Rank column
        t.insert(0, "Pos", range(1, len(t)+1))
        # Remove duplicate finish position column (Pos already conveys it)
        t = t.drop(columns=["FinishPos"], errors="ignore")
        return t, f"Round {last_round} • {gp}"

    t = d.groupby(["Team"], as_index=False).agg(
        Points=("Points","sum"),
        BestFinish=("Finish Pos","min"),
    ).sort_values(["Points","BestFinish","Team"], ascending=[False,True,True])
    t.insert(0, "Pos", range(1, len(t)+1))
    return t, f"Round {last_round} • {gp}"

def form_table(df: pd.DataFrame, entity_col: str, n_list=(3,5)) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    last_round = int(d["Round"].max())
    rr = per_round_positions(d, entity_col=entity_col)
    last_pos = rr[rr["EventIdx"] == last_round][[entity_col,"Position","PosChange"]].copy()
    last_pos["PosChange"] = last_pos["PosChange"].fillna(0).astype(int)
    rows = []
    for ent, sub in d.groupby(entity_col):
        sub = sub.sort_values(["Round","GP Name"])
        for n in n_list:
            sub_n = sub[sub["Round"] > last_round - n]
            rows.append({
                entity_col: ent,
                f"Pts L{n}": float(sub_n["Points"].sum()),
                f"AvgFin L{n}": float(np.nanmean(sub_n["Finish Pos"].astype("float"))) if len(sub_n) else np.nan
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    agg = {c:"first" for c in out.columns if c != entity_col}
    out = out.groupby(entity_col, as_index=False).agg(agg)
    out = out.merge(last_pos, on=entity_col, how="left")
    out["Position"] = out["Position"].fillna(np.nan).astype("Int64")
    sort_col = "Position" if "Position" in out.columns else f"Pts L{max(n_list)}"
    out = out.sort_values([sort_col, entity_col], ascending=[True, True])
    return out

def position_matrix(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    rr = per_round_positions(df, entity_col=entity_col)
    mat = rr.pivot_table(index=entity_col, columns="EventIdx", values="Position", aggfunc="min")
    mat = mat.sort_index()
    if not mat.empty:
        last = mat.columns.max()
        mat = mat.sort_values(by=last, ascending=True)
    mat.columns = [f"R{int(c)}" for c in mat.columns]
    mat.insert(0, "Current", mat.iloc[:, -1].astype("Int64") if mat.shape[1] else pd.Series(dtype="Int64"))
    return mat

def season_champions(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    d = df.groupby(["SeasonLabel", entity_col], as_index=False)["Points"].sum()
    d = d.sort_values(["SeasonLabel","Points"], ascending=[True,False])
    champs = d.groupby("SeasonLabel").head(1).rename(columns={entity_col:"Champion"})
    return champs[["SeasonLabel","Champion","Points"]].rename(columns={"SeasonLabel":"Season"}).sort_values("Season")

def titles_count(df: pd.DataFrame, entity_col: str):
    champs = season_champions(df, entity_col)
    t = champs.groupby("Champion", as_index=False).agg(Titles=("Season","nunique"))
    t = t.sort_values(["Titles","Champion"], ascending=[False,True]).reset_index(drop=True)
    t.insert(0, "Rank", range(1, len(t)+1))
    return t, champs

def _color_pos_change(val):
    try:
        v = float(val)
    except Exception:
        return ""
    if v > 0:
        return f"color: {THEME_CFG['positive']}; font-weight: 700;"
    if v < 0:
        return f"color: {THEME_CFG['negative']}; font-weight: 700;"
    return f"color: {THEME_CFG['neutral']};"

def style_by_columns(df: pd.DataFrame, cols):
    sty = df.style
    for c in cols:
        if c in df.columns:
            sty = sty.map(_color_pos_change, subset=[c])
    return sty

def download_csv_button(df: pd.DataFrame, filename: str, label: str):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")


def localized_table(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    rename_map = {
        "Pos": "Pos",
        "Rank": "Rank",
        "Driver": tr(lang, "drivers"),
        "Team": tr(lang, "constructors"),
        "Points": "Points" if lang == "en" else "Pontos",
        "Races": tr(lang, "races"),
        "Wins": "Wins" if lang == "en" else "Vitórias",
        "Podiums": "Podiums" if lang == "en" else "Pódios",
        "Top5": "Top 5",
        "AvgFinish": "Avg Finish" if lang == "en" else "Média de posição",
        "Consistency": "Consistency" if lang == "en" else "Consistência",
        "Pts/Race": "Pts/Race" if lang == "en" else "Pts/Corrida",
        "Round": tr(lang, "round"),
        "GP Name": "GP" if lang == "en" else "Grande Prémio",
        "Finish Pos": "Finish" if lang == "en" else "Posição final",
        "SeasonYear": "Season" if lang == "en" else "Época",
        "Season": "Season" if lang == "en" else "Época",
        "Champion": "Champion" if lang == "en" else "Campeão",
        "CumPoints": "Cumulative Points" if lang == "en" else "Pontos acumulados",
        "CurrentPoints": "Current Points" if lang == "en" else "Pontos atuais",
        "CurrentPos": "Current Pos" if lang == "en" else "Posição atual",
        "PrevPos": "Prev Pos" if lang == "en" else "Posição anterior",
        "Delta": tr(lang, "change"),
        "SeasonLabel": tr(lang, "season"),
        "League Name": tr(lang, "league"),
    }
    out = df.copy()
    return out.rename(columns={c: rename_map[c] for c in out.columns if c in rename_map})


def circuits_top3(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "IsSeasonFinal" not in d.columns:
        d = mark_season_final(d)
    d = d[(~d["IsSeasonFinal"]) & (d["Finish Pos"] == 1)].copy()
    if d.empty:
        return pd.DataFrame(columns=["GP Name", "Top 1", "Top 2", "Top 3"])

    wins = d.groupby(["GP Name", "Driver"], as_index=False).size().rename(columns={"size": "Wins"})
    wins = wins.sort_values(["GP Name", "Wins", "Driver"], ascending=[True, False, True])
    top = wins.groupby("GP Name").head(3).copy()
    top["Label"] = top["Driver"] + " (" + top["Wins"].astype(int).astype(str) + ")"
    top["Rank"] = top.groupby("GP Name").cumcount() + 1
    out = top.pivot(index="GP Name", columns="Rank", values="Label").reset_index()
    out = out.rename(columns={1: "Top 1", 2: "Top 2", 3: "Top 3"}).fillna("-")
    return out.sort_values("GP Name")


def theme_palette(theme_mode: str) -> dict:
    if theme_mode == "Light":
        return {
            "positive": "#1f9d55",
            "negative": "#e03131",
            "neutral": "#6c757d",
            "plotly_template": "plotly_white",
            "line_palette": px.colors.qualitative.Set2 if PLOTLY_OK else [],
            "css": """
                <style>
                .stApp { background-color: #f8f9fa; color: #1f2937; }
                div[data-testid='stMetricValue'] { font-size: 1.2rem; color: #111827; }
                .stTabs [role="tab"] { color: #1f2937 !important; }
                .stTabs [role="tab"][aria-selected="true"] { color: #111827 !important; font-weight: 700; }
                div[data-testid="stDataFrame"] { color: #111827; }
                </style>
            """,
        }
    return {
        "positive": "#2ecc71",
        "negative": "#ff4b4b",
        "neutral": "#b0b0b0",
        "plotly_template": "plotly_dark",
        "line_palette": px.colors.qualitative.Bold if PLOTLY_OK else [],
        "css": """
            <style>
            div[data-testid='stMetricValue'] { font-size: 1.2rem; }
            .stTabs [role="tab"] { color: #f3f4f6 !important; }
            </style>
        """,
    }


def apply_theme_css(theme_cfg: dict):
    st.markdown(theme_cfg["css"], unsafe_allow_html=True)


def championship_tension(df: pd.DataFrame, entity_col: str) -> tuple[dict, pd.DataFrame, pd.Series]:
    if df.empty:
        return {"lead_swaps": 0, "last_gap": np.nan, "last_top3_spread": np.nan}, pd.DataFrame(), pd.Series(dtype="object")
    rr = per_round_positions(df, entity_col=entity_col)
    if rr.empty:
        return {"lead_swaps": 0, "last_gap": np.nan, "last_top3_spread": np.nan}, pd.DataFrame(), pd.Series(dtype="object")

    leaders = (
        rr.sort_values(["EventIdx", "Position", entity_col])
        .groupby("EventIdx", as_index=False)
        .first()
        .set_index("EventIdx")[entity_col]
    )

    by_round = []
    for evt, sub in rr.groupby("EventIdx"):
        top = sub.sort_values("Position").head(3)
        p1 = top[top["Position"] == 1]["CumPoints"]
        p2 = top[top["Position"] == 2]["CumPoints"]
        gap = float(p1.iloc[0] - p2.iloc[0]) if len(p1) and len(p2) else np.nan
        spread = float(top["CumPoints"].max() - top["CumPoints"].min()) if len(top) >= 3 else np.nan
        by_round.append({"EventIdx": evt, "GapP1P2": gap, "Top3Spread": spread})
    tension_df = pd.DataFrame(by_round).sort_values("EventIdx") if by_round else pd.DataFrame(columns=["EventIdx", "GapP1P2", "Top3Spread"])

    metrics = {
        "lead_swaps": lead_swaps_count(leaders),
        "last_gap": float(tension_df["GapP1P2"].dropna().iloc[-1]) if not tension_df["GapP1P2"].dropna().empty else np.nan,
        "last_top3_spread": float(tension_df["Top3Spread"].dropna().iloc[-1]) if not tension_df["Top3Spread"].dropna().empty else np.nan,
    }
    return metrics, tension_df, leaders


def position_delta_table(df: pd.DataFrame, entity_col: str, n_momentum: int = 3) -> pd.DataFrame:
    rr = per_round_positions(df, entity_col=entity_col)
    if rr.empty:
        return pd.DataFrame()
    last_evt = rr["EventIdx"].max()
    last = rr[rr["EventIdx"] == last_evt][[entity_col, "Position", "PrevPos", "PosChange"]].copy()
    last["PosChange"] = last["PosChange"].fillna(0).astype(int)

    recent = rr.sort_values("EventIdx").groupby(entity_col).tail(n_momentum)
    mom = recent.groupby(entity_col, as_index=False)["PosChange"].sum().rename(columns={"PosChange": f"MomentumL{n_momentum}"})

    out = last.merge(mom, on=entity_col, how="left")
    out[f"MomentumL{n_momentum}"] = out[f"MomentumL{n_momentum}"].fillna(0).astype(int)
    out = out.rename(columns={"Position": "CurrentPos", "PrevPos": "PrevPos", "PosChange": "Delta"})
    return out.sort_values(["Delta", f"MomentumL{n_momentum}", "CurrentPos"], ascending=[False, False, True]).reset_index(drop=True)

if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Dark"
if "app_lang" not in st.session_state:
    st.session_state["app_lang"] = "English"

lang_name = st.session_state.get("app_lang", "English")
lang_name = lang_name if lang_name in LANGS else "English"
lang = LANGS[lang_name]

THEME_CFG = theme_palette(st.session_state.get("theme_mode", "Dark"))
apply_theme_css(THEME_CFG)

st.title(tr(lang, "title"))

with st.sidebar:
    st.header(tr(lang, "data"))
    uploaded = st.file_uploader(tr(lang, "upload"), type=["xlsx"], help=tr(lang, "upload_help"))
    if uploaded is None:
        bundled = find_bundled_excel()
        if bundled is None:
            st.warning(tr(lang, "no_bundled"))
            st.stop()
        st.caption(tr(lang, "using_bundled") + f"  \n• `{bundled}`")
        raw = load_data_from_excel(bundled)
    else:
        raw = load_data_from_excel(uploaded)

    st.divider()
    st.header(tr(lang, "points_system_global"))
    points_mode = st.selectbox(
        tr(lang, "how_score"),
        [tr(lang, "use_excel"), tr(lang, "f1_default"), tr(lang, "custom_mapping")],
        index=0
    )
    mode_map = {
        tr(lang, "use_excel"): "Use points from Excel",
        tr(lang, "f1_default"): "F1 default (25-18-...)",
        tr(lang, "custom_mapping"): "Custom mapping",
    }
    canonical_points_mode = mode_map[points_mode]
    custom_map = {}
    if canonical_points_mode == "Custom mapping":
        st.caption(tr(lang, "custom_caption"))
        txt = st.text_area(tr(lang, "custom_json"), value=json.dumps(DEFAULT_POINTS, indent=2))
        try:
            m = json.loads(txt) if txt.strip() else {}
            custom_map = {int(k): float(v) for k, v in m.items()}
            st.success("OK")
        except Exception as e:
            st.error(f"Invalid JSON: {e}")
            custom_map = {}

base_all = apply_points_override(raw.copy(), mode=canonical_points_mode, custom_map=custom_map, last_round_multiplier=1.0)

pairs = (
    base_all[["Game", "SeasonLabel", "SeasonNum", "League Name"]]
    .dropna(subset=["Game", "SeasonLabel", "League Name"])
    .drop_duplicates()
)
pairs["SeasonLeague"] = pairs["SeasonLabel"].astype(str) + " — " + pairs["League Name"].astype(str)

if "flt_game" not in st.session_state:
    st.session_state["flt_game"] = "All"
if "flt_pair" not in st.session_state:
    st.session_state["flt_pair"] = "All"

games = sorted(pairs["Game"].unique().tolist())
game_options = ["All"] + games
game_sel = st.session_state["flt_game"] if st.session_state["flt_game"] in game_options else "All"
st.session_state["flt_game"] = game_sel

pairs_g = pairs if game_sel == "All" else pairs[pairs["Game"] == game_sel].copy()
pair_options = ["All"] + sorted(pairs_g["SeasonLeague"].dropna().unique().tolist())
if st.session_state["flt_pair"] not in pair_options:
    st.session_state["flt_pair"] = "All"
sel_pair = st.session_state["flt_pair"]

if sel_pair == "All":
    season_sel = "All"
    league_sel = "All"
else:
    season_sel, league_sel = sel_pair.split(" — ", 1)

df_filtered = base_all.copy()
if game_sel != "All":
    df_filtered = df_filtered[df_filtered["Game"] == game_sel]
if season_sel != "All":
    df_filtered = df_filtered[df_filtered["SeasonLabel"] == season_sel]
if league_sel != "All":
    df_filtered = df_filtered[df_filtered["League Name"] == league_sel]
df_filtered = effective_rows(df_filtered)

latest_df, latest_meta = latest_league_slice(base_all)
if "IsSeasonFinal" not in latest_df.columns:
    latest_df = mark_season_final(latest_df)
latest_gp = latest_df[~latest_df["IsSeasonFinal"]].copy()

tab_dash, tab_gp, tab_circuits, tab_all, tab_settings = st.tabs(tr(lang, "tabs"))

with tab_dash:
    st.caption(f"{tr(lang, 'current_season_only')}: {latest_meta['Game']} • {latest_meta['SeasonLabel']} • {latest_meta['League Name']}")

    a1, a2 = st.columns([1.05, 1.45], gap="large")
    with a1:
        st.subheader(tr(lang, "last_gp_results"))
        last_tbl, _ = last_gp_table(latest_gp, entity="Drivers")
        if last_tbl.empty:
            st.caption(tr(lang, "not_enough"))
        else:
            st.dataframe(localized_table(last_tbl, lang), use_container_width=True, hide_index=True)

    with a2:
        st.subheader(tr(lang, "standings"))
        latest_st = standings_table(latest_gp, entity="Drivers")
        st.dataframe(localized_table(latest_st, lang), use_container_width=True, hide_index=True)

    st.markdown(f"### {tr(lang, 'race_standings')}")
    if latest_gp.empty:
        st.info(tr(lang, "not_enough"))
    else:
        race_list = (
            latest_gp[["Round", "GP Name"]]
            .drop_duplicates()
            .sort_values(["Round", "GP Name"])
        )
        race_labels = [f"R{int(r.Round)} — {r['GP Name']}" for _, r in race_list.iterrows()]
        idx = st.session_state.get("dash_race_idx", len(race_labels)-1)
        idx = max(0, min(int(idx), len(race_labels)-1))

        c1, c2 = st.columns([0.8, 1.6], gap="large")
        with c1:
            selected_label = st.radio(tr(lang, "select_race"), race_labels, index=idx, key="dash_race_selector")
        selected_round = int(selected_label.split(" — ")[0].replace("R", ""))

        with c2:
            race_rows = latest_gp[latest_gp["Round"] == selected_round].copy()
            race_rows = race_rows.sort_values(["Finish Pos", "Driver"])
            cols = ["Finish Pos", "Driver", "Team", "Points"]
            st.dataframe(localized_table(race_rows[cols], lang), use_container_width=True, hide_index=True)

    st.markdown(f"### {tr(lang, 'tension')}")
    tension_metrics, tension_df, _ = championship_tension(latest_gp, entity_col="Driver")
    m1, m2, m3 = st.columns(3)
    m1.metric(tr(lang, "lead_swaps"), f"{int(tension_metrics['lead_swaps'])}")
    m2.metric(tr(lang, "gap_p1_p2"), "-" if np.isnan(tension_metrics["last_gap"]) else f"{tension_metrics['last_gap']:.0f}")
    m3.metric(tr(lang, "gap_top3"), "-" if np.isnan(tension_metrics["last_top3_spread"]) else f"{tension_metrics['last_top3_spread']:.0f}")

    if not tension_df.empty and PLOTLY_OK:
        tdf = tension_df.copy()
        tdf["EventLabel"] = "R" + tdf["EventIdx"].astype(int).astype(str)
        fig_gap = go.Figure()
        fig_gap.add_trace(go.Scatter(x=tdf["EventLabel"], y=tdf["GapP1P2"], mode="lines+markers", name=tr(lang, "gap_p1_p2"), line={"color": THEME_CFG["positive"]}))
        fig_gap.add_trace(go.Scatter(x=tdf["EventLabel"], y=tdf["Top3Spread"], mode="lines+markers", name=tr(lang, "gap_top3"), line={"color": THEME_CFG["neutral"]}))
        fig_gap.update_layout(template=THEME_CFG["plotly_template"], height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_gap, use_container_width=True)
    elif not tension_df.empty:
        st.line_chart(tension_df.set_index("EventIdx")[["GapP1P2", "Top3Spread"]], height=320)
    else:
        st.info(tr(lang, "not_enough"))

with tab_gp:
    d_gp = base_all.copy()
    if "IsSeasonFinal" not in d_gp.columns:
        d_gp = mark_season_final(d_gp)
    d_gp = d_gp[~d_gp["IsSeasonFinal"]].copy()

    gp_pairs = (
        d_gp[["SeasonLabel", "SeasonNum", "League Name"]]
        .dropna(subset=["SeasonLabel", "League Name"])
        .drop_duplicates()
        .copy()
    )
    gp_pairs["SeasonLeague"] = gp_pairs["SeasonLabel"].astype(str) + " — " + gp_pairs["League Name"].astype(str)
    gp_pairs["_SortKey"] = gp_pairs["SeasonNum"].fillna(gp_pairs["SeasonLabel"].map(_season_sort_key))
    gp_pairs = gp_pairs.sort_values(["_SortKey", "SeasonLabel", "League Name"], ascending=[False, False, True])

    seasonleague_options = gp_pairs["SeasonLeague"].unique().tolist()
    options = ["All (GP-only)"] + seasonleague_options
    sel_gp_pair = st.selectbox(tr(lang, "season_league_gp"), options, index=0, key="gp_pair")

    df_gp = d_gp.copy()
    gp_all_time = True
    if sel_gp_pair != "All (GP-only)":
        gp_season, gp_league = sel_gp_pair.split(" — ", 1)
        df_gp = df_gp[(df_gp["SeasonLabel"] == gp_season) & (df_gp["League Name"] == gp_league)].copy()
        st.caption(f"{gp_season} • {gp_league}")
        gp_all_time = False

    if df_gp.empty:
        st.info(f"{tr(lang, 'no_rows')} {tr(lang, 'empty_hint')}")
    else:
        view = st.radio(tr(lang, "standings_type"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="dash_view")
        view_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[view]
        entity_col = "Driver" if view_canon == "Drivers" else "Team"

        st_table = standings_table(df_gp, entity=view_canon)
        st.subheader(tr(lang, "standings"))
        show_form_cols = st.toggle(tr(lang, "show_form_cols"), value=False)
        if show_form_cols:
            form = form_table(df_gp, entity_col=entity_col)
            st_table = st_table.merge(form, on=entity_col, how="left") if not form.empty else st_table
        st.dataframe(localized_table(st_table, lang), use_container_width=True, hide_index=True)

        st.subheader("GP progression (cumulative points)")
        preset = st.radio(tr(lang, "chart_preset"), ["Top 5", "Top 10", "Custom"], horizontal=True, key="gp_chart_preset")
        if preset == "Top 5":
            top_n = 5
        elif preset == "Top 10":
            top_n = 10
        else:
            top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="gp_topn")

        wide, long = cumulative_points_wide(df_gp, entity_col=entity_col, all_time=gp_all_time)
        if not wide.empty and not long.empty:
            last_idx = wide.index.max()
            final = wide.tail(1).T.sort_values(by=last_idx, ascending=False)
            keep = final.head(top_n).index.tolist()
            long_k = long[long[entity_col].isin(keep)].copy()
            order_x = long_k.sort_values("EventIdx")[["EventIdx", "EventLabel"]].drop_duplicates().sort_values("EventIdx")["EventLabel"].tolist()
            last_pts = long_k.sort_values("EventIdx").groupby(entity_col)["CumPoints"].last().sort_values(ascending=False)
            order_entities = last_pts.index.tolist()
            if PLOTLY_OK:
                fig = px.line(long_k, x="EventLabel", y="CumPoints", color=entity_col, markers=True, category_orders={"EventLabel": order_x, entity_col: order_entities}, color_discrete_sequence=THEME_CFG["line_palette"], template=THEME_CFG["plotly_template"])
                fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
                fig.update_xaxes(type="category", title=("Timeline" if gp_all_time else "GPs"))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(wide[keep].ffill().fillna(0), height=360)

        st.markdown(f"### {tr(lang, 'position_delta')}")
        delta_tbl = position_delta_table(df_gp, entity_col=entity_col, n_momentum=3)
        if delta_tbl.empty:
            st.info(tr(lang, "not_enough"))
        else:
            delta_show = delta_tbl.rename(columns={"Delta": tr(lang, "change"), "MomentumL3": tr(lang, "momentum_l3")})
            st.dataframe(style_by_columns(localized_table(delta_show, lang), [tr(lang, "change"), tr(lang, "momentum_l3")]), use_container_width=True, hide_index=True)

with tab_circuits:
    st.subheader(tr(lang, "gp_winners_top3"))
    circuits = circuits_top3(base_all)
    if circuits.empty:
        st.info(tr(lang, "no_gp_winners"))
    else:
        circuits_show = circuits.rename(columns={"GP Name": "GP" if lang == "en" else "Grande Prémio"})
        st.dataframe(circuits_show, use_container_width=True, hide_index=True)

with tab_all:
    if base_all.empty:
        st.info("No data loaded.")
    else:
        st.subheader(tr(lang, "all_time_title"))
        base = base_all.copy()
        base["SeasonYear"] = base["SeasonLabel"].astype(str).str.extract(r"(\d{4})", expand=False).fillna(base["SeasonLabel"].astype(str))

        view_all = st.radio(tr(lang, "view"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="alltime_view")
        entity = "Driver" if view_all == tr(lang, "drivers") else "Team"

        totals = base.groupby(["SeasonYear", entity], as_index=False).agg(Points=("Points", "sum"))
        def _year_key(v):
            mm = re.search(r"(\d{4})", str(v))
            return int(mm.group(1)) if mm else 0
        season_order = sorted(totals["SeasonYear"].unique().tolist(), key=_year_key)
        totals["SeasonYear"] = pd.Categorical(totals["SeasonYear"], categories=season_order, ordered=True)
        totals = totals.sort_values(["SeasonYear"])
        totals["CumPoints"] = totals.groupby(entity)["Points"].cumsum()

        st.subheader(tr(lang, "all_time_progression"))
        top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="alltime_topn")
        final = totals.groupby(entity)["CumPoints"].max().sort_values(ascending=False)
        keep = final.head(top_n).index.tolist()
        plot_df = totals[totals[entity].isin(keep)].copy()
        if PLOTLY_OK:
            fig = px.line(plot_df, x="SeasonYear", y="CumPoints", color=entity, markers=True, category_orders={"SeasonYear": season_order, entity: keep}, color_discrete_sequence=THEME_CFG["line_palette"], template=THEME_CFG["plotly_template"])
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
           fig.update_xaxes(type="category", title=tr(lang, "season"))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader(tr(lang, "all_time_standings"))
        table_df = totals[["SeasonYear", entity, "Points", "CumPoints"]].sort_values(["SeasonYear", "Points"], ascending=[True, False])
        st.dataframe(localized_table(table_df, lang), use_container_width=True, hide_index=True)

with tab_settings:
    st.subheader(tr(lang, "theme"))
    theme_label_to_mode = {tr(lang, "theme_dark"): "Dark", tr(lang, "theme_light"): "Light"}
    current_theme_label = tr(lang, "theme_dark") if st.session_state.get("theme_mode", "Dark") == "Dark" else tr(lang, "theme_light")
    selected_theme_label = st.selectbox(tr(lang, "theme"), list(theme_label_to_mode.keys()), index=list(theme_label_to_mode.keys()).index(current_theme_label))
    selected_theme_mode = theme_label_to_mode[selected_theme_label]
    if selected_theme_mode != st.session_state.get("theme_mode", "Dark"):
        st.session_state["theme_mode"] = selected_theme_mode
        st.rerun()

    lang_idx = list(LANGS.keys()).index(lang_name)
    new_lang = st.selectbox(tr(lang, "language"), list(LANGS.keys()), index=lang_idx)
    if new_lang != st.session_state.get("app_lang", "English"):
        st.session_state["app_lang"] = new_lang
        st.rerun()

st.caption(tr(lang, "version"))
