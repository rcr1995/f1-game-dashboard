import pandas as pd
import numpy as np
import base64
import re
from pathlib import Path
from functools import lru_cache
_T = {
    "en": {
        "days": "DAYS",
        "hours": "HOURS",
        "minutes": "MINUTES",
        "seconds": "SECONDS",
        "until_resumes": "UNTIL {next_race_name} RESUMES",
        "circuits": "CIRCUITS 🛣️",
        "gp_stats": "GP STATISTICS 🏁",
        "our_league": "Our PS5 F1 league.<br>One competition.<br>No mercy.",
        "season_label": "SEASON",
        "drivers_championship_standings": "🏆 DRIVERS CHAMPIONSHIP STANDINGS",
        "pos": "POS",
        "driver": "DRIVER",
        "points": "PTS",
        "wins": "WINS",
        "gap": "GAP",
        "full_standings": "FULL STANDINGS",
        "hide_standings": "HIDE STANDINGS",
        "latest_race": "🏁 LATEST RACE",
        "grand_prix": "GRAND PRIX",
        "time": "TIME",
        "fastest_lap": "FASTEST LAP",
        "full_results": "FULL RESULTS",
        "hide_results": "HIDE RESULTS",
        "next_race": "📅 NEXT RACE",
        "date": "DATE",
        "race_length": "RACE LENGTH",
        "weather": "WEATHER",
        "assists": "ASSISTS",
        "sunny_dry": "Sunny (Dry)",
        "league_rules": "League Rules",
        "constructors_standings": "🏎️ CONSTRUCTORS STANDINGS",
        "team": "TEAM",
        "teammate_battle": "⚔️ TEAMMATE BATTLE",
        "full_list": "FULL LIST",
        "hide_list": "HIDE LIST",
        "league_statistics": "📊 LEAGUE STATISTICS",
        "most_wins": "MOST WINS",
        "most_podiums": "MOST PODIUMS",
        "best_avg_finish": "BEST AVG FINISH",
        "season_calendar": "📅 SEASON CALENDAR",
        "rnd": "RND",
        "track": "TRACK",
        "winner": "WINNER",
        "status": "STATUS",
        "completed": "Completed",
        "upcoming": "Upcoming",
        "full_calendar": "FULL CALENDAR",
        "hide_calendar": "HIDE CALENDAR",
        "driver_lineup": "🏎️ DRIVER LINEUP",
        "all_drivers": "ALL DRIVERS",
        "hide_drivers": "HIDE DRIVERS",
        "hall_of_fame": "🏆 HALL OF FAME",
        "most_championships": "MOST CHAMPIONSHIPS",
        "most_dominant_season": "MOST DOMINANT SEASON",
        "all_time_wins": "ALL-TIME WINS",
        "all_time_podiums": "ALL-TIME PODIUMS",
        "titles_plural": "Titles",
        "title_singular": "Title",
        "wins_plural": "Wins",
        "podiums_plural": "Podiums",
        "pts_gap_suffix": " Pts Gap",
        "drivers_title": "Drivers Title",
        "constructors_title": "Constructors Title",
        "decided": "DECIDED",
        "is_still_open": "IS STILL OPEN",
        "leads": "leads",
        "by": "by",
        "pts": "pts",
        "finish_line": "Finish Line",
        "points_still_open": "Points Still Open",
        "races_left": "Races left",
        "magic_no_p1": "Magic No. {p1_name} (P1)",
        "magic_no_p2": "Magic No. {p2_name} (P2)",
        "magic_no_p3": "Magic No. {p3_name} (P3)",
        "match_point": "🚨 MATCH POINT: {p1_name} clinches next race with {magic_number} pts!",
        "race_in_progress": "RACE IN PROGRESS / COMPLETED",
        "wins_capital": "WINS",
        "podiums_capital": "PODIUMS",
        "best_finish": "BEST FINISH",
        "style_label": "STYLE",
        "style_Dominant": "Dominant",
        "style_Aggressive": "Aggressive",
        "style_Consistent": "Consistent",
        "style_Calculated": "Calculated",
        "style_Scrappy": "Scrappy",
        "style_Resilient": "Resilient",
        "style_Steady": "Steady",
        "style_Chaotic": "Chaotic",
        "style_Unlucky": "Unlucky",
        "style_Wildcard": "Wildcard",
        "round_label": "Round",
        "Coming soon": "Coming soon",
    },
    "pt": {
        "days": "DIAS",
        "hours": "HORAS",
        "minutes": "MINUTOS",
        "seconds": "SEGUNDOS",
        "until_resumes": "ATÉ AO GP DE {next_race_name}",
        "circuits": "CIRCUITOS 🛣️",
        "gp_stats": "ESTATÍSTICAS GP 🏁",
        "our_league": "A nossa liga de F1 na PS5.<br>Uma competição.<br>Sem misericórdia.",
        "season_label": "ÉPOCA",
        "drivers_championship_standings": "🏆 CLASSIFICAÇÃO DE PILOTOS",
        "pos": "POS",
        "driver": "PILOTO",
        "points": "PTS",
        "wins": "VIT.",
        "gap": "DIF.",
        "full_standings": "VER TUDO",
        "hide_standings": "OCULTAR",
        "latest_race": "🏁 ÚLTIMA CORRIDA",
        "grand_prix": "GP",
        "time": "TEMPO",
        "fastest_lap": "V. RÁPIDA",
        "full_results": "RESULTADOS COMPLETOS",
        "hide_results": "OCULTAR",
        "next_race": "📅 PRÓXIMA CORRIDA",
        "date": "DATA",
        "race_length": "DISTÂNCIA",
        "weather": "METEOROLOGIA",
        "assists": "AJUDAS",
        "sunny_dry": "Sol (Seco)",
        "league_rules": "Regras da Liga",
        "constructors_standings": "🏎️ CONSTRUTORES",
        "team": "EQUIPA",
        "teammate_battle": "⚔️ DUELO DE EQUIPA",
        "full_list": "VER DUELOS",
        "hide_list": "OCULTAR",
        "league_statistics": "📊 ESTATÍSTICAS",
        "most_wins": "MAIS VITÓRIAS",
        "most_podiums": "MAIS PÓDIOS",
        "best_avg_finish": "MELHOR MÉDIA",
        "season_calendar": "📅 CALENDÁRIO",
        "rnd": "RND",
        "track": "PISTA",
        "winner": "VENCEDOR",
        "status": "ESTADO",
        "completed": "Concluído",
        "upcoming": "Próxima",
        "full_calendar": "VER CALENDÁRIO",
        "hide_calendar": "OCULTAR",
        "driver_lineup": "🏎️ PILOTOS",
        "all_drivers": "TODOS OS PILOTOS",
        "hide_drivers": "OCULTAR PILOTOS",
        "hall_of_fame": "🏆 SALÃO DA FAMA",
        "most_championships": "MAIS CAMPEONATOS",
        "most_dominant_season": "ÉPOCA MAIS DOMINANTE",
        "all_time_wins": "VITÓRIAS HISTÓRICAS",
        "all_time_podiums": "PÓDIOS HISTÓRICOS",
        "titles_plural": "Títulos",
        "title_singular": "Título",
        "wins_plural": "Vitórias",
        "podiums_plural": "Pódios",
        "pts_gap_suffix": " Pts de Dif.",
        "drivers_title": "Título de Pilotos",
        "constructors_title": "Título de Construtores",
        "decided": "DECIDIDO",
        "is_still_open": "AINDA EM ABERTO",
        "leads": "lidera",
        "by": "por",
        "pts": "pts",
        "finish_line": "Meta",
        "points_still_open": "Pts em jogo",
        "races_left": "Corridas rest.",
        "magic_no_p1": "Nº Mágico {p1_name} (P1)",
        "magic_no_p2": "Nº Mágico {p2_name} (P2)",
        "magic_no_p3": "Nº Mágico {p3_name} (P3)",
        "match_point": "🚨 CAMPEÃO? {p1_name} garante o título no próximo GP com {magic_number} pts!",
        "race_in_progress": "CORRIDA EM DECURSO / CONCLUÍDA",
        "wins_capital": "VITÓRIAS",
        "podiums_capital": "PÓDIOS",
        "best_finish": "MELHOR POS.",
        "style_label": "ESTILO",
        "style_Dominant": "Dominador",
        "style_Aggressive": "Agressivo",
        "style_Consistent": "Consistente",
        "style_Calculated": "Calculador",
        "style_Scrappy": "Combativo",
        "style_Resilient": "Resiliente",
        "style_Steady": "Estável",
        "style_Chaotic": "Caótico",
        "style_Unlucky": "Azarado",
        "style_Wildcard": "Imprevisível",
        "round_label": "Ronda",
        "Coming soon": "Em breve",
    }
}

def _tr(lang: str, key: str) -> str:
    return _T.get(lang, _T["en"]).get(key, key)


