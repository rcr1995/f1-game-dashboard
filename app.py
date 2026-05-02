import streamlit as st

import pandas as pd

import numpy as np

import json

import re

from pathlib import Path
from puskas_html import render_puskas_dashboard, render_puskas_hero

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

# Version

# -----------------------------

APP_VERSION = "v35"

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

        "tabs": ["🏁 Dashboard", "📊 GP Statistics", "🛣️ Circuits", "🏆 All‑time", "🔬 Analysis"],

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

        "version": f"F1 Game Dashboard • {APP_VERSION}",

        "language": "Language",

        "no_rows": "No rows match the current filters.",

        "not_enough": "Not enough data for this view.",

        "download": "Download CSV",

        "view": "View",

        "season_league_gp": "Season — League (GP-only)",

        "calendar_title": "League calendar",

        "calendar_upcoming": "Upcoming races",

                        "gp_progression": "GP progression (cumulative points)",
        "points_delta_vs_prev": "Points delta vs prev round",
        "total_wins_all_circuits": "Total race wins (all circuits)",
        "no_data_loaded": "No data loaded.",
        "next_race_label": "Next Race",
        "round_label": "Round",
        "leads_by": "leads",
        "by_pts": "pts",
        "section_label": "Section",
        "h2h_section_hd": "Head-to-Head",
        "h2h_sec_champ": "Championship Maths",
        "h2h_sec_teammate": "Teammate Battle",
        "h2h_sec_radar": "Performance Radar",
        "h2h_sec_sos": "Season-over-Season",
        "h2h_need_2": "Select at least 2 drivers.",
        "h2h_position": "Position",
        "h2h_points": "Points",
        "h2h_wins": "Wins",
        "h2h_podiums": "Podiums",
        "h2h_avg_finish": "Avg Finish",
        "h2h_pts_race": "Pts/Race",
        "h2h_progression_title": "Points progression comparison",
        "champ_leads": "leads",
        "champ_p1p2_gap": "P1–P2 Gap",
        "champ_max_pts_annotation": "Max pts left",
        "champ_round_label": "Round",
        "champ_pts_gap_label": "Points gap",
        "radar_axes_caption": "All axes normalised to 100 = best in current season. 'Avg Finish (inv)' = lower finish position is better.",
        "sos_solid": "Solid lines = Season A · Dashed lines = Season B",
        "sos_track": "Track",
        "sos_race_x": "Race number",
        "sos_cum_pts_y": "Cumulative points",
        "sos_need_2_seasons": "Need at least 2 seasons of data.",
        "streak_win": "Win streak",
        "streak_podium": "Podium streak",
        "streak_pts": "Points-finish streak",
        "streak_current_col": "Current",
        "streak_best_col": "Best",
        "about_title": "About",
        "about_desc": "Track your private F1 gaming league: standings, form, championship tension and all-time records.",
        "about_upload": "Upload your Excel file in the sidebar or place <code>F1_Standings.xlsx</code> in the project folder.",
        "sidebar_top3_label": "Top 3 — Quick glance",
        "sidebar_pts_unit": "pts",
        "teammate_pts_adv": "Pts Advantage",
        "teammate_drivers": "Drivers",
        "lucky_avg_gain_label": "Avg positions gained per race",
        "lucky_caption": "Positive = finished better than started. Negative = lost positions on average.",
        "lucky_no_grid": "No grid/qualifying position data found in your Excel. This metric requires a 'Grid Pos' or 'Start Pos' column.",
        "alt_compute_btn": "System",
        "alt_orig_pts": "OrigPoints",
        "calendar_next_race": "Next Race — Round",
        "timeline_label": "Timeline",
        "gp_label": "GPs",
        "all_gp_label": "All (GP-only)",
        "titles_plural": "titles",
        "title_singular": "title",
        "hero_leader": "Leader",
        "hero_points": "Points",
        "hero_gap": "P1\u2192P2 Gap",
        "hero_rounds": "Rounds",
        "hero_next_race": "Next Race",
"analysis_tab": "\U0001f52c Analysis",
        "h2h_title": "Head-to-Head Comparison",
        "h2h_select": "Select up to 3 drivers",
        "champ_maths_title": "Championship Maths",
        "champ_maths_open": "\U0001f7e2 Championship is still OPEN",
        "champ_maths_closed": "\U0001f534 Championship is MATHEMATICALLY DECIDED",
        "champ_maths_races_left": "Races remaining",
        "champ_maths_pts_left": "Max points still available",
        "champ_maths_needed": "Wins needed by P2 to catch leader",
        "teammate_title": "Teammate Battle",
        "teammate_ahead": "Ahead in standings",
        "radar_title": "Performance Radar",
        "radar_driver": "Select driver for radar",
        "sos_title": "Season-over-Season Comparison",
        "sos_season_a": "Season A",
        "sos_season_b": "Season B",
        "streak_title": "Streak Tracker",
        "streak_type": "Streak type",
        "lucky_title": "Lucky / Unlucky Index",
        "alt_scoring_title": "Alternative Scoring",
        "alt_classic": "Classic F1 (10-6-4-3-2-1)",
        "alt_top5": "Top 5 only (10-7-5-3-1)",
        "alt_wins_only": "Wins only (1 pt per win)",
        "export_btn": "Download Season Report (HTML)",
"calendar_done": "Completed races",

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

        "tabs": ["🏁 Dashboard", "📊 Estatísticas GP", "🛣️ Circuitos", "🏆 Histórico", "🔬 Análise"],

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

        "version": f"Dashboard F1 • {APP_VERSION}",

        "language": "Idioma",

        "no_rows": "Sem dados para os filtros atuais.",

        "not_enough": "Dados insuficientes para esta vista.",

        "download": "Download CSV",

        "view": "Vista",

        "season_league_gp": "Época — Liga (apenas GP)",

        "calendar_title": "Calendário da liga",

        "calendar_upcoming": "Próximas corridas",

                        "gp_progression": "Progressão GP (pontos acumulados)",
        "points_delta_vs_prev": "Delta de pontos vs ronda anterior",
        "total_wins_all_circuits": "Total de vitórias (todos os circuitos)",
        "no_data_loaded": "Sem dados carregados.",
        "next_race_label": "Próxima Corrida",
        "round_label": "Ronda",
        "leads_by": "lidera",
        "by_pts": "pts",
        "section_label": "Secção",
        "h2h_section_hd": "Frente-a-Frente",
        "h2h_sec_champ": "Matemática do Campeonato",
        "h2h_sec_teammate": "Duelo de Companheiros",
        "h2h_sec_radar": "Radar de Desempenho",
        "h2h_sec_sos": "Época-a-Época",
        "h2h_need_2": "Selecione pelo menos 2 pilotos.",
        "h2h_position": "Posição",
        "h2h_points": "Pontos",
        "h2h_wins": "Vitórias",
        "h2h_podiums": "Pódios",
        "h2h_avg_finish": "Média Posição",
        "h2h_pts_race": "Pts/Corrida",
        "h2h_progression_title": "Comparação da progressão em pontos",
        "champ_leads": "lidera",
        "champ_p1p2_gap": "Diferença P1–P2",
        "champ_max_pts_annotation": "Pts máx restantes",
        "champ_round_label": "Ronda",
        "champ_pts_gap_label": "Diferença de pontos",
        "radar_axes_caption": "Todos os eixos normalizados a 100 = melhor da época. 'Média Pos. (inv)' = posição mais baixa é melhor.",
        "sos_solid": "Linhas contínuas = Época A · Linhas tracejadas = Época B",
        "sos_track": "Veículo",
        "sos_race_x": "Número da corrida",
        "sos_cum_pts_y": "Pontos acumulados",
        "sos_need_2_seasons": "Necessita de pelo menos 2 épocas de dados.",
        "streak_win": "Sequência de vitórias",
        "streak_podium": "Sequência de pódios",
        "streak_pts": "Sequência de pontos",
        "streak_current_col": "Atual",
        "streak_best_col": "Melhor",
        "about_title": "Sobre",
        "about_desc": "Acompanhe a sua liga privada de F1: classificações, forma, tensão do campeonato e recordes históricos.",
        "about_upload": "Carregue o seu ficheiro Excel na barra lateral ou coloque <code>F1_Standings.xlsx</code> na pasta do projeto.",
        "sidebar_top3_label": "Top 3 — Resumo rápido",
        "sidebar_pts_unit": "pts",
        "teammate_pts_adv": "Vantagem em Pts",
        "teammate_drivers": "Pilotos",
        "lucky_avg_gain_label": "Posições ganhas em média por corrida",
        "lucky_caption": "Positivo = acabou melhor do que partiu. Negativo = perdeu posições em média.",
        "lucky_no_grid": "Sem dados de posição na grelha. Esta métrica requer a coluna 'Grid Pos' ou 'Start Pos'.",
        "alt_compute_btn": "Sistema",
        "alt_orig_pts": "Pts Originais",
        "calendar_next_race": "Próxima Corrida — Ronda",
        "timeline_label": "Linha temporal",
        "gp_label": "GPs",
        "all_gp_label": "Todos (apenas GP)",
        "titles_plural": "títulos",
        "title_singular": "título",
        "hero_leader": "L\u00edder",
        "hero_points": "Pontos",
        "hero_gap": "Dif. P1\u2192P2",
        "hero_rounds": "Rondas",
        "hero_next_race": "Pr\u00f3xima Corrida",
