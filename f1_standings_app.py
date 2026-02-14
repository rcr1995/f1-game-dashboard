import streamlit as st
import pandas as pd
import numpy as np
import json
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
        "tabs": ["🏁 Dashboard", "📋 Matrix & Form", "🧮 Simulator", "🏆 All‑time", "⚙️ Settings"],
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
        "sim_title": "Points simulator (what‑if standings)",
        "sim_for": "Simulate for",
        "scenario": "Scenario",
        "scoring": "Scoring",
        "scenario_json": "Scenario points JSON",
        "last_round_mult": "Last round multiplier",
        "results_vs_current": "Results vs current",
        "sim_help": "Recalculates standings under a scenario (alternative scoring and/or last-race multiplier) and compares with current standings.",
        "all_time_title": "All‑time overview (ignores Season filter)",
        "all_time_standings": "All‑time standings",
        "titles_count": "Titles count",
        "champions_list": "Season champions list",
        "champions_timeline": "Champions timeline",
        "all_time_progression": "All‑time progression (cumulative points across seasons)",
        "notes": "Notes",
        "notes_body": "- Sidebar is collapsible (top-left arrow).\n- Drag & drop: yes — just drop your base Excel in the uploader.\n- Filters are on top (Game → Season → League).\n- Tabs keep things uncluttered.",
        "safe_delete": "Files you can safely delete",
        "version": "F1 Game Dashboard • v7",
        "language": "Language",
        "no_rows": "No rows match the current filters.",
        "not_enough": "Not enough data for this view.",
        "download": "Download CSV",
        "share_title": "How your brother can access this app",
        "share_body": "For Streamlit Cloud: just share your app URL. For private access: use Tailscale (see below).",
    },
    "pt": {
        "title": "Dashboard F1",
        "data": "Dados",
        "upload": "Carregar Excel (.xlsx)",
        "upload_help": "Arraste e largue aqui o ficheiro Excel base.",
        "using_bundled": "A usar um ficheiro Excel incluído no repositório.",
        "no_bundled": "Não foi encontrado nenhum Excel no repositório. Carregue o Excel na barra lateral.",
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
        "tabs": ["🏁 Dashboard", "📋 Matriz & Forma", "🧮 Simulador", "🏆 Histórico", "⚙️ Definições"],
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
        "sim_title": "Simulador de pontos (cenários)",
        "sim_for": "Simular para",
        "scenario": "Cenário",
        "scoring": "Pontuação",
        "scenario_json": "JSON de pontuação do cenário",
        "last_round_mult": "Multiplicador da última ronda",
        "results_vs_current": "Resultados vs atual",
        "sim_help": "Recalcula a classificação num cenário (pontuação alternativa e/ou multiplicador na última corrida) e compara com a atual.",
        "all_time_title": "Histórico (ignora filtro de Época)",
        "all_time_standings": "Classificação histórica",
        "titles_count": "Títulos",
        "champions_list": "Lista de campeões por época",
        "champions_timeline": "Linha temporal de campeões",
        "all_time_progression": "Progressão histórica (pontos acumulados)",
        "notes": "Notas",
        "notes_body": "- A barra lateral é recolhível (seta no canto superior esquerdo).\n- Arrastar e largar: sim — basta colocar o Excel base no carregador.\n- Filtros no topo (Jogo → Época → Liga).\n- Separado por separadores para não ficar carregado.",
        "safe_delete": "Ficheiros que pode apagar",
        "version": "Dashboard F1 • v7",
        "language": "Idioma",
        "no_rows": "Sem dados para os filtros atuais.",
        "not_enough": "Dados insuficientes para esta vista.",
        "download": "Download CSV",
        "share_title": "Como o teu irmão pode aceder à app",
        "share_body": "No Streamlit Cloud: basta partilhar o link. Para privado: use Tailscale (ver abaixo).",
    },
}

def tr(lang: str, key: str):
    return T[lang].get(key, key)