def _js_escape(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    return "".join(f"\\u{ord(c):04x}" if ord(c) > 127 else c for c in s)


def get_calendar_for_league(calendar_df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    if calendar_df is None or calendar_df.empty or not isinstance(meta, dict):
        return pd.DataFrame()
    league_name = meta.get("League Name", "")
    season_label = meta.get("SeasonLabel", "")
    # 1. Exact match on League Name
    cal = calendar_df[calendar_df["League Name"].astype(str).str.strip().str.lower() == str(league_name).strip().lower()]
    if not cal.empty:
        return cal
    # 2. Try substring match (e.g. "2026" is in "2026-T02")
    for cal_league in calendar_df["League Name"].dropna().unique():
        cal_league_str = str(cal_league).strip().lower()
        if cal_league_str and (cal_league_str in str(season_label).lower() or cal_league_str in str(league_name).lower()):
            return calendar_df[calendar_df["League Name"] == cal_league]
    return pd.DataFrame()


def _tr_gp(lang: str, gp_name: str) -> str:
    if lang == "pt":
        gp_map = {
            "British": "Grã-Bretanha",
            "Belgian": "Bélgica",
            "Japanese": "Japão",
            "Bahrain": "Barém",
            "Saudi Arabian": "Arábia Saudita",
            "Miami": "Miami",
            "Emilia Romagna": "Emília-Romanha",
            "Spanish": "Espanha",
            "Canadian": "Canadá",
            "Austrian": "Áustria",
            "Hungarian": "Hungria",
            "Dutch": "Países Baixos",
            "Italian": "Itália",
            "Azerbaijan": "Azerbaijão",
            "Singapore": "Singapura",
            "United States": "Estados Unidos",
            "Mexico City": "Cidade do México",
            "Australian": "Austrália",
            "Chinese": "China",
            "São Paulo": "São Paulo",
            "Las Vegas": "Las Vegas",
            "Qatar": "Catar",
            "Abu Dhabi": "Abu Dhabi",
            "Monaco": "Mónaco",
            "French": "França",
            "Portuguese": "Portugal",
            "Brazil": "Brasil",
            "Mexico": "México",
            "Brazilian": "Brasil",
            "Mexican": "México",
            "70th Anniversary": "70.º Aniversário",
            "Eifel": "Eifel",
            "Styrian": "Estíria",
            "Turkish": "Turquia",
            "Tuscan": "Toscana",
        }
        clean_name = gp_name.replace(" GP", "").strip()
        return gp_map.get(clean_name, clean_name)
    return gp_name.replace(" GP", "").strip()


def _tr_track(lang: str, gp_name: str, circuit: str = None) -> str:
    short_trk = circuit if (circuit and pd.notna(circuit)) else GP_SHORT_TRACK.get(gp_name, gp_name.replace(" GP", ""))
    if lang == "pt" and short_trk == "Mexico City":
        return "Cidade do México"
    return short_trk


def get_base64_image(path: str) -> str:
    """Read a local image file and return a base64 data URI string."""
    p = Path(path)
    if not p.exists():
        return ""
    suffix = p.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(suffix, "image/png")
    data = p.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# Cache hero image at module load so we don't re-encode every render
_HERO_IMG_PATH = Path(__file__).parent / "assets" / "hero_banner.png"
_HERO_B64 = get_base64_image(str(_HERO_IMG_PATH)) # Reload image with explicit numbers v2

# ── Helmet images ──
_HELMETS_DIR = Path(__file__).parent / "assets" / "helmets"

# Team name → helmet filename (without extension)
TEAM_HELMET_FILE = {
    "Ferrari": "ferrari", "McLaren": "mclaren", "Red Bull": "redbull",
    "Mercedes": "mercedes", "Aston Martin": "astonmartin", "Alpine": "alpine",
    "Williams": "williams", "Racing Bulls": "racingbulls",
    "Kick Sauber": "kicksauber", "Haas": "haas",
    "Renault": "alpine", "Alfa Romeo": "kicksauber", "Racing Point": "astonmartin",
    "Audi": "kicksauber", "Cadillac": "haas",
}

# Custom driver overrides (league-specific players with bespoke helmets)
DRIVER_HELMET_FILE = {
    "TomasRodri21": "tomasrodri21",
    "Fatacuida": "fatacuida",
    "Polingua": "polingua",
}

@lru_cache(maxsize=128)
def _get_helmet_b64(driver: str, team: str) -> str:
    """Return base64 data URI for a driver's helmet, falling back to team."""
    fname = DRIVER_HELMET_FILE.get(driver, TEAM_HELMET_FILE.get(team, ""))
    if not fname:
        return ""
    p = _HELMETS_DIR / f"{fname}.png"
    return get_base64_image(str(p))

_TRACKS_DIR = Path(__file__).parent / "assets" / "tracks"

@lru_cache(maxsize=32)
def _get_track_bg_b64(gp_name: str) -> str:
    """Return base64 data URI for a track background image."""
    short_name = GP_SHORT_TRACK.get(gp_name, gp_name.replace(" GP", ""))
    p_jpg = _TRACKS_DIR / f"{short_name}.jpg"
    p_png = _TRACKS_DIR / f"{short_name}.png"
    if p_jpg.exists():
        return get_base64_image(str(p_jpg))
    if p_png.exists():
        return get_base64_image(str(p_png))
    p_default = _TRACKS_DIR / "default.jpg"
    if p_default.exists():
        return get_base64_image(str(p_default))
    return ""

# ── Team color + icon mapping ──
TEAM_COLORS = {
    "Ferrari":       "#E8002D",
    "McLaren":       "#FF8000",
    "Red Bull":      "#3671C6",
    "Mercedes":      "#27F4D2",
    "Aston Martin":  "#229971",
    "Alpine":        "#FF87BC",
    "Williams":      "#64C4FF",
    "Racing Bulls":  "#6692FF",
    "Kick Sauber":   "#52E252",
    "Haas":          "#B6BABD",
    "Renault":       "#FFD800",
    "Alfa Romeo":    "#C92D4B",
    "Racing Point":  "#F596C8",
    "Audi":          "#F5002C",
    "Cadillac":      "#B59A57",
}

TEAM_SHORT = {
    "Ferrari":       "FER",
    "McLaren":       "MCL",
    "Red Bull":      "RBR",
    "Mercedes":      "MER",
    "Aston Martin":  "AMR",
    "Alpine":        "ALP",
    "Williams":      "WIL",
    "Racing Bulls":  "RCB",
    "Kick Sauber":   "SAU",
    "Haas":          "HAS",
    "Renault":       "REN",
    "Alfa Romeo":    "ALF",
    "Racing Point":  "RPC",
}

# ── GP name → circuit SVG mapping (latest layout) ──
_SVG_BASE = "https://raw.githubusercontent.com/julesr0y/f1-circuits-svg/main/circuits/minimal/white-outline"
CIRCUIT_SVG_MAP = {
    "British GP":         f"{_SVG_BASE}/silverstone-8.svg",
    "Belgian GP":         f"{_SVG_BASE}/spa-francorchamps-4.svg",
    "Japanese GP":        f"{_SVG_BASE}/suzuka-2.svg",
    "Bahrain GP":         f"{_SVG_BASE}/bahrain-3.svg",
    "Saudi Arabian GP":   f"{_SVG_BASE}/jeddah-1.svg",
    "Miami GP":           f"{_SVG_BASE}/miami-1.svg",
    "Emilia Romagna GP":  f"{_SVG_BASE}/imola-3.svg",
    "Spanish GP":         f"{_SVG_BASE}/catalunya-6.svg",
    "Canadian GP":        f"{_SVG_BASE}/montreal-6.svg",
    "Austrian GP":        f"{_SVG_BASE}/spielberg-3.svg",
    "Hungarian GP":       f"{_SVG_BASE}/hungaroring-3.svg",
    "Dutch GP":           f"{_SVG_BASE}/zandvoort-5.svg",
    "Italian GP":         f"{_SVG_BASE}/monza-7.svg",
    "Azerbaijan GP":      f"{_SVG_BASE}/baku-1.svg",
    "Singapore GP":       f"{_SVG_BASE}/marina-bay-4.svg",
    "United States GP":   f"{_SVG_BASE}/austin-1.svg",
    "Mexico City GP":     f"{_SVG_BASE}/mexico-city-3.svg",
    "Australian GP":      f"{_SVG_BASE}/melbourne-2.svg",
    "Chinese GP":         f"{_SVG_BASE}/shanghai-1.svg",
    "São Paulo GP":       f"{_SVG_BASE}/interlagos-2.svg",
    "Las Vegas GP":       f"{_SVG_BASE}/las-vegas-1.svg",
    "Qatar GP":           f"{_SVG_BASE}/lusail-1.svg",
    "Abu Dhabi GP":       f"{_SVG_BASE}/yas-marina-2.svg",
    "Monaco GP":          f"{_SVG_BASE}/monaco-6.svg",
    "French GP":          f"{_SVG_BASE}/paul-ricard-3.svg",
    "Portuguese GP":      f"{_SVG_BASE}/portimao-1.svg",
    "Brazil GP":          f"{_SVG_BASE}/interlagos-2.svg",
    "Mexico GP":          f"{_SVG_BASE}/mexico-city-3.svg",
    "Brazilian GP":       f"{_SVG_BASE}/interlagos-2.svg",
    "Mexican GP":         f"{_SVG_BASE}/mexico-city-3.svg",
}

# GP name → country flag emoji
GP_FLAGS = {
    "British GP": "🇬🇧", "Belgian GP": "🇧🇪", "Japanese GP": "🇯🇵",
    "Bahrain GP": "🇧🇭", "Saudi Arabian GP": "🇸🇦", "Miami GP": "🇺🇸",
    "Emilia Romagna GP": "🇮🇹", "Spanish GP": "🇪🇸", "Canadian GP": "🇨🇦",
    "Austrian GP": "🇦🇹", "Hungarian GP": "🇭🇺", "Dutch GP": "🇳🇱",
    "Italian GP": "🇮🇹", "Azerbaijan GP": "🇦🇿", "Singapore GP": "🇸🇬",
    "United States GP": "🇺🇸", "Mexico City GP": "🇲🇽", "Australian GP": "🇦🇺",
    "Chinese GP": "🇨🇳", "São Paulo GP": "🇧🇷", "Las Vegas GP": "🇺🇸",
    "Qatar GP": "🇶🇦", "Abu Dhabi GP": "🇦🇪", "Monaco GP": "🇲🇨",
    "French GP": "🇫🇷", "Portuguese GP": "🇵🇹",
    "Brazil GP": "🇧🇷", "Mexico GP": "🇲🇽",
    "Brazilian GP": "🇧🇷", "Mexican GP": "🇲🇽",
}

# GP name → short track name for calendar display
GP_SHORT_TRACK = {
    "British GP": "Silverstone", "Belgian GP": "Spa-Francorchamps",
    "Japanese GP": "Suzuka", "Bahrain GP": "Bahrain",
    "Saudi Arabian GP": "Jeddah", "Miami GP": "Miami",
    "Emilia Romagna GP": "Imola", "Spanish GP": "Barcelona",
    "Canadian GP": "Montreal", "Austrian GP": "Spielberg",
    "Hungarian GP": "Hungaroring", "Dutch GP": "Zandvoort",
    "Italian GP": "Monza", "Azerbaijan GP": "Baku",
    "Singapore GP": "Marina Bay", "United States GP": "Austin",
    "Mexico City GP": "Mexico City", "Australian GP": "Melbourne",
    "Chinese GP": "Shanghai", "São Paulo GP": "Interlagos",
    "Las Vegas GP": "Las Vegas", "Qatar GP": "Lusail",
    "Abu Dhabi GP": "Yas Marina", "Monaco GP": "Monaco",
    "French GP": "Paul Ricard", "Portuguese GP": "Portimão",
    "Brazil GP": "Interlagos", "Mexico GP": "Mexico City",
    "Brazilian GP": "Interlagos", "Mexican GP": "Mexico City",
}

# GP name → ISO country code for flag images
GP_COUNTRY_CODES = {
    "British GP": "gb", "Belgian GP": "be", "Japanese GP": "jp",
    "Bahrain GP": "bh", "Saudi Arabian GP": "sa", "Miami GP": "us",
    "Emilia Romagna GP": "it", "Spanish GP": "es", "Canadian GP": "ca",
    "Austrian GP": "at", "Hungarian GP": "hu", "Dutch GP": "nl",
    "Italian GP": "it", "Azerbaijan GP": "az", "Singapore GP": "sg",
    "United States GP": "us", "Mexico City GP": "mx", "Australian GP": "au",
    "Chinese GP": "cn", "São Paulo GP": "br", "Las Vegas GP": "us",
    "Qatar GP": "qa", "Abu Dhabi GP": "ae", "Monaco GP": "mc",
    "French GP": "fr", "Portuguese GP": "pt",
    "Brazil GP": "br", "Mexico GP": "mx",
    "Brazilian GP": "br", "Mexican GP": "mx",
    "Madrid GP": "es",
}

def _flag_img(gp_name: str, height: int = 18) -> str:
    """Return an <img> tag with the country flag for a GP name."""
    code = GP_COUNTRY_CODES.get(gp_name, "")
    if not code:
        return GP_FLAGS.get(gp_name, "")
    return (
        f'<img src="https://flagcdn.com/w40/{code}.png" '
        f'style="height:{height}px;vertical-align:middle;border-radius:2px;margin-left:6px;" />'
    )

def _driving_style(wins: int, podiums: int, avg_finish: float, consistency: float) -> str:
    """Derive a fun driving style label from stats."""
    if wins >= 5:
        return "Dominant"
    elif wins >= 3 and consistency < 2.0:
        return "Aggressive"
    elif podiums >= 5 and consistency < 2.5:
        return "Consistent"
    elif avg_finish <= 3.0:
        return "Calculated"
    elif wins >= 2:
        return "Scrappy"
    elif podiums >= 2:
        return "Resilient"
    elif avg_finish <= 8.0:
        return "Steady"
    elif consistency > 5.0:
        return "Chaotic"
    elif avg_finish > 12.0:
        return "Unlucky"
    else:
        return "Wildcard"


def _format_time(t_val, mode="time") -> str:
    """Format time/gap and fastest lap strings gracefully."""
    t_str = str(t_val)
    if t_str == "nan" or not t_str.strip() or t_str == "NaT" or t_str.lower() == "none":
        return "-"
    if t_str.startswith('0 days '):
        t_str = t_str.replace('0 days ', '')
        
    if mode == "time":
        if '.' in t_str:
            t_str = t_str.split('.')[0]
        if t_str.startswith("0") and len(t_str) > 1 and t_str[1] != ':':
            t_str = t_str[1:]
    else:
        if t_str.startswith('00:'):
            t_str = t_str[3:]
        if t_str.startswith("0") and len(t_str) > 1 and t_str[1] != ':':
            t_str = t_str[1:]
        if '.' in t_str:
            parts = t_str.split('.')
            t_str = parts[0] + '.' + parts[1][:3]
    return t_str


def _team_badge_html(team_name: str, size: int = 16) -> str:
    """Return a small coloured circle with team abbreviation as an inline badge."""
    color = TEAM_COLORS.get(team_name, "#555")
    short = TEAM_SHORT.get(team_name, "?")
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;border-radius:50%;background:{color};'
        f'font-size:7px;font-weight:900;color:#000;margin-right:6px;flex-shrink:0;'
        f'vertical-align:middle;line-height:1;">{short}</span>'
    )


def _parse_lisbon_time(time_val):
    """
    Parses a time value from the 'Time (Lisbon)' column.
    Returns (hour, minute, second). Defaults to (7, 30, 0).
    """
    if pd.isna(time_val) or time_val is None:
        return 7, 30, 0
    if isinstance(time_val, str):
        s = time_val.strip()
        if not s:
            return 7, 30, 0
        m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
        if m:
            h = int(m.group(1))
            m_val = int(m.group(2))
            s_val = int(m.group(3)) if m.group(3) else 0
            return h, m_val, s_val
    elif hasattr(time_val, "hour"):
        return time_val.hour, time_val.minute, time_val.second
    elif isinstance(time_val, (int, float)):
        total_seconds = int(time_val * 86400)
        h = (total_seconds // 3600) % 24
        m_val = (total_seconds // 60) % 60
        s_val = total_seconds % 60
        return h, m_val, s_val
    return 7, 30, 0


def render_puskas_hero(meta: dict, calendar_raw: pd.DataFrame = None, lang: str = "en") -> str:
    next_race_name = ""
    next_race_target_iso = ""
    if calendar_raw is not None and not calendar_raw.empty:
        cal = get_calendar_for_league(calendar_raw, meta)
        if not cal.empty:
            upcoming = cal[cal["Status"].astype(str).str.lower() == "upcoming"]
            if not upcoming.empty:
                nr = upcoming.iloc[0]
                next_race_name = nr.get("GP Name", "TBD")
                date_val = nr.get("Date", "")
                if pd.notna(date_val):
                    try:
                        h, m, s = _parse_lisbon_time(nr.get("Time (Lisbon)", None))
                        dt = pd.Timestamp(date_val).replace(hour=h, minute=m, second=s)
                        dt_tz = dt.tz_localize("Europe/Lisbon")
                        next_race_target_iso = dt_tz.isoformat()
                    except Exception:
                        ts = pd.Timestamp(date_val)
                        month = ts.month
                        offset = "+00:00"
                        if 3 < month < 10:
                            offset = "+01:00"
                        elif month == 3:
                            last_sun = 31 - (pd.Timestamp(f"{ts.year}-03-31").dayofweek + 1) % 7
                            if ts.day >= last_sun:
                                offset = "+01:00"
                        elif month == 10:
                            last_sun = 31 - (pd.Timestamp(f"{ts.year}-10-31").dayofweek + 1) % 7
                            if ts.day < last_sun:
                                offset = "+01:00"
                        h, m, s = _parse_lisbon_time(nr.get("Time (Lisbon)", None))
                        next_race_target_iso = f"{ts.strftime('%Y-%m-%d')}T{h:02d}:{m:02d}:{s:02d}{offset}"

    countdown_html = ""
    if next_race_target_iso:
        until_text = _tr(lang, "until_resumes").format(next_race_name=_tr_gp(lang, next_race_name).upper())
        countdown_html = f"""
        <div class="p-countdown-container" id="p-countdown-box">
            <div class="p-countdown-timer">
                <div class="p-countdown-segment">
                    <span class="p-countdown-value" id="cd-days">00</span>
                    <span class="p-countdown-label">{_tr(lang, "days")}</span>
                </div>
                <div class="p-countdown-segment">
                    <span class="p-countdown-value" id="cd-hours">00</span>
                    <span class="p-countdown-label">{_tr(lang, "hours")}</span>
                </div>
                <div class="p-countdown-segment">
                    <span class="p-countdown-value" id="cd-minutes">00</span>
                    <span class="p-countdown-label">{_tr(lang, "minutes")}</span>
                </div>
                <div class="p-countdown-segment">
                    <span class="p-countdown-value" id="cd-seconds">00</span>
                    <span class="p-countdown-label">{_tr(lang, "seconds")}</span>
                </div>
            </div>
            <div class="p-countdown-text" id="cd-text">{until_text}</div>
        </div>
        """

    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@400;600;700&family=Inter:wght@400;600;800&display=swap');
    
    .p-hero {
        background: linear-gradient(to right, #0b0b0f 15%, rgba(11,11,15,0.3) 70%, transparent 100%), 
                    url('""" + _HERO_B64 + """');
        background-color: #0b0b0f; /* fallback */
        background-size: cover;
        background-position: center;
        padding: 4rem 2rem 2.5rem 2rem;
        border-bottom: 2px solid #e10600;
        position: relative;
        display: flex;
        flex-direction: column;
    }
    .p-hero-title {
        font-family: 'Teko', sans-serif;
        font-size: 5rem;
        font-weight: 700;
        line-height: 1;
        font-style: italic;
        margin: 0;
        letter-spacing: 2px;
    }
    .p-hero-title .red { color: #e10600; }
    .p-hero-sub {
        color: #888;
        font-size: 0.9rem;
        margin-top: 1rem;
        max-width: 300px;
        line-height: 1.4;
    }
    .p-hero-season {
        color: #e10600;
        font-weight: 800;
        font-size: 0.9rem;
        margin-top: 1rem;
        letter-spacing: 1px;
    }
    .p-btn {
        background: #e10600;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 800;
        border-radius: 4px;
        margin-top: 1rem;
        cursor: pointer;
        display: inline-block;
    }
    .p-btn.dark {
        background: #1a1a1a;
        border: 1px solid #333;
    }
    .p-countdown-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        width: 100%;
        margin-top: 2.5rem;
        text-align: center;
    }
    .p-countdown-timer {
        display: flex;
        gap: 1.5rem;
        justify-content: center;
        align-items: center;
    }
    .p-countdown-segment {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 60px;
    }
    .p-countdown-value {
        font-family: 'Teko', sans-serif;
        font-size: 3.5rem;
        font-weight: 600;
        line-height: 0.9;
        color: #ffffff;
        letter-spacing: 1px;
        text-shadow: 0 4px 10px rgba(0, 0, 0, 0.9), 0 0 20px rgba(0, 0, 0, 0.6);
    }
    .p-countdown-label {
        font-size: 0.65rem;
        font-weight: 600;
        color: #aaa;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 0.2rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.9);
    }
    .p-countdown-text {
        font-family: 'Teko', sans-serif;
        font-size: 1.6rem;
        font-weight: 600;
        color: #ffffff;
        letter-spacing: 2px;
        margin-top: 0.6rem;
        text-transform: uppercase;
        text-shadow: 0 2px 6px rgba(0, 0, 0, 0.9);
    }
    
    @media (max-width: 768px) {
        .puskas-container { margin: -1rem; }
        .p-hero { padding: 3rem 1rem 1.5rem 1rem; }
        .p-hero-title { font-size: 3rem; }
        .p-countdown-value { font-size: 2.5rem; }
        .p-countdown-text { font-size: 1.2rem; }
        .p-countdown-timer { gap: 1rem; }
        .p-countdown-segment { min-width: 45px; }
    }
    </style>
    """
    html = f"""
    {css}
    <div class="puskas-container">
        <!-- HERO -->
        <div class="p-hero" style="position: relative;">
            <div class="p-hero-main">
                <div class="p-hero-title">F1 PUSKAS<br><span class="red">LEAGUE</span></div>
                <div class="p-hero-sub">{_tr(lang, "our_league")}</div>
                <div class="p-hero-season">{_tr(lang, "season_label")} 1 • {meta.get("SeasonLabel", "2025")}</div>
                <div style="margin-top: 1rem;">
                    <div class="p-btn" id="btn-hero-circuits" style="cursor: pointer;">{_tr(lang, "circuits")}</div>
                    <div class="p-btn dark" id="btn-hero-gpstats" style="cursor: pointer;">{_tr(lang, "gp_stats")}</div>
                </div>
            </div>
            {countdown_html}
        </div>
    </div>
    """
    return "\n".join(line.lstrip() for line in html.split("\n"))

def render_puskas_dashboard(latest_gp: pd.DataFrame, calendar_raw: pd.DataFrame, st_tbl_latest: pd.DataFrame, meta: dict, base_all: pd.DataFrame = None, lang: str = "en") -> str:
    next_race_target_iso = ""
    if calendar_raw is not None and not calendar_raw.empty:
        cal = get_calendar_for_league(calendar_raw, meta)
        if not cal.empty:
            upcoming = cal[cal["Status"].astype(str).str.lower() == "upcoming"]
            if not upcoming.empty:
                nr = upcoming.iloc[0]
                date_val = nr.get("Date", "")
                if pd.notna(date_val):
                    try:
                        h, m, s = _parse_lisbon_time(nr.get("Time (Lisbon)", None))
                        dt = pd.Timestamp(date_val).replace(hour=h, minute=m, second=s)
                        dt_tz = dt.tz_localize("Europe/Lisbon")
                        next_race_target_iso = dt_tz.isoformat()
                    except Exception:
                        ts = pd.Timestamp(date_val)
                        month = ts.month
                        offset = "+00:00"
                        if 3 < month < 10:
                            offset = "+01:00"
                        elif month == 3:
                            last_sun = 31 - (pd.Timestamp(f"{ts.year}-03-31").dayofweek + 1) % 7
                            if ts.day >= last_sun:
                                offset = "+01:00"
                        elif month == 10:
                            last_sun = 31 - (pd.Timestamp(f"{ts.year}-10-31").dayofweek + 1) % 7
                            if ts.day < last_sun:
                                offset = "+01:00"
                        h, m, s = _parse_lisbon_time(nr.get("Time (Lisbon)", None))
                        next_race_target_iso = f"{ts.strftime('%Y-%m-%d')}T{h:02d}:{m:02d}:{s:02d}{offset}"

    # ── Build driver→team lookup from latest GP data ──
    driver_team = {}
    if not latest_gp.empty:
        for _, row in latest_gp.drop_duplicates(subset=["Driver"]).iterrows():
            driver_team[str(row["Driver"])] = str(row.get("Team", ""))
    if base_all is not None and not base_all.empty:
        for _, row in base_all.drop_duplicates(subset=["Driver"]).iterrows():
            d = str(row["Driver"])
            if d not in driver_team:
                driver_team[d] = str(row.get("Team", ""))

    reigning_champ = ""
    if base_all is not None and not base_all.empty:
        try:
            # 1. Identify ongoing seasons to exclude them
            ongoing_seasons = set()
            if calendar_raw is not None and not calendar_raw.empty:
                upcoming_leagues = calendar_raw[calendar_raw['Status'].astype(str).str.lower() == 'upcoming']['League Name'].dropna().unique().tolist()
                if upcoming_leagues:
                    standings_seasons = base_all[['SeasonLabel', 'League Name']].drop_duplicates().values.tolist()
                    for label, league in standings_seasons:
                        st_gps = set(base_all[(base_all['SeasonLabel'] == label) & (base_all['League Name'] == league) & (~base_all['IsSeasonFinal'])]['GP Name'].dropna().unique())
                        for ul in upcoming_leagues:
                            if str(ul).strip().lower() == str(league).strip().lower():
                                ongoing_seasons.add(label)
                                break
                            cal_gps = set(calendar_raw[calendar_raw['League Name'] == ul]['GP Name'].dropna().unique())
                            if cal_gps and st_gps and st_gps.issubset(cal_gps):
                                ongoing_seasons.add(label)
                                break

            # 2. Filter out ongoing seasons
            df_finished = base_all[~base_all["SeasonLabel"].isin(ongoing_seasons)].copy()
            if not df_finished.empty:
                # 3. Find the champions of each finished season
                d = df_finished.groupby(["SeasonLabel", "Driver"], as_index=False)["Points"].sum()
                d = d.sort_values(["SeasonLabel", "Points"], ascending=[True, False])
                champs = d.groupby("SeasonLabel").head(1)
                
                # 4. Sort seasons and get the champion of the latest one
                def _season_sort_key(label):
                    import re
                    if pd.isna(label):
                        return (0, 0, "")
                    s = str(label).strip()
                    m = re.match(r"(\d{4})[-/]T(\d{2})", s)
                    if m:
                        return (1, int(m.group(1)), f"T{m.group(2)}")
                    m2 = re.match(r"(\d{4})", s)
                    if m2:
                        return (2, int(m2.group(1)), "")
                    return (3, 0, s)

                champs_list = champs.to_dict('records')
                if champs_list:
                    champs_list.sort(key=lambda x: _season_sort_key(x["SeasonLabel"]))
                    reigning_champ = champs_list[-1]["Driver"]
        except Exception:
            pass

    # Check if latest GP has a Sprint Race to dynamically adjust standings card length
    has_sprint = False
    if not latest_gp.empty:
        last_r = int(latest_gp["Round"].max())
        d0_temp = latest_gp[(latest_gp["Round"] == last_r) & (~latest_gp["IsSeasonFinal"])]
        if "Type" in d0_temp.columns and (d0_temp["Type"] == "SR").any():
            has_sprint = True
            
    standings_limit = 8 if has_sprint else 6

    # 1. CHAMPIONSHIP STANDINGS
    standings_top_html = ""
    standings_extra_html = ""
    all_standings = list(st_tbl_latest.iterrows())
    for i, (idx, row) in enumerate(all_standings):
        pos = int(row.get('Pos', 0))
        driver = str(row.get('Driver', ''))
        points = int(row.get('Points', 0))
        wins = int(row.get('Wins', 0))
        
        # Calculate gap to leader
        gap = "-"
        if pos > 1 and not st_tbl_latest.empty:
            leader_pts = st_tbl_latest.iloc[0]['Points']
            gap = f"-{int(leader_pts - points)}"
            
        color_class = "pos-gold" if pos == 1 else "pos-silver" if pos == 2 else "pos-bronze" if pos == 3 else "pos-other"
        team = driver_team.get(driver, "")
        badge = _team_badge_html(team, 18)
        
        disp_driver = f"{driver} ⭐" if driver == reigning_champ else driver
        row_html = f"""
        <div class="p-row">
            <div class="p-col p-pos"><span class="{color_class}">{pos}</span></div>
            <div class="p-col p-driver">{badge}{disp_driver}</div>
            <div class="p-col p-pts">{points}</div>
            <div class="p-col p-wins">{wins}</div>
            <div class="p-col p-gap">{gap}</div>
        </div>
        """
        if i < standings_limit:
            standings_top_html += row_html
        else:
            standings_extra_html += row_html

    # 2. LATEST RACE
    latest_race_name = "TBD"
    latest_round = "-"
    latest_flag_img = ""
    latest_race_card_content = ""
    if not latest_gp.empty:
        last_r = int(latest_gp["Round"].max())
        d0 = latest_gp[(latest_gp["Round"] == last_r) & (~latest_gp["IsSeasonFinal"])].copy()
        if "Type" not in d0.columns:
            d0["Type"] = "R"
            
        if not d0.empty:
            latest_race_name = d0.iloc[0]["GP Name"]
            latest_round = last_r
            latest_flag_img = _flag_img(latest_race_name, 20)
            
            d0_race = d0[d0["Type"] == "R"].copy()
            d0_sprint = d0[d0["Type"] == "SR"].copy()
            
            def _build_results_html(df_sub, view_id, show_headers=True):
                top_html = ""
                extra_html = ""
                df_sort = df_sub.sort_values(["Finish Pos", "Driver"])
                for idx, (index_val, row) in enumerate(df_sort.iterrows()):
                    fpos = int(row["Finish Pos"]) if pd.notna(row["Finish Pos"]) else "-"
                    drv = str(row["Driver"])
                    disp_drv = f"{drv} ⭐" if drv == reigning_champ else drv
                    pts = int(row["Points"]) if pd.notna(row["Points"]) else 0
                    team = str(row.get("Team", ""))
                    badge = _team_badge_html(team, 18)
                    
                    time_val = _format_time(row.get("Time", "-"), mode="time")
                    fl_val = _format_time(row.get("Fastest Lap", "-"), mode="fl")

                    r_html = f"""
                    <div class="p-row">
                        <div class="p-col p-pos">{fpos}</div>
                        <div class="p-col p-driver">{badge}{disp_drv}</div>
                        <div class="p-time">{time_val}</div>
                        <div class="p-fl">{fl_val}</div>
                        <div class="p-col p-pts">{pts}</div>
                    </div>
                    """
                    if idx < 6:
                        top_html += r_html
                    else:
                        extra_html += r_html
                
                headers = ""
                if show_headers:
                    headers = f"""
                    <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                        <div class="p-col p-pos">{_tr(lang, "pos")}</div>
                        <div class="p-col p-driver">{_tr(lang, "driver")}</div>
                        <div class="p-time">{_tr(lang, "time")}</div>
                        <div class="p-fl">{_tr(lang, "fastest_lap")}</div>
                        <div class="p-col p-pts">{_tr(lang, "points")}</div>
                    </div>
                    """
                
                extra_btn = ""
                if len(df_sort) > 6:
                    btn_id = f"btn-full-{view_id}"
                    extra_id = f"extra-{view_id}"
                    extra_btn = f"""
                    <div id="{extra_id}" style="display:none;">
                        {extra_html}
                    </div>
                    <div class="p-btn-outline" id="{btn_id}">{_tr(lang, "full_results")}</div>
                    <script>
                    document.getElementById('{btn_id}').addEventListener('click', function() {{
                        var ex = document.getElementById('{extra_id}');
                        if (ex.style.display === 'none') {{
                            ex.style.display = 'block';
                            this.textContent = '{_tr(lang, "show_less") if lang == "en" else "MOSTRAR MENOS"}';
                        }} else {{
                            ex.style.display = 'none';
                            this.textContent = '{_tr(lang, "full_results")}';
                        }}
                    }});
                    </script>
                    """
                
                return f"""
                <div id="{view_id}">
                    {headers}
                    {top_html}
                    {extra_btn}
                </div>
                """

            def _build_weekend_score_html(df_r, df_sr):
                drivers = pd.concat([df_r["Driver"], df_sr["Driver"]]).unique()
                wk_rows = []
                for d in drivers:
                    sr_pts = df_sr[df_sr["Driver"] == d]["Points"].sum()
                    r_pts = df_r[df_r["Driver"] == d]["Points"].sum()
                    t_sub = df_r[df_r["Driver"] == d]
                    if t_sub.empty:
                        t_sub = df_sr[df_sr["Driver"] == d]
                    team = str(t_sub.iloc[0]["Team"]) if not t_sub.empty else ""
                    wk_rows.append({
                        "Driver": d,
                        "Team": team,
                        "SR": int(sr_pts),
                        "Race": int(r_pts),
                        "Total": int(sr_pts + r_pts)
                    })
                df_wk = pd.DataFrame(wk_rows).sort_values(by=["Total", "Race"], ascending=[False, False])
                
                headers = f"""
                <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                    <div class="p-col p-pos">{_tr(lang, "pos")}</div>
                    <div class="p-col p-driver">{_tr(lang, "driver")}</div>
                    <div style="width: 50px; text-align: right;">SR</div>
                    <div style="width: 50px; text-align: right;">RACE</div>
                    <div class="p-col p-pts" style="width: 60px; text-align: right; font-weight: 900; color: #fff;">TOTAL</div>
                </div>
                """
                
                top_html = ""
                extra_html = ""
                for idx, r in enumerate(df_wk.iterrows(), start=1):
                    _, row = r
                    drv = str(row["Driver"])
                    disp_drv = f"{drv} ⭐" if drv == reigning_champ else drv
                    team = str(row["Team"])
                    badge = _team_badge_html(team, 18)
                    sr_pts = int(row["SR"])
                    r_pts = int(row["Race"])
                    tot_pts = int(row["Total"])
                    
                    r_html = f"""
                    <div class="p-row" style="align-items: center;">
                        <div class="p-col p-pos">{idx}</div>
                        <div class="p-col p-driver">{badge}{disp_drv}</div>
                        <div style="width: 50px; text-align: right; color: #aaa;">{sr_pts}</div>
                        <div style="width: 50px; text-align: right; color: #aaa;">{r_pts}</div>
                        <div class="p-col p-pts" style="width: 60px; text-align: right; font-weight: 800; color: #e10600;">{tot_pts}</div>
                    </div>
                    """
                    if idx <= 6:
                        top_html += r_html
                    else:
                        extra_html += r_html
                        
                extra_btn = ""
                if len(df_wk) > 6:
                    btn_id = "btn-full-weekend"
                    extra_id = "extra-weekend"
                    extra_btn = f"""
                    <div id="{extra_id}" style="display:none;">
                        {extra_html}
                    </div>
                    <div class="p-btn-outline" id="{btn_id}">{_tr(lang, "full_results")}</div>
                    <script>
                    document.getElementById('{btn_id}').addEventListener('click', function() {{
                        var ex = document.getElementById('{extra_id}');
                        if (ex.style.display === 'none') {{
                            ex.style.display = 'block';
                            this.textContent = '{_tr(lang, "show_less") if lang == "en" else "MOSTRAR MENOS"}';
                        }} else {{
                            ex.style.display = 'none';
                            this.textContent = '{_tr(lang, "full_results")}';
                        }}
                    }});
                    </script>
                    """
                return f"""
                <div id="latest-race-view-weekend" style="display:none;">
                    {headers}
                    {top_html}
                    {extra_btn}
                </div>
                """

            if not d0_sprint.empty:
                latest_race_card_content = f"""
                <div class="p-card-tabs" style="display:flex; gap:6px; margin-bottom:1rem; border-bottom:1px solid #222; padding-bottom:0.6rem;">
                    <div class="p-card-tab active" id="tab-btn-race" onclick="switchLatestRaceView('race')" style="cursor:pointer; font-size:0.7rem; font-weight:800; padding:0.3rem 0.6rem; border-radius:3px; background:#e10600; color:#fff;">{_tr(lang, "grand_prix").upper()}</div>
                    <div class="p-card-tab" id="tab-btn-sprint" onclick="switchLatestRaceView('sprint')" style="cursor:pointer; font-size:0.7rem; font-weight:800; padding:0.3rem 0.6rem; border-radius:3px; background:#222; color:#aaa;">SPRINT</div>
                    <div class="p-card-tab" id="tab-btn-weekend" onclick="switchLatestRaceView('weekend')" style="cursor:pointer; font-size:0.7rem; font-weight:800; padding:0.3rem 0.6rem; border-radius:3px; background:#222; color:#aaa;">{_tr(lang, "weekend").upper() if lang == "en" else "FIM DE SEMANA"}</div>
                </div>
                {_build_results_html(d0_race, "latest-race-view-race")}
                <div id="latest-race-view-sprint" style="display:none;">
                    {_build_results_html(d0_sprint, "latest-race-view-sprint-internal", show_headers=True)}
                </div>
                {_build_weekend_score_html(d0_race, d0_sprint)}
                """
            else:
                latest_race_card_content = _build_results_html(d0_race, "latest-race-view-race")

    # 1.5 CONSTRUCTORS STANDINGS
    c_standings_top_html = ""
    c_standings_extra_html = ""
    if not latest_gp.empty and "Team" in latest_gp.columns:
        valid_gp = latest_gp[latest_gp["Team"].notna() & (latest_gp["Team"] != "")].copy()
        team_pts = valid_gp.groupby("Team")["Points"].sum().reset_index()
        team_wins = valid_gp[valid_gp["Finish Pos"] == 1].groupby("Team").size().reset_index(name="Wins")
        team_st = pd.merge(team_pts, team_wins, on="Team", how="left").fillna(0)
        team_st = team_st.sort_values(["Points", "Wins"], ascending=[False, False]).reset_index(drop=True)
        
        real_pos = 0
        for i, (idx, row) in enumerate(team_st.iterrows()):
            team = str(row["Team"])
            if team.lower() in ["nan", "none", ""]: continue
            real_pos += 1
            points = int(row["Points"])
            wins = int(row["Wins"])
            
            gap = "-"
            if real_pos > 1 and not team_st.empty:
                leader_pts = team_st.iloc[0]["Points"]
                gap = f"-{int(leader_pts - points)}"
                
            color_class = "pos-gold" if real_pos == 1 else "pos-silver" if real_pos == 2 else "pos-bronze" if real_pos == 3 else "pos-other"
            badge = _team_badge_html(team, 18)
            
            row_html = f"""
            <div class="p-row">
                <div class="p-col p-pos"><span class="{color_class}">{real_pos}</span></div>
                <div class="p-col p-driver">{badge}{team}</div>
                <div class="p-col p-pts">{points}</div>
                <div class="p-col p-wins">{wins}</div>
                <div class="p-col p-gap">{gap}</div>
            </div>
            """
            if real_pos <= 6:
                c_standings_top_html += row_html
            else:
                c_standings_extra_html += row_html

    # 3. NEXT RACE (with circuit layout, date, race length, weather)
    next_race_name = "TBD"
    next_race_date = "-"
    next_race_flag_img = ""
    next_race_circuit_svg = ""
    if not calendar_raw.empty:
        cal = get_calendar_for_league(calendar_raw, meta)
        if not cal.empty:
            upcoming = cal[cal["Status"].astype(str).str.lower() == "upcoming"]
            if not upcoming.empty:
                nr = upcoming.iloc[0]
                next_race_name = nr.get("GP Name", "TBD")
                next_race_flag_img = _flag_img(next_race_name, 18)
                date_val = nr.get("Date", "")
                if pd.notna(date_val):
                    try:
                        h, m, s = _parse_lisbon_time(nr.get("Time (Lisbon)", None))
                        dt = pd.Timestamp(date_val).replace(hour=h, minute=m, second=s)
                    except Exception:
                        try:
                            dt = pd.Timestamp(date_val)
                        except Exception:
                            dt = None
                    
                    if dt is not None:
                        if lang == "pt":
                            day_map = {
                                "Monday": "Segunda-feira", "Tuesday": "Terça-feira", "Wednesday": "Quarta-feira",
                                "Thursday": "Quinta-feira", "Friday": "Sexta-feira", "Saturday": "Sábado", "Sunday": "Domingo"
                            }
                            month_map = {
                                "Jan": "Jan", "Feb": "Fev", "Mar": "Mar", "Apr": "Abr", "May": "Mai", "Jun": "Jun",
                                "Jul": "Jul", "Aug": "Ago", "Sep": "Set", "Oct": "Out", "Nov": "Nov", "Dec": "Dez"
                            }
                            day_en = dt.strftime("%A").strip()
                            month_en = dt.strftime("%b").strip()
                            day_pt = day_map.get(day_en, day_map.get(day_en.title(), day_en))
                            month_pt = month_map.get(month_en, month_map.get(month_en.title(), month_en))
                            
                            if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and pd.isna(nr.get("Time (Lisbon)", None)):
                                next_race_date = f"{day_pt}, {dt.day} {month_pt}"
                            else:
                                next_race_date = f"{day_pt}, {dt.day} {month_pt} · {dt.strftime('%H:%M')}"
                        else:
                            if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and pd.isna(nr.get("Time (Lisbon)", None)):
                                next_race_date = dt.strftime("%A, %d %b")
                            else:
                                next_race_date = dt.strftime("%A, %d %b · %H:%M")
                    else:
                        next_race_date = str(date_val)
                next_race_circuit_svg = CIRCUIT_SVG_MAP.get(next_race_name, "")

    # Build Next Race card HTML
    circuit_img = ""
    if next_race_circuit_svg:
        circuit_img = f'<img src="{next_race_circuit_svg}" style="width:100%;max-width:200px;height:auto;opacity:0.85;margin:0.5rem auto;display:block; filter: drop-shadow(0 0 4px rgba(255,255,255,0.2));" />'

    next_race_bg_b64 = _get_track_bg_b64(next_race_name)
    bg_style = ""
    bg_title_style = ""
    if next_race_bg_b64:
        bg_style = f"background: linear-gradient(to bottom, rgba(15,15,18,0.4) 0%, rgba(15,15,18,0.95) 100%), url('{next_race_bg_b64}'); background-size: cover; background-position: center;"
        bg_title_style = "border-bottom:none; color:#ddd; text-shadow: 1px 1px 3px rgba(0,0,0,0.8);"

    next_race_card_html = f"""
    <div style="text-align:center; padding: 0.5rem 0;">
        <h2 style="margin:0; font-size:1.3rem; letter-spacing:2px; font-weight:800; text-shadow: 1px 1px 3px rgba(0,0,0,0.8);">{_tr_gp(lang, next_race_name).upper()} {next_race_flag_img}</h2>
        {circuit_img}
        <div style="text-align:left; padding: 0.5rem 1rem 0 1rem; font-size:0.78rem; color:#aaa; text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>📅&nbsp; {_tr(lang, 'date')}</span>
                <span style="color:#fff;font-weight:600;">{next_race_date}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>🏁&nbsp; {_tr(lang, 'race_length')}</span>
                <span style="color:#fff;font-weight:600;">100%</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>☀️&nbsp; {_tr(lang, 'weather')}</span>
                <span style="color:#fff;font-weight:600;">{_tr(lang, 'sunny_dry')}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;">
                <span>🎮&nbsp; {_tr(lang, 'assists')}</span>
                <span style="color:#fff;font-weight:600;">{_tr(lang, 'league_rules')}</span>
            </div>
        </div>
    </div>
    """

    # 3.5 CHAMPIONSHIP MATHS
    def _build_math_section(title, df, is_team=False):
        if df.empty or len(df) < 2: return ""
        p1_pts = int(df.iloc[0]["Points"])
        p1_name = str(df.iloc[0]["Team"] if is_team else df.iloc[0]["Driver"])
        p2_pts = int(df.iloc[1]["Points"])
        p2_name = str(df.iloc[1]["Team"] if is_team else df.iloc[1]["Driver"])
        if not is_team:
            p1_name = f"{p1_name} ⭐" if p1_name == reigning_champ else p1_name
            p2_name = f"{p2_name} ⭐" if p2_name == reigning_champ else p2_name
        gap = p1_pts - p2_pts
        
        cal_league = get_calendar_for_league(calendar_raw, meta)
        total_races = int(cal_league["Round"].nunique()) if not cal_league.empty and "Round" in cal_league.columns else None
        rounds_done = int(latest_gp["Round"].nunique()) if not latest_gp.empty else 0
        races_left = (total_races - rounds_done) if (total_races and total_races > rounds_done) else 0
        
        if is_team:
            max_pts_per_race = 43.0
        else:
            max_pts_per_race = 25.0

        max_available = int(races_left * max_pts_per_race)
        magic_number = p2_pts + max_available - p1_pts + 1
        
        p3_name, magic_p2 = "", None
        if len(df) > 2:
            p3_pts = int(df.iloc[2]["Points"])
            p3_name = str(df.iloc[2]["Team"] if is_team else df.iloc[2]["Driver"])
            magic_p2 = p3_pts + max_available - p2_pts + 1
            
        magic_p3 = None
        if len(df) > 3:
            p4_pts = int(df.iloc[3]["Points"])
            magic_p3 = p4_pts + max_available - p3_pts + 1

        is_decided = p2_pts + max_available < p1_pts
        
        card_cls = "p-maths-card " + ("p-maths-closed" if is_decided else "p-maths-open")
        title_str = _tr(lang, title)
        verdict = f"{title_str.upper()} {(_tr(lang, 'decided').upper() if is_decided else _tr(lang, 'is_still_open').upper())}"
        
        finish_line = p2_pts + max_available
        w_p1 = min(100, (p1_pts / finish_line * 100)) if finish_line > 0 else 0
        w_p2 = min(100, (p2_pts / finish_line * 100)) if finish_line > 0 else 0
        
        leads_word = _tr(lang, "leads")
        by_word = _tr(lang, "by")
        pts_word = _tr(lang, "pts")
        finish_line_label = _tr(lang, "finish_line")

        details = f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0; border-bottom:1px solid rgba(255,255,255,0.1);'><span>{_tr(lang, 'points_still_open')}</span><span style='color:#fff;font-weight:600;'>{max_available}</span></div>"
        details += f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0; border-bottom:1px solid rgba(255,255,255,0.1);'><span>{_tr(lang, 'races_left')}</span><span style='color:#fff;font-weight:600;'>{races_left}</span></div>"
        if not is_decided and races_left > 0:
            magic_label_p1 = _tr(lang, 'magic_no_p1').format(p1_name=p1_name)
            details += f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0; border-bottom:1px solid rgba(255,255,255,0.1);'><span>{magic_label_p1}</span><span style='color:#fff;font-weight:600;'>{magic_number}</span></div>"
            if magic_number <= max_pts_per_race:
                clinch_text = _tr(lang, 'match_point').format(p1_name=p1_name, magic_number=magic_number)
                details += f"<div class='p-maths-clinch'>{clinch_text}</div>"
        
        if races_left > 0:
            if magic_p2 is not None:
                magic_label_p2 = _tr(lang, 'magic_no_p2').format(p2_name=p2_name)
                details += f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0; border-bottom:1px solid rgba(255,255,255,0.1);'><span>{magic_label_p2}</span><span style='color:#fff;font-weight:600;'>{magic_p2}</span></div>"
            if magic_p3 is not None and len(df) > 2:
                magic_label_p3 = _tr(lang, 'magic_no_p3').format(p3_name=p3_name)
                details += f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0; border-bottom:1px solid rgba(255,255,255,0.1);'><span>{magic_label_p3}</span><span style='color:#fff;font-weight:600;'>{magic_p3}</span></div>"
        
        return f"""
        <div class="{card_cls}" style="margin-bottom:0.8rem; padding:1rem;">
            <div style="font-size:0.9rem; font-weight:800; margin-bottom:0.3rem; z-index:5; position:relative;">{verdict}</div>
            <div style="color:#aaa; font-size:0.75rem; margin-bottom:0.5rem; z-index:5; position:relative;">
                <span style="color:#fff;font-weight:700;">{p1_name}</span> {leads_word} <span style="color:#fff;font-weight:700;">{p2_name}</span> {by_word} <b style="color:#E10600">{gap} {pts_word}</b>
            </div>
            
            <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:#888; margin-bottom:2px; z-index:5; position:relative;">
                <span>0</span>
                <span>{finish_line_label}: {finish_line} {pts_word}</span>
            </div>
            <div class="p-prog-wrap" style="z-index:5;">
                <div class="p-prog-bar1" style="width:{w_p1}%;"></div>
                <div class="p-prog-bar2" style="width:{w_p2}%;"></div>
                <div class="p-prog-finish" title="{finish_line_label} ({p2_name} + {_tr(lang, 'points_still_open')})"></div>
            </div>
            <div style="display:flex; gap:10px; font-size:0.65rem; color:#888; margin-top:4px; z-index:5; position:relative; margin-bottom:10px;">
                <span style="display:flex; align-items:center; gap:3px;"><span style="display:inline-block; width:8px; height:8px; background:#58a6ff; border-radius:2px;"></span>{p1_name} ({p1_pts})</span>
                <span style="display:flex; align-items:center; gap:3px;"><span style="display:inline-block; width:8px; height:8px; background:rgba(225,6,0,0.7); border-radius:2px;"></span>{p2_name} ({p2_pts})</span>
            </div>
            
            <div style="font-size:0.7rem; color:#aaa; margin-top:0.5rem; z-index:5; position:relative;">
                {details}
            </div>
        </div>
        """

    maths_html = ""
    if not st_tbl_latest.empty and len(st_tbl_latest) >= 2:
        maths_html += _build_math_section("drivers_title", st_tbl_latest, is_team=False)
    if "team_st" in locals() and not team_st.empty and len(team_st) >= 2:
        maths_html += _build_math_section("constructors_title", team_st, is_team=True)


    # 3.8 TEAMMATE BATTLE CHART
    import plotly.express as px
    team_chart_html = ""
    team_chart_extra_html = ""
    
    target_drivers = ["TomasRodri21", "Polingua", "Fatacuida"]
    target_teams = [driver_team.get(d) for d in target_drivers if d in driver_team]
    target_teams = [t for t in target_teams if t]
    
    duel_rows = []
    for _, row in st_tbl_latest.iterrows():
        drv = str(row.get("Driver", ""))
        disp_drv = f"{drv} ⭐" if drv == reigning_champ else drv
        tm = driver_team.get(drv, "")
        pts = int(row.get("Points", 0))
        if tm:
            duel_rows.append({"Driver": disp_drv, "Team": tm, "Points": pts})
            
    if duel_rows:
        duel_df = pd.DataFrame(duel_rows)
        if not target_teams and not duel_df.empty:
            top_teams = duel_df.groupby("Team")["Points"].sum().sort_values(ascending=False).head(3).index.tolist()
            target_teams = top_teams
        teams_with_2 = duel_df.groupby("Team").filter(lambda x: len(x) >= 2)["Team"].unique()
        plot_duel = duel_df[duel_df["Team"].isin(teams_with_2)].copy()
        
        if not plot_duel.empty:
            max_pts = plot_duel["Points"].max() * 1.05 if not plot_duel.empty else 100
            def _make_team_chart(df, height=250, use_cdn=True):
                fig = px.bar(
                    df.sort_values(["Team","Points"], ascending=[True,False]),
                    x="Points", y="Driver", color="Team",
                    orientation="h",
                    color_discrete_sequence=["#E10600", "#58a6ff", "#f5c518", "#2ecc71", "#e67e22", "#9b59b6", "#1abc9c", "#34495e", "#e74c3c", "#3498db"],
                    template="plotly_dark"
                )
                fig.update_layout(
                    height=height, 
                    margin=dict(l=10, r=20, t=10, b=10),
                    showlegend=False,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(range=[0, max_pts], showgrid=True, gridcolor='rgba(255,255,255,0.1)', color='#aaa', title=''),
                    yaxis=dict(color='#ccc', title='')
                )
                return fig.to_html(full_html=False, include_plotlyjs='cdn' if use_cdn else False, config={'displayModeBar': False})

            plot_top = plot_duel[plot_duel["Team"].isin(target_teams)].copy()
            if not plot_top.empty:
                team_chart_html = _make_team_chart(plot_top, height=200, use_cdn=True)
                
            plot_extra = plot_duel[~plot_duel["Team"].isin(target_teams)].copy()
            if not plot_extra.empty:
                team_chart_extra_html = _make_team_chart(plot_extra, height=max(200, len(plot_extra)*28), use_cdn=False)

    # 4. LEAGUE STATISTICS
    stats_html = ""
    if not st_tbl_latest.empty:
        wins_df = st_tbl_latest.sort_values("Wins", ascending=False).head(3).to_dict('records')
        pod_df = st_tbl_latest.sort_values("Podiums", ascending=False).head(3).to_dict('records')
        avg_df = st_tbl_latest[st_tbl_latest["Races"]>0].sort_values("AvgFinish", ascending=True).head(3).to_dict('records')
        
        def _sub_html(rows, col, fmt="int"):
            if len(rows) <= 1:
                return ""
            h = '<div style="margin-top: 0.8rem; font-size: 0.7rem; color: #aaa; text-align: left; padding-top: 0.5rem; border-top: 1px solid #222;">'
            for idx, r in enumerate(rows[1:], start=2):
                v = f"{int(r[col])}" if fmt=="int" else f"{float(r[col]):.1f}"
                disp_d = f"{r['Driver']} ⭐" if r['Driver'] == reigning_champ else r['Driver']
                h += f'<div style="display: flex; justify-content: space-between; padding: 0.15rem 0;"><span>{idx}. {disp_d}</span><span style="color:#fff;font-weight:600;">{v}</span></div>'
            h += '</div>'
            return h

        if wins_df and pod_df and avg_df:
            most_wins = wins_df[0]
            most_podiums = pod_df[0]
            best_avg = avg_df[0]
            
            w_drv = f"{most_wins['Driver']} ⭐" if most_wins['Driver'] == reigning_champ else most_wins['Driver']
            p_drv = f"{most_podiums['Driver']} ⭐" if most_podiums['Driver'] == reigning_champ else most_podiums['Driver']
            a_drv = f"{best_avg['Driver']} ⭐" if best_avg['Driver'] == reigning_champ else best_avg['Driver']
            
            stats_html += f"""
            <div class="p-stat-box">
                <div class="p-stat-icon">🏆</div>
                <div class="p-stat-label">{_tr(lang, 'most_wins')}</div>
                <div class="p-stat-driver">{w_drv}</div>
                <div class="p-stat-val">{int(most_wins['Wins'])}</div>
                {_sub_html(wins_df, 'Wins', 'int')}
            </div>
            <div class="p-stat-box">
                <div class="p-stat-icon">🥈</div>
                <div class="p-stat-label">{_tr(lang, 'most_podiums')}</div>
                <div class="p-stat-driver">{p_drv}</div>
                <div class="p-stat-val">{int(most_podiums['Podiums'])}</div>
                {_sub_html(pod_df, 'Podiums', 'int')}
            </div>
            <div class="p-stat-box">
                <div class="p-stat-icon">🎯</div>
                <div class="p-stat-label">{_tr(lang, 'best_avg_finish')}</div>
                <div class="p-stat-driver">{a_drv}</div>
                <div class="p-stat-val">{float(best_avg['AvgFinish']):.1f}</div>
                {_sub_html(avg_df, 'AvgFinish', 'float')}
            </div>
            """

    # 5. SEASON CALENDAR (show first 8 rows with flags + short track names)
    cal_top_html = ""
    cal_extra_html = ""
    if not calendar_raw.empty:
        cal = get_calendar_for_league(calendar_raw, meta)
        for i, (idx, row) in enumerate(cal.iterrows()):
            rnd = row.get("Round", "-")
            gp_name = str(row.get("GP Name", "-"))
            flag_icon = _flag_img(gp_name, 14)
            short_trk = _tr_track(lang, gp_name, row.get("Circuit"))
            status = str(row.get("Status", "")).lower()

            winner = "–"
            if status == "done" and not latest_gp.empty:
                type_mask = (latest_gp["Type"] == "R") if "Type" in latest_gp.columns else True
                r_gp = latest_gp[(latest_gp["Round"] == rnd) & (latest_gp["Finish Pos"] == 1) & type_mask]
                if not r_gp.empty:
                    winner = r_gp.iloc[0]["Driver"]

            disp_winner = f"{winner} ⭐" if winner == reigning_champ else winner
            status_cls = "status-done" if status == "done" else "status-up"
            if status == "done":
                status_txt = _tr(lang, "completed")
            else:
                date_val = row.get("Date")
                if pd.notna(date_val):
                    try:
                        dt = pd.to_datetime(date_val)
                        status_txt = dt.strftime("%d/%m/%Y")
                    except:
                        status_txt = str(date_val)
                else:
                    status_txt = _tr(lang, "upcoming")
            row_html = f"""
            <div class="p-cal-row">
                <div class="p-cal-rnd">{rnd}</div>
                <div class="p-cal-track">{flag_icon} {short_trk}</div>
                <div class="p-cal-winner">{disp_winner}</div>
                <div class="p-cal-status {status_cls}">{status_txt}</div>
            </div>
            """
            if i < 8:
                cal_top_html += row_html
            else:
                cal_extra_html += row_html

    # 6. DRIVER LINEUP
    drivers_top_html = ""
    drivers_extra_html = ""
    if not st_tbl_latest.empty:
        all_drivers = list(st_tbl_latest.head(20).iterrows())
        for i, (_, drow) in enumerate(all_drivers):
            driver = str(drow["Driver"])
            pos = int(drow["Pos"])
            team = driver_team.get(driver, "")
            badge = _team_badge_html(team, 16)
            color = TEAM_COLORS.get(team, "#555")
            wins = int(drow.get("Wins", 0))
            podiums = int(drow.get("Podiums", 0))
            avg_f = float(drow.get("AvgFinish", 99))
            consist = float(drow.get("Consistency", 5))
            best_finish = 1 if wins > 0 else (2 if podiums > 0 else (int(avg_f) if avg_f < 20 else "-"))
            if lang == "pt":
                best_str = f"{best_finish}º" if isinstance(best_finish, int) else "-"
            else:
                best_str = f"{best_finish}{'st' if best_finish==1 else 'nd' if best_finish==2 else 'rd' if best_finish==3 else 'th'}" if isinstance(best_finish, int) else "-"
            style = _driving_style(wins, podiums, avg_f, consist)
            style_localized = _tr(lang, f"style_{style}")

            helmet_b64 = _get_helmet_b64(driver, team)
            helmet_html = f'<img src="{helmet_b64}" class="p-helmet-img" />' if helmet_b64 else '<div class="p-helmet-icon">🪖</div>'

            disp_driver = f"{driver} ⭐" if driver == reigning_champ else driver
            card = f"""
            <div class="p-driver-card-v2">
                <div class="p-helmet-area" style="background: linear-gradient(135deg, {color}33 0%, #0a0a0f 60%);">
                    {helmet_html}
                </div>
                <div class="p-drv-name">{disp_driver}</div>
                <div class="p-drv-num">#{pos}</div>
                <div class="p-drv-team">{badge} {team}</div>
                <div class="p-drv-stats">
                    <div class="p-drv-stat"><span class="p-stat-lbl">{_tr(lang, "wins_capital")}</span> <span class="p-stat-v">{wins}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">{_tr(lang, "podiums_capital")}</span> <span class="p-stat-v">{podiums}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">{_tr(lang, "best_finish")}</span> <span class="p-stat-v">{best_str}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">{_tr(lang, "style_label")}</span> <span class="p-stat-v">⚡ {style_localized}</span></div>
                </div>
            </div>
            """
            if i < 4:
                drivers_top_html += card
            else:
                drivers_extra_html += card

    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@400;600;700&family=Inter:wght@400;600;800&display=swap');
    
    html, body {
        margin: 0;
        padding: 0;
        background-color: #0b0b0f;
        overflow-x: hidden;
    }
    
    .puskas-container {
        font-family: 'Inter', sans-serif;
        background-color: #0b0b0f;
        color: #ffffff;
        padding: 0;
        margin: 0;
    }

    .p-grid {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 1rem;
        padding: 1.5rem 2rem;
    }
    .p-grid > div, .p-grid-half > div, .p-grid-2 > div, .p-grid-3 > div {
        min-width: 0;
    }
    .p-card {
        background: #111115;
        border: 1px solid #222;
        border-radius: 8px;
        padding: 1.2rem;
    }
    .p-card-title {
        font-size: 0.8rem;
        font-weight: 800;
        color: #aaa;
        margin-bottom: 1rem;
        border-bottom: 1px solid #333;
        padding-bottom: 0.5rem;
        letter-spacing: 1px;
    }
    
    .p-row {
        display: flex;
        align-items: center;
        border-bottom: 1px solid #222;
        padding: 0.5rem 0;
        font-size: 0.85rem;
    }
    .p-row:last-child { border-bottom: none; }
    .p-col { flex: 0.8; text-align: center; color: #ccc; }
    .p-driver { flex: 3.5; text-align: left; font-weight: 600; color: #fff; display: flex; align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .p-pos { flex: 0.5; font-weight: 800; }
    .p-time { flex: 1.0; text-align: right; padding-right: 0.5rem; color: #ccc; font-variant-numeric: tabular-nums; font-size: 0.7rem; }
    .p-fl { flex: 1.0; text-align: right; padding-right: 0.5rem; color: #ccc; font-variant-numeric: tabular-nums; font-size: 0.7rem; }
    .pos-gold { color: #f1c40f; }
    .pos-silver { color: #bdc3c7; }
    .pos-bronze { color: #cd7f32; }
    .pos-other { color: #555; }
    
    .p-stats-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-top: 1rem;
    }
    .p-stat-box {
        background: #111115;
        border: 1px solid #222;
        border-radius: 6px;
        flex: 1;
        min-width: 120px;
        text-align: center;
        padding: 1rem;
    }
    .p-stat-icon { font-size: 1.5rem; color: #e10600; margin-bottom: 0.5rem; }
    .p-stat-label { font-size: 0.6rem; color: #888; font-weight: 800; letter-spacing: 1px; }
    .p-stat-driver { font-size: 0.9rem; color: #fff; font-weight: 600; margin: 0.2rem 0; }
    .p-stat-val { font-size: 1.2rem; font-weight: 800; color: #fff; }

    .p-grid-2 {
        display: grid;
        grid-template-columns: 1fr 2fr;
        gap: 1rem;
        padding: 0 2rem 1.5rem 2rem;
    }
    .status-done { color: #555; font-size: 0.72rem; }
    .status-up { color: #e10600; font-weight: 600; font-size: 0.72rem; }

    /* Calendar compact rows */
    .p-cal-row {
        display: flex;
        align-items: center;
        border-bottom: 1px solid #1e1e22;
        padding: 0.35rem 0;
        font-size: 0.75rem;
        white-space: nowrap;
    }
    .p-cal-row:last-child { border-bottom: none; }
    .p-cal-rnd { width: 32px; text-align: center; font-weight: 800; color: #666; flex-shrink: 0; }
    .p-cal-track { flex: 2; display: flex; align-items: center; gap: 6px; font-weight: 600; color: #ddd; overflow: hidden; text-overflow: ellipsis; }
    .p-cal-winner { flex: 1.2; text-align: center; color: #aaa; font-size: 0.7rem; overflow: hidden; text-overflow: ellipsis; }
    .p-cal-status { flex: 0.8; text-align: right; font-size: 0.68rem; padding-right: 0.3rem; }
    
    .p-drivers-flex {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.8rem;
        padding-bottom: 0.5rem;
    }
    .p-driver-card-v2 {
        background: #15151a;
        border: 1px solid #2a2a30;
        border-radius: 8px;
        min-width: 140px;
        max-width: 160px;
        flex-shrink: 0;
        overflow: hidden;
    }
    .p-helmet-area {
        height: 90px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-bottom: 1px solid #2a2a30;
        overflow: hidden;
    }
    .p-helmet-img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        object-position: center 30%;
    }
    .p-helmet-icon { font-size: 2.5rem; opacity: 0.7; }
    .p-drv-name { font-weight: 800; font-size: 0.85rem; padding: 0.5rem 0.6rem 0; }
    .p-drv-num { font-size: 0.7rem; color: #666; padding: 0 0.6rem; }
    .p-drv-team { font-size: 0.65rem; color: #888; padding: 0.3rem 0.6rem; display: flex; align-items: center; gap: 4px; border-bottom: 1px solid #222; }
    .p-drv-stats { padding: 0.4rem 0.6rem; }
    .p-drv-stat { display: flex; justify-content: space-between; font-size: 0.6rem; padding: 0.15rem 0; }
    .p-stat-lbl { color: #555; font-weight: 700; letter-spacing: 0.5px; }
    .p-stat-v { color: #ccc; font-weight: 800; }
    .p-drivers-extra {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.8rem;
        padding: 0.8rem 0 0 0;
    }
    .p-btn-outline {
        display: block;
        text-align: center;
        border: 1px solid #e10600;
        color: #e10600;
        font-weight: 800;
        font-size: 0.7rem;
        letter-spacing: 2px;
        padding: 0.5rem;
        margin: 0.8rem;
        border-radius: 4px;
        cursor: pointer;
    }
    
    .p-hof {
        padding: 0 2rem 2rem 2rem;
    }
    .p-hof-grid {
        display: flex;
        gap: 1rem;
    }
    .p-hof-card {
        flex: 1;
        background: #111115;
        border: 1px solid #222;
        border-radius: 6px;
        text-align: center;
        padding: 2rem 1rem;
        color: #888;
        font-size: 0.8rem;
    }

    @keyframes pulse-glow {
        0% { box-shadow: 0 0 5px rgba(46,204,113,0.1); }
        50% { box-shadow: 0 0 15px rgba(46,204,113,0.4); }
        100% { box-shadow: 0 0 5px rgba(46,204,113,0.1); }
    }
    .p-maths-card {
        background: linear-gradient(135deg, #0d2037 0%, #0a0d14 100%);
        border: 1px solid rgba(88,166,255,0.2);
        border-left: 4px solid #58a6ff;
        border-radius: 8px;
        padding: 1.2rem;
        position: relative;
        overflow: hidden;
    }
    .p-maths-open { border-left-color: #2ecc71; background: linear-gradient(135deg, #0d2a1a, #0a0d14); animation: pulse-glow 3s infinite; }
    .p-maths-closed { border-left-color: #E10600; background: linear-gradient(135deg, #1a0a0a, #0a0d14); }
    
    .p-maths-closed::after {
        content: "🏆";
        position: absolute;
        top: -30px;
        right: -10px;
        font-size: 8rem;
        opacity: 0.03;
        transform: rotate(15deg);
        pointer-events: none;
    }

    .p-prog-wrap {
        width: 100%;
        height: 8px;
        background: #222;
        border-radius: 4px;
        margin: 10px 0;
        position: relative;
    }
    .p-prog-bar1 {
        height: 100%;
        background: #58a6ff;
        border-radius: 4px;
        position: absolute;
        left: 0;
        top: 0;
        z-index: 2;
    }
    .p-prog-bar2 {
        height: 100%;
        background: rgba(225,6,0,0.7);
        border-radius: 4px;
        position: absolute;
        left: 0;
        top: 0;
        z-index: 1;
    }
    .p-prog-finish {
        position: absolute;
        right: 0;
        top: -4px;
        bottom: -4px;
        width: 2px;
        background: #fff;
        z-index: 3;
    }
    .p-maths-clinch {
        color: #f5c518;
        font-size: 0.75rem;
        font-weight: 800;
        animation: pulse-glow 2s infinite;
        text-align: center;
        margin-top: 0.5rem;
        letter-spacing: 0.5px;
    }
    .p-grid-half {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
        padding: 0 2rem 1.5rem 2rem;
    }
    .p-grid-3 {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 1rem;
        padding: 0 2rem 1.5rem 2rem;
    }
    
    @media (max-width: 900px) {
        .puskas-container { margin: -1rem; }
        .p-grid, .p-grid-2, .p-grid-half, .p-grid-3 { grid-template-columns: 1fr; padding: 1rem; }
        .p-hof-grid { flex-direction: column; }
        .p-hof { padding: 0 1rem 1rem 1rem; }
        .p-stats-grid { flex-direction: column; }
        .p-col { font-size: 0.75rem; }
        .p-driver { font-size: 0.8rem; }
    }
    </style>
    """

    def _hof_sub_list(items, limit=5, stacked=False):
        if len(items) <= 1:
            return ""
        h = '<div style="margin-top: 0.8rem; font-size: 0.7rem; color: #aaa; text-align: left; padding-top: 0.5rem; border-top: 1px solid #222;">'
        for i, item in enumerate(items[1:limit], start=2):
            if stacked:
                h += f'<div style="padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);"><div>{i}. {item[0]}</div><div style="color:#fff;font-weight:600;font-size:0.65rem;margin-top:0.1rem;">{item[1]}</div></div>'
            else:
                h += f'<div style="display: flex; justify-content: space-between; padding: 0.15rem 0;"><span>{i}. {item[0]}</span><span style="color:#fff;font-weight:600;">{item[1]}</span></div>'
        h += '</div>'
        return h

    coming_soon_lbl = _tr(lang, "Coming soon")
    champ_name = coming_soon_lbl
    dom_name = coming_soon_lbl
    best_race = coming_soon_lbl
    funny_crash = coming_soon_lbl
    
    if base_all is not None and not base_all.empty:
        df_hof = base_all.dropna(subset=['Driver', 'Finish Pos', 'Points']).copy()
        
        # Exclude ongoing seasons for championships
        try:
            ongoing_seasons = set()
            if calendar_raw is not None and not calendar_raw.empty:
                upcoming_leagues = calendar_raw[calendar_raw['Status'].astype(str).str.lower() == 'upcoming']['League Name'].dropna().unique().tolist()
                if upcoming_leagues:
                    standings_seasons = base_all[['SeasonLabel', 'League Name']].drop_duplicates().values.tolist()
                    for label, league in standings_seasons:
                        st_gps = set(base_all[(base_all['SeasonLabel'] == label) & (base_all['League Name'] == league) & (~base_all['IsSeasonFinal'])]['GP Name'].dropna().unique())
                        for ul in upcoming_leagues:
                            if str(ul).strip().lower() == str(league).strip().lower():
                                ongoing_seasons.add(label)
                                break
                            cal_gps = set(calendar_raw[calendar_raw['League Name'] == ul]['GP Name'].dropna().unique())
                            if cal_gps and st_gps and st_gps.issubset(cal_gps):
                                ongoing_seasons.add(label)
                                break
            df_hof_finished = df_hof[~df_hof["SeasonLabel"].isin(ongoing_seasons)].copy()
        except Exception:
            df_hof_finished = df_hof.copy()

        if not df_hof_finished.empty:
            # Match All-time titles calculation (group by SeasonLabel)
            d_champs = df_hof_finished.groupby(['SeasonLabel', 'Driver'], as_index=False)['Points'].sum()
            d_champs = d_champs.sort_values(['SeasonLabel', 'Points'], ascending=[True, False])
            champs = d_champs.groupby('SeasonLabel').head(1)
            most_champs = champs.groupby('Driver').size().sort_values(ascending=False)
            if not most_champs.empty:
                champs_items = [(idx, val) for idx, val in zip(most_champs.index, most_champs.values)]
                titles_lbl = _tr(lang, "titles_plural") if champs_items[0][1] != 1 else _tr(lang, "title_singular")
                champ_name = f"<span style='color:#fff;font-weight:800;font-size:1.1rem;'>{champs_items[0][0]}</span><br><span style='font-size:0.75rem;color:#E10600;font-weight:700;'>{champs_items[0][1]} {titles_lbl}</span>{_hof_sub_list(champs_items)}"
            
            # Most Dominant Season
            dom_candidates = []
            for _, c in champs.iterrows():
                season = c['SeasonLabel']
                driver = c['Driver']
                points = c['Points']
                
                season_data = df_hof[df_hof['SeasonLabel'] == season]
                total_races = season_data['Round'].nunique()
                if total_races == 0: total_races = season_data['GP Name'].nunique()
                
                driver_points = season_data.groupby('Driver')['Points'].sum().sort_values(ascending=False)
                p2_points = driver_points.iloc[1] if len(driver_points) > 1 else 0
                
                gap_score = int(points - p2_points)
                
                dom_candidates.append({
                    'Driver': driver,
                    'SeasonLabel': season,
                    'Score': gap_score
                })
 
            if dom_candidates:
                dom_df = pd.DataFrame(dom_candidates).sort_values('Score', ascending=False)
                def trunc(name): return str(name)[:15] + "..." if len(str(name)) > 15 else str(name)
                dom_items = [(r['Driver'], f"{int(r['Score'])}{_tr(lang, 'pts_gap_suffix')} ({trunc(r['SeasonLabel'])})") for _, r in dom_df.iterrows()]
                dom_name = f"<span style='color:#fff;font-weight:800;font-size:1.1rem;'>{dom_items[0][0]}</span><br><span style='font-size:0.75rem;color:#E10600;font-weight:700;'>{dom_items[0][1]}</span>{_hof_sub_list(dom_items, stacked=True)}"
 
            wins_df = df_hof[(df_hof['Finish Pos'] == 1) & (~df_hof['IsSeasonFinal'])]
            if not wins_df.empty:
                
                all_time_wins = wins_df.groupby('Driver').size().sort_values(ascending=False)
                if not all_time_wins.empty:
                    wins_items = [(idx, val) for idx, val in zip(all_time_wins.index, all_time_wins.values)]
                    wins_lbl = _tr(lang, "wins_plural") if wins_items[0][1] != 1 else _tr(lang, "wins")
                    best_race = f"<span style='color:#fff;font-weight:800;font-size:1.1rem;'>{wins_items[0][0]}</span><br><span style='font-size:0.75rem;color:#E10600;font-weight:700;'>{wins_items[0][1]} {wins_lbl}</span>{_hof_sub_list(wins_items)}"
                
            pod_df = df_hof[(df_hof['Finish Pos'] <= 3) & (~df_hof['IsSeasonFinal'])]
            if not pod_df.empty:
                all_time_pod = pod_df.groupby('Driver').size().sort_values(ascending=False)
                if not all_time_pod.empty:
                    pod_items = [(idx, val) for idx, val in zip(all_time_pod.index, all_time_pod.values)]
                    pods_lbl = _tr(lang, "podiums_plural") if pod_items[0][1] != 1 else _tr(lang, "podiums")
                    funny_crash = f"<span style='color:#fff;font-weight:800;font-size:1.1rem;'>{pod_items[0][0]}</span><br><span style='font-size:0.75rem;color:#E10600;font-weight:700;'>{pod_items[0][1]} {pods_lbl}</span>{_hof_sub_list(pod_items)}"


    hero_html = render_puskas_hero(meta, calendar_raw, lang=lang)

    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>F1 Dashboard</title>
    </head>
    <body>
    {css}
    <div class="puskas-container">
        {hero_html}
        <!-- ROW 1 -->
        <div class="p-grid">
            <!-- STANDINGS -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "drivers_championship_standings")}</div>
                <h3 style="margin:0 0 0.8rem 0;font-size:1.1rem;letter-spacing:1px;text-transform:uppercase;">{meta.get("League Name", "")}</h3>
                <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                    <div class="p-col p-pos">{_tr(lang, "pos")}</div>
                    <div class="p-col p-driver">{_tr(lang, "driver")}</div>
                    <div class="p-col p-pts">{_tr(lang, "points")}</div>
                    <div class="p-col p-wins">{_tr(lang, "wins")}</div>
                    <div class="p-col p-gap">{_tr(lang, "gap")}</div>
                </div>
                {standings_top_html}
                <div id="standings-extra" style="display:none;">
                    {standings_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-standings">{_tr(lang, "full_standings")}</div>
            </div>

            <!-- LATEST RACE -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "latest_race")}<span style="float:right;color:#555;">{_tr(lang, "round_label")} {latest_round}</span></div>
                <h3 style="margin:0 0 0.8rem 0;font-size:1.1rem;letter-spacing:1px;">{f"{_tr(lang, 'grand_prix').upper()} - {latest_race_name.upper().replace(' GP','')}" if lang != "en" else latest_race_name.upper().replace(' GP',' GRAND PRIX')} {latest_flag_img}</h3>
                {latest_race_card_content}
            </div>

            <!-- NEXT RACE -->
            <div class="p-card" style="{bg_style}">
                <div class="p-card-title" style="{bg_title_style}">{_tr(lang, "next_race")}</div>
                {next_race_card_html}
            </div>
        </div>

        <!-- ROW 2: CONSTRUCTORS & MATHS & CHART -->
        <div class="p-grid-3">
            <!-- CONSTRUCTORS STANDINGS -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "constructors_standings")}</div>
                <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                    <div class="p-col p-pos">{_tr(lang, "pos")}</div>
                    <div class="p-col p-driver">{_tr(lang, "team")}</div>
                    <div class="p-col p-pts">{_tr(lang, "points")}</div>
                    <div class="p-col p-wins">{_tr(lang, "wins")}</div>
                    <div class="p-col p-gap">{_tr(lang, "gap")}</div>
                </div>
                {c_standings_top_html}
                <div id="c-standings-extra" style="display:none;">
                    {c_standings_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-c-standings">{_tr(lang, "full_standings")}</div>
            </div>
            
            <!-- TEAMMATE BATTLE CHART -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "teammate_battle")}</div>
                <div id="team-chart-top">
                    {team_chart_html}
                </div>
                <div id="team-chart-extra" style="display:none; margin-top: 1rem; border-top: 1px solid #333; padding-top: 1rem;">
                    {team_chart_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-team-chart">{_tr(lang, "full_list")}</div>
            </div>

            <!-- CHAMPIONSHIP MATHS -->
            <div>
                {maths_html}
            </div>
        </div>

        <!-- ROW 2.5: LEAGUE STATS -->
        <div style="padding: 0 2rem;">
            <div class="p-card-title" style="margin-bottom:0;">{_tr(lang, "league_statistics")}</div>
            <div class="p-stats-grid">
                {stats_html}
            </div>
        </div>
        <br>

        <!-- ROW 3 -->
        <div class="p-grid-2">
            <!-- CALENDAR -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "season_calendar")}</div>
                <div class="p-cal-row" style="color:#555; font-size:0.6rem; font-weight:800; border-bottom: 1px solid #333;">
                    <div class="p-cal-rnd">{_tr(lang, "rnd")}</div>
                    <div class="p-cal-track">{_tr(lang, "track")}</div>
                    <div class="p-cal-winner">{_tr(lang, "winner")}</div>
                    <div class="p-cal-status">{_tr(lang, "status")}</div>
                </div>
                {cal_top_html}
                <div id="cal-extra" style="display:none;">
                    {cal_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-calendar">{_tr(lang, "full_calendar")}</div>
            </div>

            <!-- DRIVERS -->
            <div class="p-card">
                <div class="p-card-title">{_tr(lang, "driver_lineup")}</div>
                <div class="p-drivers-flex">
                    {drivers_top_html}
                </div>
                <div class="p-drivers-flex" id="drivers-extra" style="display:none;">
                    {drivers_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-all-drivers">{_tr(lang, "all_drivers")}</div>
                <script>
                (function() {{
                    function resizeIframe() {{
                        var h = document.documentElement.scrollHeight;
                        var container = document.querySelector('.puskas-container');
                        if (container) h = container.scrollHeight;
                        try {{
                            window.parent.postMessage({{
                                isStreamlitMessage: true,
                                type: 'streamlit:setFrameHeight',
                                height: h + 50
                            }}, '*');
                        }} catch(e) {{}}
                        try {{
                            if (window.frameElement) {{
                                window.frameElement.style.height = (h + 50) + 'px';
                            }}
                        }} catch(e) {{}}
                    }}
                    
                    function switchLatestRaceView(view) {{
                        var views = ['race', 'sprint', 'weekend'];
                        views.forEach(function(v) {{
                            var el = document.getElementById('latest-race-view-' + v);
                            var tab = document.getElementById('tab-btn-' + v);
                            if (el) {{
                                if (v === view) {{
                                    el.style.display = 'block';
                                    if (tab) {{
                                        tab.style.background = '#e10600';
                                        tab.style.color = '#fff';
                                    }}
                                }} else {{
                                    el.style.display = 'none';
                                    if (tab) {{
                                        tab.style.background = '#222';
                                        tab.style.color = '#aaa';
                                    }}
                                }}
                            }}
                        }});
                        setTimeout(resizeIframe, 50);
                    }}
                    window.switchLatestRaceView = switchLatestRaceView;
                    
                    function setupToggle(btnId, elId, showText, hideText, displayStyle) {{
                        var btn = document.getElementById(btnId);
                        var el  = document.getElementById(elId);
                        if (btn && el) {{
                            btn.addEventListener('click', function(e) {{
                                e.preventDefault();
                                if (el.style.display === 'none' || el.style.display === '') {{
                                    el.style.display = displayStyle || 'block';
                                    btn.textContent = hideText;
                                }} else {{
                                    el.style.display = 'none';
                                    btn.textContent = showText;
                                }}
                                setTimeout(resizeIframe, 50);
                            }});
                        }}
                    }}
                    
                    setupToggle('btn-full-standings',  'standings-extra',  '{_js_escape(_tr(lang, "full_standings"))}',  '{_js_escape(_tr(lang, "hide_standings"))}',  'block');
                    setupToggle('btn-full-c-standings','c-standings-extra','{_js_escape(_tr(lang, "full_standings"))}',  '{_js_escape(_tr(lang, "hide_standings"))}',  'block');
                    setupToggle('btn-full-team-chart', 'team-chart-extra', '{_js_escape(_tr(lang, "full_list"))}',       '{_js_escape(_tr(lang, "hide_list"))}',       'block');
                    setupToggle('btn-full-results',    'race-extra',       '{_js_escape(_tr(lang, "full_results"))}',    '{_js_escape(_tr(lang, "hide_results"))}',    'block');
                    setupToggle('btn-full-calendar',   'cal-extra',        '{_js_escape(_tr(lang, "full_calendar"))}',   '{_js_escape(_tr(lang, "hide_calendar"))}',   'block');
                    setupToggle('btn-all-drivers',     'drivers-extra',    '{_js_escape(_tr(lang, "all_drivers"))}',     '{_js_escape(_tr(lang, "hide_drivers"))}',    'flex');
                    
                    // Initial resize
                    setTimeout(resizeIframe, 500);
                    
                    // Use ResizeObserver for accurate and safe resizing without infinite loops
                    try {{
                        var container = document.querySelector('.puskas-container');
                        if (container && window.ResizeObserver) {{
                            new ResizeObserver(function() {{
                                resizeIframe();
                            }}).observe(container);
                        }} else {{
                            window.addEventListener('resize', function() {{ setTimeout(resizeIframe, 500); }});
                        }}
                    }} catch(e) {{}}

                    // Attach event listeners to hero buttons (which live in the parent window)
                    setTimeout(function() {{
                        try {{
                            var btn1 = document.getElementById('btn-hero-circuits');
                            if (btn1) {{
                                btn1.addEventListener('click', function() {{
                                    try {{
                                        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                                        if (tabs.length > 2) tabs[2].click();
                                    }} catch(e) {{}}
                                }});
                            }}
                            var btn2 = document.getElementById('btn-hero-gpstats');
                            if (btn2) {{
                                btn2.addEventListener('click', function() {{
                                    try {{
                                        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                                        if (tabs.length > 1) tabs[1].click();
                                    }} catch(e) {{}}
                                }});
                            }}
                        }} catch(e) {{}}
                    }}, 200);

                    // Dynamic Countdown Timer (targets Lisbon 7 AM time)
                    var targetIso = "{next_race_target_iso}";
                    if (targetIso) {{
                        var targetDate = new Date(targetIso).getTime();
                        function updateCountdown() {{
                            try {{
                                var pDoc = document;
                                var daysEl = pDoc.getElementById("cd-days");
                                var hoursEl = pDoc.getElementById("cd-hours");
                                var minutesEl = pDoc.getElementById("cd-minutes");
                                var secondsEl = pDoc.getElementById("cd-seconds");
                                var textEl = pDoc.getElementById("cd-text");
                                
                                var now = new Date().getTime();
                                var diff = targetDate - now;
                                
                                if (diff <= 0) {{
                                    if (daysEl) daysEl.textContent = "00";
                                    if (hoursEl) hoursEl.textContent = "00";
                                    if (minutesEl) minutesEl.textContent = "00";
                                    if (secondsEl) secondsEl.textContent = "00";
                                    if (textEl) textEl.textContent = "{_js_escape(_tr(lang, "race_in_progress"))}";
                                    return;
                                }}
                                
                                var d = Math.floor(diff / (1000 * 60 * 60 * 24));
                                var h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                                var m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                                var s = Math.floor((diff % (1000 * 60)) / 1000);
                                
                                if (daysEl) daysEl.textContent = String(d).padStart(2, '0');
                                if (hoursEl) hoursEl.textContent = String(h).padStart(2, '0');
                                if (minutesEl) minutesEl.textContent = String(m).padStart(2, '0');
                                if (secondsEl) secondsEl.textContent = String(s).padStart(2, '0');
                            }} catch(e) {{}}
                        }}
                        updateCountdown();
                        setInterval(updateCountdown, 1000);
                    }}
                }})();
                </script>
            </div>
        </div>

        <!-- ROW 4: HOF -->
        <div class="p-hof">
            <div class="p-card-title">{_tr(lang, "hall_of_fame")}</div>
            <div class="p-hof-grid">
                <div class="p-hof-card"><div style="color:#aaa;font-weight:800;font-size:0.65rem;letter-spacing:1px;margin-bottom:0.5rem;">{_tr(lang, "most_championships")}</div>{champ_name}</div>
                <div class="p-hof-card"><div style="color:#aaa;font-weight:800;font-size:0.65rem;letter-spacing:1px;margin-bottom:0.5rem;">{_tr(lang, "most_dominant_season")}</div>{dom_name}</div>
                <div class="p-hof-card"><div style="color:#aaa;font-weight:800;font-size:0.65rem;letter-spacing:1px;margin-bottom:0.5rem;">{_tr(lang, "all_time_wins")}</div>{best_race}</div>
                <div class="p-hof-card"><div style="color:#aaa;font-weight:800;font-size:0.65rem;letter-spacing:1px;margin-bottom:0.5rem;">{_tr(lang, "all_time_podiums")}</div>{funny_crash}</div>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return "\n".join(line.lstrip() for line in html.split("\n"))