"analysis_tab": "\U0001f52c An\u00e1lise",
        "h2h_title": "Compara\u00e7\u00e3o Frente-a-Frente",
        "h2h_select": "Selecionar at\u00e9 3 pilotos",
        "champ_maths_title": "Matem\u00e1tica do Campeonato",
        "champ_maths_open": "\U0001f7e2 Campeonato ainda ABERTO",
        "champ_maths_closed": "\U0001f534 Campeonato MATEMATICAMENTE DECIDIDO",
        "champ_maths_races_left": "Corridas restantes",
        "champ_maths_pts_left": "Pontos m\u00e1ximos dispon\u00edveis",
        "champ_maths_needed": "Vit\u00f3rias necess\u00e1rias para alcan\u00e7ar o l\u00edder",
        "teammate_title": "Duelo de Companheiros",
        "teammate_ahead": "\u00c0 frente na classifica\u00e7\u00e3o",
        "radar_title": "Radar de Desempenho",
        "radar_driver": "Selecionar piloto para radar",
        "sos_title": "Compara\u00e7\u00e3o \u00c9poca-a-\u00c9poca",
        "sos_season_a": "\u00c9poca A",
        "sos_season_b": "\u00c9poca B",
        "streak_title": "Sequ\u00eancias",
        "streak_type": "Tipo de sequ\u00eancia",
        "lucky_title": "\u00cdndice Sorte / Azar",
        "alt_scoring_title": "Sistema de Pontua\u00e7\u00e3o Alternativo",
        "alt_classic": "F1 Cl\u00e1ssico (10-6-4-3-2-1)",
        "alt_top5": "Top 5 apenas (10-7-5-3-1)",
        "alt_wins_only": "Apenas vit\u00f3rias (1 pt por vit\u00f3ria)",
        "export_btn": "Download do Relat\u00f3rio (HTML)",
"calendar_done": "Corridas concluídas",
    },
}

def tr(lang: str, key: str):
    return T[lang].get(key, key)

def effective_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Avoid double-counting when both GP-level rows and season-total rows exist.

    Rule per (Game, Season, League):
    - if any GP-level rows exist: keep ONLY GP-level rows
    - else: keep season-final rows (one or more)
    """
    if df.empty:
        return df
    d = df.copy()

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
    # Trigger cache invalidation for new Time columns

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

@st.cache_data(show_spinner=False)
def load_calendar_from_excel(file) -> pd.DataFrame:
    try:
        df = pd.read_excel(file, sheet_name="Calendar")
    except Exception:
        return pd.DataFrame(columns=["League Name", "Round", "Date", "GP Name", "Status"])

    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        return pd.DataFrame(columns=["League Name", "Round", "Date", "GP Name", "Status"])

    keep = [c for c in ["League Name", "Round", "Date", "GP Name", "Circuit", "Status"] if c in df.columns]
    d = df[keep].copy()

    if "League Name" not in d.columns:
        d["League Name"] = ""
    if "Round" not in d.columns:
        d["Round"] = pd.NA
    if "Date" not in d.columns:
        d["Date"] = pd.NaT
    if "GP Name" not in d.columns:
        d["GP Name"] = ""
    if "Status" not in d.columns:
        d["Status"] = ""

    d["League Name"] = d["League Name"].astype(str).str.strip()
    d["Round"] = pd.to_numeric(d["Round"], errors="coerce").astype("Int64")
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    d["GP Name"] = d["GP Name"].astype(str).str.strip()
    d["Status"] = d["Status"].astype(str).str.strip()

    d = d[~(d["GP Name"].eq("") & d["Date"].isna())].copy()
    d = d.sort_values(["Round", "Date", "GP Name"], na_position="last").reset_index(drop=True)
    return d

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

    d = df[~df["IsSeasonFinal"]].copy()
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
    d0 = df[~df["IsSeasonFinal"]].copy()
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
    d = df[(~df["IsSeasonFinal"]) & (df["Finish Pos"] == 1)].copy()
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
                :root {
                    --bg-app: #f8f9fa;
                    --bg-panel: #ffffff;
                    --bg-card: linear-gradient(145deg, #ffffff, #f9fafb);
                    --bg-hero: linear-gradient(135deg, #ffefef 0%, #fcfcfc 45%, #f8f9fa 100%);
                    --bg-sidebar: #f3f4f6;
                    --text-main: #111827;
                    --text-muted: #4b5563;
                    --text-faint: #9ca3af;
                    --border-color: #e5e7eb;
                    --pill-done-bg: #d1fae5; --pill-done-text: #059669;
                    --pill-up-bg: #dbeafe;   --pill-up-text: #2563eb;
                    --pill-tbd-bg: #e5e7eb;  --pill-tbd-text: #4b5563;
                    --title-card-bg: linear-gradient(145deg, #fffbeb, #ffffff);
                    --title-card-border: #fde68a;
                    --h2h-bg: linear-gradient(145deg, #ffffff, #f3f4f6);
                    --next-race-bg: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
                    --scrollbar-track: #e5e7eb;
                    --maths-bg: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
                    --maths-open-bg: linear-gradient(135deg, #ecfdf5, #ffffff);
                    --maths-closed-bg: linear-gradient(135deg, #fef2f2, #ffffff);
                }
                .stApp { background-color: var(--bg-app); color: var(--text-main); }
                div[data-testid='stMetricValue'] { font-size: 1.2rem; color: var(--text-main); }
                .stTabs [role="tab"] { color: var(--text-muted) !important; }
                .stTabs [role="tab"][aria-selected="true"] { color: var(--text-main) !important; font-weight: 700; }
                div[data-testid="stDataFrame"] { color: var(--text-main); }
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
            :root {
                --bg-app: #0a0d14;
                --bg-panel: #10151c;
                --bg-card: linear-gradient(145deg, #161b22, #0f1117);
                --bg-hero: linear-gradient(135deg, #1a0000 0%, #0e1117 45%, #0a0d14 100%);
                --bg-sidebar: #07090e;
                --text-main: #FAFAFA;
                --text-muted: #888888;
                --text-faint: #555555;
                --border-color: #21262d;
                --pill-done-bg: #0d3322; --pill-done-text: #2ecc71;
                --pill-up-bg: #0a1e38;   --pill-up-text: #58a6ff;
                --pill-tbd-bg: #1a1f28;  --pill-tbd-text: #666666;
                --title-card-bg: linear-gradient(145deg, #1c1400, #0f1117);
                --title-card-border: #2e2200;
                --h2h-bg: linear-gradient(145deg, #10151f, #0a0d14);
                --next-race-bg: linear-gradient(135deg, #0a1e38 0%, #070c17 100%);
                --scrollbar-track: #0a0d14;
                --maths-bg: linear-gradient(135deg, #0d2037 0%, #0a0d14 100%);
                --maths-open-bg: linear-gradient(135deg, #0d2a1a, #0a0d14);
                --maths-closed-bg: linear-gradient(135deg, #1a0a0a, #0a0d14);
            }
            div[data-testid='stMetricValue'] { font-size: 1.2rem; color: var(--text-main); }
            .stTabs [role="tab"] { color: var(--text-muted) !important; }
            .stTabs [role="tab"][aria-selected="true"] { color: var(--text-main) !important; font-weight: 700; }
            </style>
        """,
    }