@st.cache_data(show_spinner=False)
def load_data_from_excel(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name=0)  # requires openpyxl
    df.columns = [c.strip() for c in df.columns]
    required = {"Game","Season","League Name","Round","GP Name","Driver","Team","Finish Pos","Points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in Excel: {sorted(missing)}")

    df["Season"] = pd.to_numeric(df["Season"], errors="coerce").astype("Int64")
    df["Round"] = pd.to_numeric(df["Round"], errors="coerce").astype("Int64")
    df["Finish Pos"] = pd.to_numeric(df["Finish Pos"], errors="coerce").astype("Int64")
    df["Points"] = pd.to_numeric(df["Points"], errors="coerce").fillna(0.0)

    for c in ["Game","League Name","GP Name","Driver","Team"]:
        df[c] = df[c].astype(str).str.strip()

    df = df.dropna(subset=["Season","Round"])
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

def standings_table(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    col = "Driver" if entity == "Drivers" else "Team"
    g = df.groupby(col, as_index=False).agg(
        Points=("Points","sum"),
        Races=("GP Name","nunique"),
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

def event_sort_cols(df: pd.DataFrame, all_time: bool) -> pd.DataFrame:
    d = df.copy()
    if all_time:
        d["EventIdx"] = d["Season"].astype(int) * 1000 + d["Round"].astype(int)
        d["EventLabel"] = d["Season"].astype(str) + " R" + d["Round"].astype(str) + " • " + d["GP Name"]
    else:
        d["EventIdx"] = d["Round"].astype(int)
        d["EventLabel"] = "R" + d["Round"].astype(str) + " • " + d["GP Name"]
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
    if df.empty:
        return pd.DataFrame(), ""
    last_round = int(df["Round"].max())
    gp_mode = df.loc[df["Round"] == last_round, "GP Name"].mode()
    gp = gp_mode.iloc[0] if len(gp_mode) else ""
    d = df[(df["Round"] == last_round) & (df["GP Name"] == gp)].copy()
    if entity == "Drivers":
        t = d.groupby(["Driver","Team"], as_index=False).agg(
            FinishPos=("Finish Pos","min"),
            Points=("Points","sum"),
        ).sort_values(["FinishPos","Driver"], ascending=[True,True])
        t.insert(0, "Pos", range(1, len(t)+1))
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
    d = df.groupby(["Season", entity_col], as_index=False)["Points"].sum()
    d = d.sort_values(["Season","Points"], ascending=[True,False])
    champs = d.groupby("Season").head(1).rename(columns={entity_col:"Champion"})
    return champs[["Season","Champion","Points"]].sort_values("Season")

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
        return "color: #2ecc71; font-weight: 700;"
    if v < 0:
        return "color: #ff4b4b; font-weight: 700;"
    return "color: #b0b0b0;"

def style_by_columns(df: pd.DataFrame, cols):
    sty = df.style
    for c in cols:
        if c in df.columns:
            sty = sty.map(_color_pos_change, subset=[c])
    return sty

def download_csv_button(df: pd.DataFrame, filename: str, label: str):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")

top_a, _ = st.columns([1, 5])
with top_a:
    lang_name = st.selectbox(T["en"]["language"], list(LANGS.keys()), index=0)
lang = LANGS[lang_name]
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

f1, f2, f3 = st.columns([1,1,1])
with f1:
    games = ["All"] + sorted(raw["Game"].dropna().unique().tolist())
    game = st.selectbox(tr(lang, "game"), games, index=0)
with f2:
    seasons = ["All"] + sorted(raw["Season"].dropna().astype(int).unique().tolist())
    season = st.selectbox(tr(lang, "season"), seasons, index=0)
with f3:
    leagues = ["All"] + sorted(raw["League Name"].dropna().unique().tolist())
    league = st.selectbox(tr(lang, "league"), leagues, index=0)

df = raw.copy()
if game != "All":
    df = df[df["Game"] == game]
if season != "All":
    df = df[df["Season"].astype(int) == int(season)]
if league != "All":
    df = df[df["League Name"] == league]

df = apply_points_override(df, mode=canonical_points_mode, custom_map=custom_map, last_round_multiplier=1.0)

tab_dash, tab_matrix, tab_sim, tab_all, tab_settings = st.tabs(tr(lang, "tabs"))

with tab_dash:
    if df.empty:
        st.info(tr(lang, "no_rows"))
    else:
        view = st.radio(tr(lang, "standings_type"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="dash_view")
        view_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[view]
        entity_col = "Driver" if view_canon == "Drivers" else "Team"
        st.markdown(f"### {tr(lang, 'overview')}")
        st.caption(f"{game if game!='All' else 'All'} • {league if league!='All' else 'All'} • {season if season!='All' else 'All'}")
        st_table = standings_table(df, entity=view_canon)
        leader = st_table.iloc[0][entity_col] if not st_table.empty else "-"
        lead_pts = float(st_table.iloc[0]["Points"]) if not st_table.empty else 0.0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(tr(lang, "leader"), str(leader))
        c2.metric(tr(lang, "leader_points"), f"{lead_pts:.0f}")
        c3.metric(tr(lang, "races"), f"{int(df['GP Name'].nunique())}")
        c4.metric(tr(lang, "grid_size"), f"{int(df[entity_col].nunique())}")
        left, right = st.columns([1.05, 1.45], gap="large")
        with left:
            st.subheader(tr(lang, "standings"))
            show_form_cols = st.toggle(tr(lang, "show_form_cols"), value=True)
            if show_form_cols:
                form = form_table(df, entity_col=entity_col)
                st_table2 = st_table.merge(form, on=entity_col, how="left") if not form.empty else st_table
            else:
                st_table2 = st_table
            st.dataframe(st_table2, use_container_width=True, hide_index=True)
            download_csv_button(st_table2, "standings.csv", tr(lang, "download"))
            st.caption(tr(lang, "tiebreak"))
            st.markdown("---")
            st.subheader(tr(lang, "last_gp_results"))
            last_tbl, last_label = last_gp_table(df, entity=view_canon)
            if last_tbl.empty:
                st.caption(tr(lang, "not_enough"))
            else:
                st.caption(last_label)
                st.dataframe(last_tbl, use_container_width=True, hide_index=True)
                download_csv_button(last_tbl, "last_gp_results.csv", tr(lang, "download"))
        with right:
            st.subheader(tr(lang, "progression"))
            top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="dash_topn")
            wide, _ = cumulative_points_wide(df, entity_col=entity_col, all_time=False)
            if wide.empty:
                st.info(tr(lang, "not_enough"))
            else:
                final = wide.tail(1).T.sort_values(by=wide.index.max(), ascending=False)
                keep = final.head(top_n).index.tolist()
                wide_plot = wide[keep].ffill().fillna(0)
                if PLOTLY_OK:
                    melt = wide_plot.reset_index().melt(id_vars=["EventIdx"], var_name=entity_col, value_name="CumPoints")
                    fig = px.line(melt, x="EventIdx", y="CumPoints", color=entity_col, markers=True)
                    fig.update_layout(height=360, margin=dict(l=10,r=10,t=10,b=10), legend_title_text="")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.line_chart(wide_plot, height=360)
            st.subheader(tr(lang, "biggest_movers"))
            rr = per_round_positions(df, entity_col=entity_col)
            if rr.empty:
                st.info(tr(lang, "not_enough"))
            else:
                last_round = rr["EventIdx"].max()
                last = rr[rr["EventIdx"] == last_round].copy()
                last["PosChange"] = last["PosChange"].fillna(0).astype(int)
                gainers = last.sort_values("PosChange", ascending=False).head(5)[[entity_col,"Position","PosChange","CumPoints"]]
                losers = last.sort_values("PosChange", ascending=True).head(5)[[entity_col,"Position","PosChange","CumPoints"]]
                gcol, lcol = st.columns(2)
                with gcol:
                    st.markdown(f"**{tr(lang, 'top_gainers')}**")
                    st.dataframe(style_by_columns(gainers, ["PosChange"]), use_container_width=True, hide_index=True)
                    download_csv_button(gainers, "top_gainers.csv", tr(lang, "download"))
                with lcol:
                    st.markdown(f"**{tr(lang, 'top_losers')}**")
                    st.dataframe(style_by_columns(losers, ["PosChange"]), use_container_width=True, hide_index=True)
                    download_csv_button(losers, "top_losers.csv", tr(lang, "download"))
                st.subheader(tr(lang, "leader_tracker"))
                leaders = rr.sort_values(["EventIdx","Position"]).groupby("EventIdx").head(1).sort_values("EventIdx")
                second = rr.sort_values(["EventIdx","Position"]).groupby("EventIdx").nth(1).reset_index()
                leaders = leaders.merge(second[["EventIdx","CumPoints"]].rename(columns={"CumPoints":"SecondPoints"}), on="EventIdx", how="left")
                leaders["LeadMargin"] = (leaders["CumPoints"] - leaders["SecondPoints"]).fillna(leaders["CumPoints"])
                swaps = lead_swaps_count(leaders[entity_col].astype(str))
                a, b, c, d = st.columns(4)
                a.metric(tr(lang, "leader"), str(leaders.iloc[-1][entity_col]))
                b.metric(tr(lang, "round"), f"{int(leaders.iloc[-1]['EventIdx'])}")
                c.metric(tr(lang, "lead_margin"), f"{float(leaders.iloc[-1]['LeadMargin']):.0f} pts")
                d.metric(tr(lang, "lead_swaps"), f"{swaps}")
                if PLOTLY_OK:
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(
                        x=leaders["EventIdx"],
                        y=leaders["LeadMargin"],
                        mode="lines+markers",
                        customdata=np.stack([leaders[entity_col].astype(str)], axis=-1),
                        hovertemplate="Round %{x}<br>Leader %{customdata[0]}<br>Lead margin %{y:.0f} pts<extra></extra>"
                    ))
                    fig2.update_layout(height=320, margin=dict(l=10,r=10,t=10,b=10), xaxis_title=None, yaxis_title=None)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.line_chart(leaders.set_index("EventIdx")[["LeadMargin"]], height=320)

with tab_matrix:
    if df.empty:
        st.info(tr(lang, "no_rows"))
    else:
        kind = st.radio(tr(lang, "matrix_for"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="mat_kind")
        kind_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[kind]
        entity_col = "Driver" if kind_canon == "Drivers" else "Team"
        st.subheader(tr(lang, "pos_matrix"))
        mat = position_matrix(df, entity_col=entity_col)
        if mat.empty:
            st.info(tr(lang, "not_enough"))
        else:
            st.dataframe(mat, use_container_width=True)
            download_csv_button(mat.reset_index(), "position_matrix.csv", tr(lang, "download"))
        st.subheader(tr(lang, "form_table"))
        st.caption(tr(lang, "form_help"))
        form = form_table(df, entity_col=entity_col)
        if form.empty:
            st.info(tr(lang, "not_enough"))
        else:
            col_cfg = {
                entity_col: st.column_config.TextColumn(entity_col),
                "Pts L3": st.column_config.NumberColumn("Pts L3", help="Total points in the last 3 rounds", format="%.0f"),
                "AvgFin L3": st.column_config.NumberColumn("AvgFin L3", help="Average finish position in the last 3 rounds (lower is better)", format="%.1f"),
                "Pts L5": st.column_config.NumberColumn("Pts L5", help="Total points in the last 5 rounds", format="%.0f"),
                "AvgFin L5": st.column_config.NumberColumn("AvgFin L5", help="Average finish position in the last 5 rounds (lower is better)", format="%.1f"),
                "Position": st.column_config.NumberColumn("Position", help="Current championship position after the latest round"),
                "PosChange": st.column_config.NumberColumn("PosChange", help="Positions gained (+) or lost (-) vs previous round"),
            }
            st.data_editor(form, use_container_width=True, hide_index=True, disabled=True, column_config=col_cfg)
            st.caption("Color hint: green = improved, red = worse.")
            st.dataframe(style_by_columns(form, ["PosChange"]), use_container_width=True, hide_index=True)
            download_csv_button(form, "form_table.csv", tr(lang, "download"))

with tab_sim:
    if df.empty:
        st.info(tr(lang, "no_rows"))
    else:
        st.subheader(tr(lang, "sim_title"))
        st.caption(tr(lang, "sim_help"))
        kind = st.radio(tr(lang, "sim_for"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="sim_kind")
        kind_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[kind]
        entity_col = "Driver" if kind_canon == "Drivers" else "Team"
        sim1, sim2 = st.columns([1.1, 1.3], gap="large")
        with sim1:
            st.markdown(f"### {tr(lang, 'scenario')}")
            sim_mode_label = st.selectbox(tr(lang, "scoring"), [tr(lang, "use_excel"), tr(lang, "f1_default"), tr(lang, "custom_mapping")], index=0, key="sim_points_mode")
            sim_mode = {tr(lang, "use_excel"): "Use points from Excel", tr(lang, "f1_default"): "F1 default (25-18-...)", tr(lang, "custom_mapping"): "Custom mapping"}[sim_mode_label]
            sim_map = {}
            if sim_mode == "Custom mapping":
                st.caption(tr(lang, "custom_caption"))
                txt = st.text_area(tr(lang, "scenario_json"), value=json.dumps(DEFAULT_POINTS, indent=2), key="sim_json")
                try:
                    m = json.loads(txt) if txt.strip() else {}
                    sim_map = {int(k): float(v) for k, v in m.items()}
                    st.success("OK")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")
                    sim_map = {}
            last_mult = st.slider(tr(lang, "last_round_mult"), 1.0, 3.0, 1.0, 0.25)
        with sim2:
            st.markdown(f"### {tr(lang, 'results_vs_current')}")
            base = apply_points_override(df, mode=canonical_points_mode, custom_map=custom_map, last_round_multiplier=1.0)
            scen = apply_points_override(df, mode=sim_mode, custom_map=sim_map, last_round_multiplier=last_mult)
            base_st = standings_table(base, entity=kind_canon)
            scen_st = standings_table(scen, entity=kind_canon)
            comp = base_st[[entity_col,"Points","Pos"]].merge(scen_st[[entity_col,"Points","Pos"]].rename(columns={"Points":"ScenarioPoints","Pos":"ScenarioPos"}), on=entity_col, how="outer").fillna({"Points":0,"ScenarioPoints":0})
            comp["Δ Points"] = (comp["ScenarioPoints"] - comp["Points"]).round(1)
            comp["Δ Pos"] = (comp["Pos"] - comp["ScenarioPos"]).astype("Int64")
            comp = comp.sort_values(["ScenarioPoints", "ScenarioPos", entity_col], ascending=[False, True, True])
            comp.insert(0, "ScenarioRank", range(1, len(comp)+1))
            col_cfg = {
                entity_col: st.column_config.TextColumn(entity_col),
                "Points": st.column_config.NumberColumn("Points", help="Current total points"),
                "Pos": st.column_config.NumberColumn("Pos", help="Current championship position"),
                "ScenarioPoints": st.column_config.NumberColumn("ScenarioPoints", help="Total points under the scenario"),
                "ScenarioPos": st.column_config.NumberColumn("ScenarioPos", help="Championship position under the scenario"),
                "Δ Points": st.column_config.NumberColumn("Δ Points", help="ScenarioPoints - Points"),
                "Δ Pos": st.column_config.NumberColumn("Δ Pos", help="Positions gained (+) or lost (-) under the scenario"),
            }
            st.data_editor(comp, use_container_width=True, hide_index=True, disabled=True, column_config=col_cfg)
            st.caption("Color hint: green = improvement, red = worse.")
            st.dataframe(style_by_columns(comp, ["Δ Pos", "Δ Points"]), use_container_width=True, hide_index=True)
            download_csv_button(comp, "simulator_results.csv", tr(lang, "download"))

with tab_all:
    if raw.empty:
        st.info("No data loaded.")
    else:
        st.subheader(tr(lang, "all_time_title"))
        base = raw.copy()
        if game != "All":
            base = base[base["Game"] == game]
        if league != "All":
            base = base[base["League Name"] == league]
        base = apply_points_override(base, mode=canonical_points_mode, custom_map=custom_map, last_round_multiplier=1.0)
        at_view = st.radio(tr(lang, "all_time_standings"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="at_view")
        at_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[at_view]
        entity_col = "Driver" if at_canon == "Drivers" else "Team"
        c1, c2 = st.columns([1.1, 1.4], gap="large")
        with c1:
            st.markdown(f"### {tr(lang, 'all_time_standings')}")
            at_tbl = standings_table(base, entity=at_canon)
            st.dataframe(at_tbl, use_container_width=True, hide_index=True)
            download_csv_button(at_tbl, "all_time_standings.csv", tr(lang, "download"))
            st.markdown(f"### {tr(lang, 'titles_count')}")
            titles, champs = titles_count(base, entity_col=entity_col)
            st.dataframe(titles, use_container_width=True, hide_index=True)
            download_csv_button(titles, "titles_count.csv", tr(lang, "download"))
            with st.expander(tr(lang, "champions_list")):
                st.dataframe(champs, use_container_width=True, hide_index=True)
                download_csv_button(champs, "season_champions.csv", tr(lang, "download"))
        with c2:
            st.markdown(f"### {tr(lang, 'champions_timeline')}")
            _, champs = titles_count(base, entity_col=entity_col)
            if PLOTLY_OK and not champs.empty:
                fig = px.scatter(champs, x="Season", y="Champion", size="Points", hover_data=["Points"])
                fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(champs, use_container_width=True, hide_index=True)
            st.markdown(f"### {tr(lang, 'all_time_progression')}")
            top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="at_topn")
            wide, _ = cumulative_points_wide(base, entity_col=entity_col, all_time=True)
            if wide.empty:
                st.info(tr(lang, "not_enough"))
            else:
                final = wide.tail(1).T.sort_values(by=wide.index.max(), ascending=False)
                keep = final.head(top_n).index.tolist()
                wide_plot = wide[keep].ffill().fillna(0)
                if PLOTLY_OK:
                    melt = wide_plot.reset_index().melt(id_vars=["EventIdx"], var_name=entity_col, value_name="CumPoints")
                    fig2 = px.line(melt, x="EventIdx", y="CumPoints", color=entity_col)
                    fig2.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10), legend_title_text="")
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.line_chart(wide_plot, height=280)

with tab_settings:
    st.subheader(tr(lang, "notes"))
    st.markdown(tr(lang, "notes_body"))
    st.markdown(f"### {tr(lang, 'share_title')}")
    st.markdown(tr(lang, 'share_body'))
    st.markdown(
        \"\"\"
**Streamlit Cloud (Option 2)**
- After deployment, your brothers just open the URL of your app.

**Important for Streamlit Cloud**
- Make sure your repo has:
  - `requirements.txt` (not `requirements_v6.txt`)
  - `runtime.txt` with `python-3.11`

**Private sharing: Tailscale**
1) Install Tailscale on your PC and on your brothers' PCs.
2) Log in with the same account (or invite them).
3) Run:
   - `python -m streamlit run f1_standings_app_v7.py --server.address 0.0.0.0 --server.port 8501`
4) Share:
   - `http://YOUR_TAILSCALE_IP:8501`
\"\"\"
    )
    st.markdown(f"### {tr(lang, 'safe_delete')}")
    st.write([
        "f1_standings_app_v6.py", "requirements_v6.txt",
        "f1_standings_app_v5.py", "requirements_v5.txt",
        "f1_standings_app_v4.py", "requirements_v4.txt",
    ])
st.caption(tr(lang, "version"))