def apply_theme_css(theme_cfg: dict):
    st.html(theme_cfg["css"])

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

# ─────────────────────────────────────────────────────────────────────────────
# Global CSS & UI helpers
# ─────────────────────────────────────────────────────────────────────────────
GLOBAL_CSS = """
<style>
/* ── Custom scrollbar ─────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--scrollbar-track); }
::-webkit-scrollbar-thumb { background: #E10600; border-radius: 3px; }

/* ── App shell ────────────────────────────────────────────── */
.stApp { background: var(--bg-app); }

/* ── Hero banner ──────────────────────────────────────────── */
.f1-hero {
    background: var(--bg-hero);
    border: 1px solid rgba(225,6,0,0.2);
    border-left: 4px solid #E10600;
    border-radius: 12px;
    padding: 1.1rem 1.6rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0;
    flex-wrap: wrap;
    box-shadow: 0 0 28px rgba(225,6,0,0.06);
}
.f1-hero-main { min-width: 160px; margin-right: 1rem; }
.f1-hero-title {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: #E10600;
    margin-bottom: 0.15rem;
    font-weight: 700;
}
.f1-hero-value {
    font-size: 1.45rem;
    font-weight: 800;
    color: var(--text-main);
    line-height: 1.2;
}
.f1-hero-sub {
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 0.1rem;
}
.f1-stat-card {
    text-align: center;
    padding: 0.3rem 1.1rem;
    border-left: 1px solid var(--border-color);
    min-width: 90px;
}
.f1-stat-gap { color: #E10600 !important; }

/* ── Metric cards ─────────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 0.8rem 1rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stMetric"]:hover {
    border-color: rgba(225,6,0,0.4);
    box-shadow: 0 0 14px rgba(225,6,0,0.1);
}
div[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 700;
    color: var(--text-main);
}
div[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-muted) !important;
}

/* ── Tabs ─────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    border-bottom: 1px solid var(--border-color) !important;
    background: transparent !important;
}
.stTabs [role="tab"] {
    color: var(--text-muted) !important;
    font-size: 0.8rem !important;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 0.45rem 0.9rem !important;
    border-radius: 8px 8px 0 0 !important;
    transition: color 0.2s, background 0.2s;
    background: transparent !important;
}
.stTabs [role="tab"]:hover {
    color: var(--text-main) !important;
    background: rgba(225,6,0,0.04) !important;
}
.stTabs [role="tab"][aria-selected="true"] {
    color: var(--text-main) !important;
    font-weight: 700 !important;
    background: rgba(225,6,0,0.08) !important;
    border-bottom: 2px solid #E10600 !important;
}

/* ── Sidebar ──────────────────────────────────────────────── */
div[data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border-color) !important;
}
div[data-testid="stSidebar"] hr {
    border-color: #E10600 !important;
    opacity: 0.2;
}

/* ── Buttons ──────────────────────────────────────────────── */
.stDownloadButton button, .stButton > button {
    border-radius: 6px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stDownloadButton button:hover, .stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(225,6,0,0.15) !important;
}

/* ── Section headings ─────────────────────────────────────── */
h2, h3 {
    border-left: 3px solid #E10600;
    padding-left: 0.55rem !important;
    margin-top: 1.2rem !important;
    color: var(--text-main) !important;
}

/* ── Status pills ─────────────────────────────────────────── */
.pill-done     { display:inline-block; padding:2px 11px; border-radius:999px;
                 background:var(--pill-done-bg); color:var(--pill-done-text); font-size:0.74rem; font-weight:600; }
.pill-upcoming { display:inline-block; padding:2px 11px; border-radius:999px;
                 background:var(--pill-up-bg); color:var(--pill-up-text); font-size:0.74rem; font-weight:600; }
.pill-tbd      { display:inline-block; padding:2px 11px; border-radius:999px;
                 background:var(--pill-tbd-bg); color:var(--pill-tbd-text); font-size:0.74rem; font-weight:600; }

/* ── Next-race box ────────────────────────────────────────── */
.next-race-box {
    background: var(--next-race-bg);
    border: 1px solid rgba(88,166,255,0.25);
    border-left: 4px solid #58a6ff;
    border-radius: 10px;
    padding: 0.9rem 1.3rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 0 18px rgba(88,166,255,0.05);
}
.next-race-label { font-size:0.65rem; text-transform:uppercase; letter-spacing:0.15em; color:#3b82f6; font-weight:700; }
.next-race-name  { font-size:1.2rem; font-weight:800; color:var(--text-main); margin:0.15rem 0; }
.next-race-sub   { font-size:0.75rem; color:var(--text-muted); }

/* ── All-time title cards ─────────────────────────────────── */
.title-card {
    background: var(--title-card-bg);
    border: 1px solid var(--title-card-border);
    border-top: 3px solid #f5c518;
    border-radius: 10px;
    padding: 0.8rem 0.6rem;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
    height: 100%;
}
.title-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 24px rgba(245,197,24,0.1);
}
.title-card-name  { font-weight:700; font-size:0.9rem; color:var(--text-main); margin-bottom:0.3rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.title-card-count { font-size:2rem; font-weight:800; color:#f5c518; line-height:1; }
.title-card-label { font-size:0.6rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--text-muted); margin-top:0.2rem; }

/* ── About card (settings) ────────────────────────────────── */
.about-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 1.1rem 1.4rem;
    margin-top: 1.5rem;
}
.about-card h4 { color: #E10600; margin-bottom: 0.4rem; }
.about-card p  { color: var(--text-muted); font-size: 0.82rem; margin: 0.2rem 0; }

/* ── Head-to-Head comparison cards ────────────────────────── */
.h2h-card {
    background: var(--h2h-bg);
    border: 1px solid var(--border-color); border-top: 3px solid #E10600;
    border-radius: 10px; padding: 1rem 1.2rem; text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}
.h2h-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(225,6,0,0.1); }
.h2h-driver { font-size: 1.05rem; font-weight: 800; color: var(--text-main); margin-bottom: 0.5rem; }
.h2h-stat   { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.1em; }
.h2h-val    { font-size: 1.3rem; font-weight: 700; color: #E10600; }
.h2h-best   { color: #d97706 !important; }

/* ── Championship maths card ──────────────────────────────── */
.maths-card { background: var(--maths-bg);
    border: 1px solid rgba(88,166,255,0.2); border-left: 4px solid #58a6ff;
    border-radius: 10px; padding: 1.2rem 1.6rem; margin-bottom: 1rem; }
.maths-open   { border-left-color: #2ecc71 !important; background: var(--maths-open-bg) !important; }
.maths-closed { border-left-color: #E10600 !important; background: var(--maths-closed-bg) !important; }

/* ── Streak pill ─────────────────────────────────────────── */
.streak-pill { display:inline-block; background: rgba(225,6,0,0.05); border:1px solid rgba(225,6,0,0.2);
    border-radius:999px; padding:2px 12px; font-size:0.8rem; font-weight:700; color:#E10600; margin:2px 4px; }

/* ── Quick-compare sidebar ────────────────────────────────── */
.qc-row { display:flex;justify-content:space-between;align-items:center;
    padding:4px 0;border-bottom:1px solid var(--border-color); }
.qc-pos  { font-weight:800; color:#E10600; min-width:18px; }
.qc-name { flex:1; padding:0 6px; font-size:0.87rem; color: var(--text-main); }
.qc-pts  { font-size:0.87rem; color: var(--text-muted); }
</style>
"""

def style_pos_column(df: pd.DataFrame, pos_col: str = "Pos", is_light: bool = False):
    """Return a Pandas Styler with gold/silver/bronze on the position column."""
    def _row(row):
        try:
            p = int(row[pos_col])
        except Exception:
            return [""] * len(row)
        
        if p == 1:
            css = "background:#fef3c7;color:#b45309;font-weight:700;" if is_light else "background:#2a1f00;color:#f5c518;font-weight:700;"
        elif p == 2:
            css = "background:#f3f4f6;color:#4b5563;font-weight:700;" if is_light else "background:#161a20;color:#a8a9ad;font-weight:700;"
        elif p == 3:
            css = "background:#ffedd5;color:#9a3412;font-weight:700;" if is_light else "background:#1c1008;color:#cd7f32;font-weight:700;"
        else:
            css = ""
            
        return [css if row.index[i] == pos_col else "" for i in range(len(row))]
    return df.style.apply(_row, axis=1)

def render_hero(lang: str, meta: dict, gp_df: pd.DataFrame, calendar_df: pd.DataFrame | None = None):
    """Hero banner: season context + leader stats + optional next-race block."""
    season = meta.get("SeasonLabel", "—")
    league = meta.get("League Name", "—")
    game   = meta.get("Game", "—")
    leader, leader_pts, gap, rounds = "—", "—", "—", "—"
    if not gp_df.empty:
        st_tbl = standings_table(gp_df, entity="Drivers")
        if not st_tbl.empty:
            leader     = str(st_tbl.iloc[0]["Driver"])
            leader_pts = int(st_tbl.iloc[0]["Points"])
            rounds     = int(gp_df["Round"].nunique())
            if len(st_tbl) > 1:
                gap = int(leader_pts - st_tbl.iloc[1]["Points"])

    # ── Next race lookup ──
    next_race_html = ""
    if calendar_df is not None and not calendar_df.empty:
        cal = calendar_df.copy()
        if "League Name" in cal.columns and league != "—":
            cal = cal[cal["League Name"] == league]
        upcoming = cal[cal["Status"].astype(str).str.lower() == "upcoming"] if "Status" in cal.columns else cal.iloc[0:0]
        if not upcoming.empty:
            nr = upcoming.iloc[0]
            nr_round   = int(nr["Round"]) if "Round" in nr and str(nr["Round"]) not in ("", "nan", "<NA>") else ""
            nr_gp      = str(nr.get("GP Name", "")).strip()
            nr_circuit = str(nr.get("Circuit", "")).strip()
            nr_date    = ""
            if "Date" in nr:
                try:
                    nr_date = pd.Timestamp(nr["Date"]).strftime("%d %b %Y")
                except Exception:
                    nr_date = str(nr["Date"])
            circ_line  = f"{nr_circuit} &bull; " if nr_circuit and nr_circuit != "nan" else ""
            round_line = f"{tr(lang,'hero_rounds')} {nr_round}" if nr_round != "" else ""
            next_race_html = (
                '<div class="f1-stat-card" style="border-left:1px solid #21262d;padding-left:1.4rem;">' +
                f'<div class="f1-hero-title" style="color:#58a6ff">&#x1F535; {tr(lang,"hero_next_race")}' + (f" — {round_line}" if round_line else "") + '</div>' +
                f'<div class="f1-hero-value" style="font-size:1.05rem;color:#FAFAFA">{nr_gp}</div>' +
                f'<div class="f1-hero-sub">{circ_line}{nr_date}</div>' +
                '</div>'
            )

    html = (
        '<div class="f1-hero">' +
        '<div class="f1-hero-main">' +
        f'<div class="f1-hero-title">{game}</div>' +
        f'<div class="f1-hero-value">{season}</div>' +
        f'<div class="f1-hero-sub">{league}</div>' +
        '</div>' +
        '<div class="f1-stat-card">' +
        f'<div class="f1-hero-title">{tr(lang,"hero_leader")}</div>' +
        f'<div class="f1-hero-value" style="font-size:1.1rem">{leader}</div>' +
        '</div>' +
        '<div class="f1-stat-card">' +
        f'<div class="f1-hero-title">{tr(lang,"hero_points")}</div>' +
        f'<div class="f1-hero-value">{leader_pts}</div>' +
        '</div>' +
        '<div class="f1-stat-card">' +
        f'<div class="f1-hero-title">{tr(lang,"hero_gap")}</div>' +
        f'<div class="f1-hero-value f1-stat-gap">{gap}</div>' +
        '</div>' +
        '<div class="f1-stat-card">' +
        f'<div class="f1-hero-title">{tr(lang,"hero_rounds")}</div>' +
        f'<div class="f1-hero-value">{rounds}</div>' +
        '</div>' +
        next_race_html +
        '</div>'
    )
    st.html(html)

def render_movers_chart(df: pd.DataFrame, entity_col: str, top_n: int = 6):
    """Horizontal bar chart of biggest point gainers/losers in the last round."""
    if df.empty or not PLOTLY_OK:
        return
    d = df.copy()
    last_r = int(d["Round"].max())
    prev_r = int(d[d["Round"] < last_r]["Round"].max()) if len(d[d["Round"] < last_r]) else None
    if prev_r is None:
        return
    pts_last = d[d["Round"] == last_r].groupby(entity_col)["Points"].sum().rename("Last")
    pts_prev = d[d["Round"] == prev_r].groupby(entity_col)["Points"].sum().rename("Prev")
    delta = pd.concat([pts_last, pts_prev], axis=1).fillna(0)
    delta["Delta"] = delta["Last"] - delta["Prev"]
    delta = delta.sort_values("Delta")
    colors = [THEME_CFG["positive"] if v >= 0 else THEME_CFG["negative"] for v in delta["Delta"]]
    fig_m = go.Figure(go.Bar(
        x=delta["Delta"],
        y=delta.index.tolist(),
        orientation="h",
        marker_color=colors,
        text=[f"+{v:.0f}" if v >= 0 else f"{v:.0f}" for v in delta["Delta"]],
        textposition="outside",
    ))
    fig_m.update_layout(
        template=THEME_CFG["plotly_template"],
        height=max(220, len(delta) * 28),
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis_title=tr(lang, "points_delta_vs_prev"),
        yaxis_title="",
    )
    st.plotly_chart(fig_m, use_container_width=True)

if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Dark"
if "app_lang" not in st.session_state:
    st.session_state["app_lang"] = "English"

lang_name = st.session_state.get("app_lang", "English")
lang_name = lang_name if lang_name in LANGS else "English"
lang = LANGS[lang_name]

THEME_CFG = theme_palette(st.session_state.get("theme_mode", "Dark"))
apply_theme_css(THEME_CFG)
st.html(GLOBAL_CSS)

# st.title(tr(lang, "title"))

with st.sidebar:
    st.header(tr(lang, "data"))
    uploaded = st.file_uploader(tr(lang, "upload"), type=["xlsx"], help=tr(lang, "upload_help"), key="sidebar_excel_upload")
    if uploaded is None:
        bundled = find_bundled_excel()
        if bundled is None:
            st.warning(tr(lang, "no_bundled"))
            st.stop()
        st.caption(tr(lang, "using_bundled") + f"  \n• `{bundled}`")
        raw = load_data_from_excel(bundled)
        calendar_raw = load_calendar_from_excel(bundled)
    else:
        raw = load_data_from_excel(uploaded)
        calendar_raw = load_calendar_from_excel(uploaded)

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
pairs["SeasonLeague"] = pairs["SeasonLabel"].astype(str) + " ||| " + pairs["League Name"].astype(str)

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
    season_sel, league_sel = sel_pair.split(" ||| ", 1)

df_filtered = base_all.copy()
if game_sel != "All":
    df_filtered = df_filtered[df_filtered["Game"] == game_sel]
if season_sel != "All":
    df_filtered = df_filtered[df_filtered["SeasonLabel"] == season_sel]
if league_sel != "All":
    df_filtered = df_filtered[df_filtered["League Name"] == league_sel]
df_filtered = effective_rows(df_filtered)

latest_df, latest_meta = latest_league_slice(base_all)
latest_gp = latest_df[~latest_df["IsSeasonFinal"]].copy()
# render_hero(lang, latest_meta, latest_gp, calendar_raw)
st_tbl_latest = standings_table(latest_gp, entity="Drivers") if not latest_gp.empty else pd.DataFrame()

tab_dash, tab_gp, tab_circuits, tab_all, tab_analysis = st.tabs(tr(lang, "tabs"))

with st.sidebar:

    # ── Quick-compare: persistent Top-3 widget ──────────────────────────
    if not st_tbl_latest.empty:
        st.markdown("---")
        st.caption(f"📊 **{tr(lang, 'sidebar_top3_label')}**")
        top3 = st_tbl_latest.head(3)
        gap_to_leader = None
        if len(top3) > 1:
            gap_to_leader = int(top3.iloc[0]["Points"] - top3.iloc[1]["Points"])
        rows_html = ""
        for _, r in top3.iterrows():
            gap_str = ""
            if r["Pos"] > 1 and not st_tbl_latest.empty:
                g = int(st_tbl_latest.iloc[0]["Points"] - r["Points"])
                gap_str = f' <span style="color:#E10600;font-size:0.75rem">-{g}</span>'
            rows_html += (
                f'<div class="qc-row">' +
                f'<span class="qc-pos">P{int(r["Pos"])}</span>' +
                f'<span class="qc-name">{r["Driver"]}</span>' +
                f'<span class="qc-pts">{int(r["Points"])} pts{gap_str}</span>' +
                '</div>'
            )
        st.html(rows_html)

with tab_dash:
    st.html(render_puskas_hero(latest_meta))
    html_dashboard = render_puskas_dashboard(latest_gp, calendar_raw, st_tbl_latest, latest_meta)
    import streamlit.components.v1 as stc
    stc.html(html_dashboard, height=1800, scrolling=False)



with tab_gp:
    d_gp = base_all[~base_all["IsSeasonFinal"]].copy()

    gp_pairs = (
        d_gp[["SeasonLabel", "SeasonNum", "League Name"]]
        .dropna(subset=["SeasonLabel", "League Name"])
        .drop_duplicates()
        .copy()
    )
    gp_pairs["SeasonLeague"] = gp_pairs["SeasonLabel"].astype(str) + " ||| " + gp_pairs["League Name"].astype(str)
    gp_pairs["_SortKey"] = gp_pairs["SeasonNum"].fillna(gp_pairs["SeasonLabel"].map(_season_sort_key))
    gp_pairs = gp_pairs.sort_values(["_SortKey", "SeasonLabel", "League Name"], ascending=[False, False, True])

    seasonleague_options = gp_pairs["SeasonLeague"].unique().tolist()
    options = [tr(lang, "all_gp_label")] + seasonleague_options
    sel_gp_pair = st.selectbox(tr(lang, "season_league_gp"), options, index=0, key="gp_pair")

    df_gp = d_gp.copy()
    gp_all_time = True
    if sel_gp_pair != tr(lang, "all_gp_label"):
        gp_season, gp_league = sel_gp_pair.split(" ||| ", 1)
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
        loc_st = localized_table(st_table, lang)
        if "Pos" in loc_st.columns:
            st.dataframe(style_pos_column(loc_st, is_light=(st.session_state.get("theme_mode", "Dark") == "Light")), use_container_width=True, hide_index=True)
        else:
            st.dataframe(loc_st, use_container_width=True, hide_index=True)

        st.subheader(tr(lang, "gp_progression"))
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
                fig = px.line(long_k, x="EventLabel", y="CumPoints", color=entity_col, markers=True,
                              category_orders={"EventLabel": order_x, entity_col: order_entities},
                              color_discrete_sequence=THEME_CFG["line_palette"],
                              template=THEME_CFG["plotly_template"])
                fig.update_layout(height=550, margin=dict(l=10, r=10, t=10, b=40), legend_title_text="")
                fig.update_xaxes(type="category", title=(tr(lang,"timeline_label") if gp_all_time else tr(lang,"gp_label")),
                                 rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(wide[keep].ffill().fillna(0), height=550)

        st.markdown(f"### {tr(lang, 'tension')}")
        _, gp_tension_df, _ = championship_tension(df_gp, entity_col=entity_col)
        if not gp_tension_df.empty and PLOTLY_OK:
            tdf = gp_tension_df.copy()
            tdf["EventLabel"] = "R" + tdf["EventIdx"].astype(int).astype(str)
            fig_tension = go.Figure()
            fig_tension.add_trace(go.Scatter(
                x=tdf["EventLabel"], y=tdf["GapP1P2"],
                mode="lines+markers", name=tr(lang, "gap_p1_p2"),
                fill="tozeroy", fillcolor="rgba(46,204,113,0.1)",
                line={"color": THEME_CFG["positive"], "width": 2},
            ))
            fig_tension.add_trace(go.Scatter(
                x=tdf["EventLabel"], y=tdf["Top3Spread"],
                mode="lines+markers", name=tr(lang, "gap_top3"),

                fill="tozeroy", fillcolor="rgba(176,176,176,0.07)",

                line={"color": THEME_CFG["neutral"], "width": 2},

            ))

            fig_tension.update_layout(

                template=THEME_CFG["plotly_template"], height=360,

                margin=dict(l=10, r=10, t=10, b=10),

                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),

            )

            st.plotly_chart(fig_tension, use_container_width=True)

        elif not gp_tension_df.empty:

            st.line_chart(gp_tension_df.set_index("EventIdx")[["GapP1P2", "Top3Spread"]], height=360)

        else:

            st.info(tr(lang, "not_enough"))

        st.markdown(f"### {tr(lang, 'position_delta')}")

        delta_tbl = position_delta_table(df_gp, entity_col=entity_col, n_momentum=3)

        if delta_tbl.empty:

            st.info(tr(lang, "not_enough"))

        else:

            delta_show = delta_tbl.rename(columns={"Delta": tr(lang, "change"), "MomentumL3": tr(lang, "momentum_l3")})

            st.dataframe(style_by_columns(localized_table(delta_show, lang), [tr(lang, "change"), tr(lang, "momentum_l3")]), use_container_width=True, hide_index=True)

        st.markdown(f"### {tr(lang, 'biggest_movers')}")

        render_movers_chart(df_gp, entity_col=entity_col)

with tab_circuits:

    st.subheader(tr(lang, "gp_winners_top3"))

    circuits = circuits_top3(base_all)

    if circuits.empty:

        st.info(tr(lang, "no_gp_winners"))

    else:

        # ── Wins-per-circuit horizontal bar chart ──

        d_cir = base_all[(~base_all["IsSeasonFinal"]) & (base_all["Finish Pos"] == 1)].copy()

        if not d_cir.empty and PLOTLY_OK:

            wins_per_driver = d_cir.groupby("Driver").size().reset_index(name="Wins").sort_values("Wins", ascending=True)
            fig_cir = go.Figure(go.Bar(
                x=wins_per_driver["Wins"],
                y=wins_per_driver["Driver"],
                orientation="h",
                marker_color="#E10600",
                text=wins_per_driver["Wins"],
                textposition="outside",
            ))
            fig_cir.update_layout(
                template=THEME_CFG["plotly_template"],
                height=max(300, len(wins_per_driver) * 28),
                margin=dict(l=10, r=50, t=10, b=10),
                xaxis_title=tr(lang, "total_wins_all_circuits"),
                yaxis_title="",
            )
            st.plotly_chart(fig_cir, use_container_width=True)

        circuits_show = circuits.rename(columns={"GP Name": "GP" if lang == "en" else "Grande Prémio"})

        st.dataframe(circuits_show, use_container_width=True, hide_index=True)

with tab_all:

    if base_all.empty:

        st.info(tr(lang, "no_data_loaded"))

    else:

        st.subheader(tr(lang, "all_time_title"))

        base = base_all.copy()

        view_all = st.radio(

            tr(lang, "view"),

            [tr(lang, "drivers"), tr(lang, "constructors")],

            horizontal=True,

            key="alltime_view",

        )

        entity = "Driver" if view_all == tr(lang, "drivers") else "Team"

        # ── Title cards row ──

        tc_df, _ = titles_count(base, entity_col=entity)

        if not tc_df.empty:

            champ_top = tc_df.head(8)

            cols_tc = st.columns(len(champ_top))

            for i, (_, row) in enumerate(champ_top.iterrows()):

                with cols_tc[i]:

                    st.html(f"""

                    <div class="title-card">

                      <div class="title-card-name" title="{row['Champion']}">{row['Champion']}</div>

                      <div class="title-card-count">{int(row['Titles'])}</div>

                      <div class="title-card-label">{'🏆 ' + (tr(lang,"titles_plural") if row["Titles"] != 1 else tr(lang,"title_singular"))}</div>

                    </div>

                    """)

            st.html("<br>")

        # ── Progression chart ──

        totals = base.groupby(["SeasonLabel", entity], as_index=False).agg(Points=("Points", "sum"))

        season_order = sorted(totals["SeasonLabel"].unique().tolist(), key=_season_sort_key)

        totals["SeasonLabel"] = pd.Categorical(totals["SeasonLabel"], categories=season_order, ordered=True)

        totals = totals.sort_values(["SeasonLabel"])

        totals["CumPoints"] = totals.groupby(entity)["Points"].cumsum()

        st.subheader(tr(lang, "all_time_progression"))

        top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="alltime_topn")

        final = totals.groupby(entity)["CumPoints"].max().sort_values(ascending=False)

        keep  = final.head(top_n).index.tolist()

        plot_df = totals[totals[entity].isin(keep)].copy()

        if PLOTLY_OK:

            fig = px.line(

                plot_df, x="SeasonLabel", y="CumPoints", color=entity, markers=True,

                category_orders={"SeasonLabel": season_order, entity: keep},

                color_discrete_sequence=THEME_CFG["line_palette"],

                template=THEME_CFG["plotly_template"],

            )

            fig.update_layout(

                height=460, margin=dict(l=10, r=10, t=10, b=40), legend_title_text="",

                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),

            )

            fig.update_xaxes(type="category", title=tr(lang, "season"))

            st.plotly_chart(fig, use_container_width=True)

        st.subheader(tr(lang, "all_time_standings"))

        table_df = totals[["SeasonLabel", entity, "Points", "CumPoints"]].sort_values(

            ["SeasonLabel", "Points"], ascending=[True, False],

        )

        st.dataframe(localized_table(table_df, lang), use_container_width=True, hide_index=True)



# ═══════════════════════════════════════════════════════════════════════════
# TAB: ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════
with tab_analysis:
    all_drivers = sorted(latest_gp["Driver"].dropna().unique().tolist()) if not latest_gp.empty else []
    st_tbl_latest = standings_table(latest_gp, entity="Drivers") if not latest_gp.empty else pd.DataFrame()

    analysis_section = st.radio(
        tr(lang, "section_label"),
        [tr(lang,"h2h_section_hd"), tr(lang,"h2h_sec_champ"), tr(lang,"h2h_sec_teammate"), tr(lang,"h2h_sec_radar"), tr(lang,"h2h_sec_sos")],
        horizontal=True,
        key="analysis_section_radio",
    )

    st.markdown("---")

    # ── A1: Head-to-Head ─────────────────────────────────────────────────
    if analysis_section == tr(lang, "h2h_section_hd"):
        st.subheader(tr(lang, "h2h_title"))
        if len(all_drivers) < 2:
            st.info(tr(lang, "not_enough"))
        else:
            defaults = all_drivers[:min(3, len(all_drivers))]
            sel_drivers = st.multiselect(
                tr(lang, "h2h_select"),
                all_drivers,
                default=defaults,
                max_selections=3,
                key="h2h_drivers",
            )
            if len(sel_drivers) < 2:
                st.info(tr(lang, "h2h_need_2"))
            else:
                # Stat cards row
                cols_h2h = st.columns(len(sel_drivers))
                stat_rows = []
                for d in sel_drivers:
                    row = st_tbl_latest[st_tbl_latest["Driver"] == d]
                    if row.empty:
                        stat_rows.append({})
                        continue
                    r = row.iloc[0]
                    stat_rows.append({
                        "Pos": int(r.get("Pos", 0)),
                        "Points": int(r.get("Points", 0)),
                        "Wins": int(r.get("Wins", 0)),
                        "Podiums": int(r.get("Podiums", 0)),
                        "Races": int(r.get("Races", 0)),
                        "AvgFinish": float(r.get("AvgFinish", 0)),
                        "PtsPerRace": float(r.get("Pts/Race", 0)),
                    })

                for i, (d, sr) in enumerate(zip(sel_drivers, stat_rows)):
                    if not sr:
                        continue
                    # find bests across compared drivers
                    best_pts  = max(s.get("Points",0) for s in stat_rows if s)
                    best_wins = max(s.get("Wins",0) for s in stat_rows if s)
                    best_avg  = min(s.get("AvgFinish",99) for s in stat_rows if s)
                    with cols_h2h[i]:
                        pts_cls  = "h2h-best" if sr["Points"]    == best_pts  else ""
                        wins_cls = "h2h-best" if sr["Wins"]       == best_wins else ""
                        avg_cls  = "h2h-best" if sr["AvgFinish"]  == best_avg  else ""

                        # Color swatch per driver (cycle through 3 accent colors)
                        DRIVER_COLORS = ["#E10600", "#58a6ff", "#f5c518"]
                        border_color = DRIVER_COLORS[i % 3]
                        st.html(f"""
                        <div class="h2h-card" style="border-top-color:{border_color}">
                          <div class="h2h-driver">{d}</div>
                          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-top:0.5rem">
                            <div><div class="h2h-stat">{tr(lang,"h2h_position")}</div><div class="h2h-val">P{sr["Pos"]}</div></div>
                            <div><div class="h2h-stat">{tr(lang,"h2h_points")}</div><div class="h2h-val {pts_cls}">{sr["Points"]}</div></div>
                            <div><div class="h2h-stat">{tr(lang,"h2h_wins")}</div><div class="h2h-val {wins_cls}">{sr["Wins"]}</div></div>
                            <div><div class="h2h-stat">{tr(lang,"h2h_podiums")}</div><div class="h2h-val">{sr["Podiums"]}</div></div>
                            <div><div class="h2h-stat">{tr(lang,"h2h_avg_finish")}</div><div class="h2h-val {avg_cls}">{sr["AvgFinish"]:.1f}</div></div>
                            <div><div class="h2h-stat">{tr(lang,"h2h_pts_race")}</div><div class="h2h-val">{sr["PtsPerRace"]:.1f}</div></div>
                          </div>
                        </div>
                        """)

                # Progression overlay for selected drivers
                st.markdown(f"#### {tr(lang, 'h2h_progression_title')}")
                wide, long = cumulative_points_wide(latest_gp, entity_col="Driver", all_time=False)
                if not wide.empty and not long.empty and PLOTLY_OK:
                    long_h2h = long[long["Driver"].isin(sel_drivers)].copy()
                    order_x  = long_h2h.sort_values("EventIdx")[["EventIdx","EventLabel"]].drop_duplicates().sort_values("EventIdx")["EventLabel"].tolist()
                    fig_h2h  = px.line(
                        long_h2h, x="EventLabel", y="CumPoints", color="Driver",
                        markers=True,
                        category_orders={"EventLabel": order_x, "Driver": sel_drivers},
                        color_discrete_sequence=["#E10600","#58a6ff","#f5c518"],
                        template=THEME_CFG["plotly_template"],
                    )
                    fig_h2h.update_layout(height=360, margin=dict(l=10,r=10,t=10,b=40), legend_title_text="")
                    fig_h2h.update_xaxes(type="category", title="GP")
                    st.plotly_chart(fig_h2h, use_container_width=True)

    # ── A2: Championship Maths ──────────────────────────────────────────
    elif analysis_section == tr(lang, "h2h_sec_champ"):
        st.subheader(tr(lang, "champ_maths_title"))
        if st_tbl_latest.empty or len(st_tbl_latest) < 2:
            st.info(tr(lang, "not_enough"))
        else:
            # Use calendar to count remaining races
            cal_league = calendar_raw[calendar_raw["League Name"] == latest_meta["League Name"]].copy() if not calendar_raw.empty else pd.DataFrame()
            total_races = int(cal_league["Round"].nunique()) if not cal_league.empty and "Round" in cal_league.columns else None
            rounds_done = int(latest_gp["Round"].nunique()) if not latest_gp.empty else 0

            # Max points per race (from the points mode config)
            pts_agg = latest_gp.groupby(["Round", "Driver"])["Points"].sum()
            max_pts_per_race = float(pts_agg.max()) if not pts_agg.empty else 25.0

            if total_races and total_races > rounds_done:
                races_left = total_races - rounds_done
            else:
                races_left = None

            p1_pts = int(st_tbl_latest.iloc[0]["Points"])
            p1_name = str(st_tbl_latest.iloc[0]["Driver"])
            p2_pts = int(st_tbl_latest.iloc[1]["Points"])
            p2_name = str(st_tbl_latest.iloc[1]["Driver"])
            gap = p1_pts - p2_pts

            max_available = int(races_left * max_pts_per_race) if races_left else None
            is_decided = (max_available is not None) and (p2_pts + max_available < p1_pts)

            card_cls = "maths-card " + ("maths-closed" if is_decided else "maths-open")
            verdict  = tr(lang, "champ_maths_closed") if is_decided else tr(lang, "champ_maths_open")
            details  = ""
            if races_left is not None:
                details += f"<br><b>{tr(lang,'champ_maths_races_left')}:</b> {races_left}"
            if max_available is not None:
                details += f"<br><b>{tr(lang,'champ_maths_pts_left')}:</b> {max_available}"
            if not is_decided and races_left:
                wins_needed = int(np.ceil(gap / max_pts_per_race)) if max_pts_per_race else "?"
                details += f"<br><b>{tr(lang,'champ_maths_needed')}:</b> {wins_needed}"

            st.html(f"""
            <div class="{card_cls}">
              <b style="font-size:1.1rem">{verdict}</b>
              <br>
              <span style="color:#aaa">{p1_name} {tr(lang,"champ_leads")} {p2_name} by <b style="color:#E10600">{gap} {tr(lang,"champ_pts_gap_label")}</b></span>
              {details}
            </div>
            """)

            # Visualise the gap trajectory
            _, tension_df2, _ = championship_tension(latest_gp, entity_col="Driver")
            if not tension_df2.empty and PLOTLY_OK:
                tdf2 = tension_df2.copy()
                tdf2["EventLabel"] = "R" + tdf2["EventIdx"].astype(int).astype(str)
                fig_m = go.Figure()
                fig_m.add_trace(go.Scatter(
                    x=tdf2["EventLabel"], y=tdf2["GapP1P2"],
                    mode="lines+markers", name=tr(lang, "champ_p1p2_gap"),
                    fill="tozeroy", fillcolor="rgba(225,6,0,0.08)",
                    line={"color": "#E10600", "width": 2},
                ))
                if max_available is not None and not is_decided:
                    last_lbl = tdf2["EventLabel"].iloc[-1]
                    fig_m.add_hline(y=max_available, line_dash="dot", line_color="#58a6ff",
                                    annotation_text=tr(lang, "champ_max_pts_annotation"), annotation_position="top right")
                fig_m.update_layout(template=THEME_CFG["plotly_template"], height=320,
                                    margin=dict(l=10,r=10,t=10,b=10),
                                    xaxis_title=tr(lang,"champ_round_label"), yaxis_title=tr(lang,"champ_pts_gap_label"))
                st.plotly_chart(fig_m, use_container_width=True)

    # ── A3: Teammate Battle ─────────────────────────────────────────────
    elif analysis_section == tr(lang, "h2h_sec_teammate"):
        st.subheader(tr(lang, "teammate_title"))
        if latest_gp.empty or "Team" not in latest_gp.columns:
            st.info(tr(lang, "not_enough"))
        else:
            duel_rows = []
            for team, tdf in latest_gp.groupby("Team"):
                drivers_in_team = tdf["Driver"].dropna().unique().tolist()
                if len(drivers_in_team) < 2:
                    continue
                for d in drivers_in_team:
                    row = st_tbl_latest[st_tbl_latest["Driver"] == d]
                    if row.empty:
                        continue
                    r = row.iloc[0]
                    duel_rows.append({
                        "Team": team,
                        "Driver": d,
                        "Pos": int(r.get("Pos", 99)),
                        "Points": int(r.get("Points", 0)),
                        "Wins": int(r.get("Wins", 0)),
                        "AvgFinish": float(r.get("AvgFinish", 99)),
                    })

            if not duel_rows:
                st.info(tr(lang, "not_enough"))
            else:
                duel_df = pd.DataFrame(duel_rows)
                # For each team pick the two with most points and label winner
                summary = []
                for team, g in duel_df.groupby("Team"):
                    g2 = g.sort_values("Points", ascending=False)
                    if len(g2) >= 2:
                        winner = g2.iloc[0]["Driver"]
                        pts_delta = int(g2.iloc[0]["Points"] - g2.iloc[1]["Points"])
                        summary.append({"Team": team, tr(lang,"teammate_ahead"): winner, tr(lang,"teammate_pts_adv"): pts_delta,
                                        "Drivers": " vs ".join(g2.head(2)["Driver"].tolist())})
                if summary:
                    sm_df = pd.DataFrame(summary)
                    st.dataframe(sm_df, use_container_width=True, hide_index=True)

                # Bar chart: per-team points side by side  
                if PLOTLY_OK:
                    # Only teams with 2+ drivers
                    teams_with_2 = duel_df.groupby("Team").filter(lambda x: len(x) >= 2)["Team"].unique()
                    plot_duel = duel_df[duel_df["Team"].isin(teams_with_2)].copy()
                    if not plot_duel.empty:
                        fig_duel = px.bar(
                            plot_duel.sort_values(["Team","Points"], ascending=[True,False]),
                            x="Points", y="Driver", color="Team",
                            orientation="h",
                            color_discrete_sequence=THEME_CFG["line_palette"],
                            template=THEME_CFG["plotly_template"],
                        )
                        fig_duel.update_layout(height=max(300, len(plot_duel)*28),
                                               margin=dict(l=10,r=40,t=10,b=10), showlegend=True)
                        st.plotly_chart(fig_duel, use_container_width=True)

    # ── A4: Performance Radar ───────────────────────────────────────────
    elif analysis_section == tr(lang, "h2h_sec_radar"):
        st.subheader(tr(lang, "radar_title"))
        if st_tbl_latest.empty:
            st.info(tr(lang, "not_enough"))
        elif not PLOTLY_OK:
            st.info("Plotly required for radar chart.")
        else:
            sel_radar = st.multiselect(
                tr(lang, "radar_driver"),
                all_drivers,
                default=all_drivers[:min(3, len(all_drivers))],
                max_selections=3,
                key="radar_drivers",
            )
            categories = ["Points", "Wins", "Podiums", "Avg Finish (inv)", "Pts/Race"]
            fig_radar = go.Figure()
            RADAR_COLORS = ["#E10600", "#58a6ff", "#f5c518"]
            for ci, drv in enumerate(sel_radar):
                row = st_tbl_latest[st_tbl_latest["Driver"] == drv]
                if row.empty:
                    continue
                r = row.iloc[0]
                max_pts      = st_tbl_latest["Points"].max() or 1
                max_wins     = st_tbl_latest["Wins"].max() or 1
                max_podiums  = st_tbl_latest["Podiums"].max() or 1
                max_ptsrace  = st_tbl_latest["Pts/Race"].max() or 1
                avg_inv_max  = st_tbl_latest["AvgFinish"].max() or 1  # lower is better → invert
                vals = [
                    float(r.get("Points",0)) / max_pts * 100,
                    float(r.get("Wins",0)) / max_wins * 100,
                    float(r.get("Podiums",0)) / max_podiums * 100,
                    (avg_inv_max - float(r.get("AvgFinish",avg_inv_max))) / avg_inv_max * 100,
                    float(r.get("Pts/Race",0)) / max_ptsrace * 100,
                ]
                fig_radar.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor=RADAR_COLORS[ci % 3].replace("#", "rgba(").replace(")", ",0.15)") if False else "rgba(0,0,0,0)",
                    line={"color": RADAR_COLORS[ci % 3], "width": 2},
                    name=drv,
                    opacity=0.85,
                ))
            fig_radar.update_layout(
                polar=dict(
                    bgcolor="#10151f",
                    radialaxis=dict(visible=True, range=[0,100], gridcolor="#21262d", tickcolor="#555"),
                    angularaxis=dict(gridcolor="#21262d", linecolor="#333"),
                ),
                template=THEME_CFG["plotly_template"],
                height=480, margin=dict(l=60,r=60,t=40,b=40),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            st.caption(tr(lang, "radar_axes_caption"))

    # ── A5: Season-over-Season ──────────────────────────────────────────
    elif analysis_section == tr(lang, "h2h_sec_sos"):
        st.subheader(tr(lang, "sos_title"))
        if base_all.empty:
            st.info(tr(lang, "not_enough"))
        else:
            seasons_avail = sorted(base_all["SeasonLabel"].dropna().unique().tolist(), key=_season_sort_key)
            if len(seasons_avail) < 2:
                st.info(tr(lang, "sos_need_2_seasons"))
            else:
                c_a, c_b = st.columns(2)
                with c_a:
                    sos_a = st.selectbox(tr(lang,"sos_season_a"), seasons_avail, index=len(seasons_avail)-2, key="sos_a")
                with c_b:
                    sos_b = st.selectbox(tr(lang,"sos_season_b"), seasons_avail, index=len(seasons_avail)-1, key="sos_b")

                sos_entity = st.radio(tr(lang, "sos_track"), [tr(lang,"drivers"), tr(lang,"constructors")], horizontal=True, key="sos_entity")
                sos_col = "Driver" if sos_entity == tr(lang,"drivers") else "Team"
                top_n_sos = st.slider("Top N", 3, 10, 5, key="sos_topn")

                def _sos_curve(season_label, entity_col, top_n):
                    sub = base_all[(base_all["SeasonLabel"] == season_label) & (~base_all["IsSeasonFinal"])].copy()
                    if sub.empty:
                        return pd.DataFrame()
                    sub = event_sort_cols(sub, all_time=False)
                    sub = sub.sort_values(["EventIdx", entity_col])
                    top_ents = sub.groupby(entity_col)["Points"].sum().nlargest(top_n).index.tolist()
                    sub = sub[sub[entity_col].isin(top_ents)]
                    sub["CumPts"] = sub.groupby(entity_col)["Points"].cumsum()
                    sub["RaceN"] = sub.groupby(entity_col).cumcount() + 1
                    return sub

                df_a = _sos_curve(sos_a, sos_col, top_n_sos)
                df_b = _sos_curve(sos_b, sos_col, top_n_sos)

                if df_a.empty and df_b.empty:
                    st.info(tr(lang, "not_enough"))
                elif PLOTLY_OK:
                    fig_sos = go.Figure()
                    for ent in df_a[sos_col].unique() if not df_a.empty else []:
                        sub = df_a[df_a[sos_col] == ent]
                        fig_sos.add_trace(go.Scatter(
                            x=sub["RaceN"], y=sub["CumPts"],
                            mode="lines+markers", name=f"{ent} ({sos_a})",
                            line={"width": 2, "dash": "solid"},
                        ))
                    for ent in df_b[sos_col].unique() if not df_b.empty else []:
                        sub = df_b[df_b[sos_col] == ent]
                        fig_sos.add_trace(go.Scatter(
                            x=sub["RaceN"], y=sub["CumPts"],
                            mode="lines+markers", name=f"{ent} ({sos_b})",
                            line={"width": 2, "dash": "dash"},
                        ))
                    fig_sos.update_layout(
                        template=THEME_CFG["plotly_template"],
                        height=480, margin=dict(l=10,r=10,t=10,b=40),
                        xaxis_title=tr(lang,"sos_race_x"), yaxis_title=tr(lang,"sos_cum_pts_y"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                    )
                    st.plotly_chart(fig_sos, use_container_width=True)
                    st.caption(tr(lang, "sos_solid"))



st.caption(tr(lang, "version"))