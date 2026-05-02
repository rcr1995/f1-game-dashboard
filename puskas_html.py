import pandas as pd
import numpy as np
import base64
from pathlib import Path

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
}

# Custom driver overrides (league-specific players with bespoke helmets)
DRIVER_HELMET_FILE = {
    "TomasRodri21": "tomasrodri21",
    "Fatacuida": "fatacuida",
    "Polingua": "polingua",
}

def _get_helmet_b64(driver: str, team: str) -> str:
    """Return base64 data URI for a driver's helmet, falling back to team."""
    fname = DRIVER_HELMET_FILE.get(driver, TEAM_HELMET_FILE.get(team, ""))
    if not fname:
        return ""
    p = _HELMETS_DIR / f"{fname}.png"
    return get_base64_image(str(p))

_TRACKS_DIR = Path(__file__).parent / "assets" / "tracks"

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


def render_puskas_hero(meta: dict) -> str:
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@400;600;700&family=Inter:wght@400;600;800&display=swap');
    
    .puskas-container {
        font-family: 'Inter', sans-serif;
        background-color: #0b0b0f;
        color: #ffffff;
        padding: 0;
        margin: -1rem -2rem; /* negate streamlit padding */
    }
    
    .p-hero {
        background: linear-gradient(to right, #000000 20%, transparent 100%), 
                    url('""" + _HERO_B64 + """');
        background-color: #1a1a20; /* fallback */
        background-size: cover;
        background-position: center;
        padding: 4rem 2rem;
        border-bottom: 2px solid #e10600;
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
    
    @media (max-width: 768px) {
        .puskas-container { margin: -1rem; }
        .p-hero { padding: 3rem 1rem; }
        .p-hero-title { font-size: 3rem; }
    }
    </style>
    """
    html = f"""
    {css}
    <div class="puskas-container">
        <!-- HERO -->
        <div class="p-hero" style="position: relative;">
            <div class="p-hero-title">F1 PUSKAS<br><span class="red">LEAGUE</span></div>
            <div class="p-hero-sub">Our PS5 F1 league.<br>One competition.<br>No mercy.</div>
            <div class="p-hero-season">SEASON 1 • {meta.get("SeasonLabel", "2025")}</div>
            <div class="p-btn" id="btn-hero-alltime" style="cursor: pointer;">ALL-TIME 🏆</div>
            <div class="p-btn dark" id="btn-hero-gpstats" style="cursor: pointer;">GP STATISTICS 🏁</div>
        </div>
    </div>
    """
    return "\n".join(line.lstrip() for line in html.split("\n"))

def render_puskas_dashboard(latest_gp: pd.DataFrame, calendar_raw: pd.DataFrame, st_tbl_latest: pd.DataFrame, meta: dict) -> str:

    # ── Build driver→team lookup from latest GP data ──
    driver_team = {}
    if not latest_gp.empty:
        for _, row in latest_gp.drop_duplicates(subset=["Driver"]).iterrows():
            driver_team[str(row["Driver"])] = str(row.get("Team", ""))

    # 1. CHAMPIONSHIP STANDINGS – top 6 visible, rest toggled
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
        
        row_html = f"""
        <div class="p-row">
            <div class="p-col p-pos"><span class="{color_class}">{pos}</span></div>
            <div class="p-col p-driver">{badge}{driver}</div>
            <div class="p-col p-pts">{points}</div>
            <div class="p-col p-wins">{wins}</div>
            <div class="p-col p-gap">{gap}</div>
        </div>
        """
        if i < 6:
            standings_top_html += row_html
        else:
            standings_extra_html += row_html

    # 2. LATEST RACE – top 6 visible, rest toggled
    race_top_html = ""
    race_extra_html = ""
    latest_race_name = "TBD"
    latest_round = "-"
    latest_flag_img = ""
    if not latest_gp.empty:
        last_r = int(latest_gp["Round"].max())
        d0 = latest_gp[(latest_gp["Round"] == last_r) & (~latest_gp["IsSeasonFinal"])]
        if not d0.empty:
            latest_race_name = d0.iloc[0]["GP Name"]
            latest_round = last_r
            latest_flag_img = _flag_img(latest_race_name, 20)
            d_sort = d0.sort_values(["Finish Pos", "Driver"])
            for i, (idx, row) in enumerate(d_sort.iterrows()):
                fpos = int(row["Finish Pos"]) if pd.notna(row["Finish Pos"]) else "-"
                drv = str(row["Driver"])
                pts = int(row["Points"]) if pd.notna(row["Points"]) else 0
                team = str(row.get("Team", ""))
                badge = _team_badge_html(team, 18)
                
                # Format Time and Fastest Lap
                time_val = _format_time(row.get("Time", "-"), mode="time")
                fl_val = _format_time(row.get("Fastest Lap", "-"), mode="fl")

                r_html = f"""
                <div class="p-row">
                    <div class="p-col p-pos">{fpos}</div>
                    <div class="p-col p-driver">{badge}{drv}</div>
                    <div class="p-time">{time_val}</div>
                    <div class="p-fl">{fl_val}</div>
                    <div class="p-col p-pts">{pts}</div>
                </div>
                """
                if i < 6:
                    race_top_html += r_html
                else:
                    race_extra_html += r_html

    # 3. NEXT RACE (with circuit layout, date, race length, weather)
    next_race_name = "TBD"
    next_race_date = "-"
    next_race_flag_img = ""
    next_race_circuit_svg = ""
    if not calendar_raw.empty:
        cal = calendar_raw[calendar_raw["League Name"] == meta.get("League Name", "")]
        if not cal.empty:
            upcoming = cal[cal["Status"].astype(str).str.lower() == "upcoming"]
            if not upcoming.empty:
                nr = upcoming.iloc[0]
                next_race_name = nr.get("GP Name", "TBD")
                next_race_flag_img = _flag_img(next_race_name, 18)
                date_val = nr.get("Date", "")
                if pd.notna(date_val):
                    try:
                        next_race_date = pd.Timestamp(date_val).strftime("%A, %d %b · %H:%M")
                    except:
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
        <h2 style="margin:0; font-size:1.3rem; letter-spacing:2px; font-weight:800; text-shadow: 1px 1px 3px rgba(0,0,0,0.8);">{next_race_name.upper().replace(' GP','')} {next_race_flag_img}</h2>
        {circuit_img}
        <div style="text-align:left; padding: 0.5rem 1rem 0 1rem; font-size:0.78rem; color:#aaa; text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>📅&nbsp; DATE</span>
                <span style="color:#fff;font-weight:600;">{next_race_date}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>🏁&nbsp; RACE LENGTH</span>
                <span style="color:#fff;font-weight:600;">100%</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.1);">
                <span>☀️&nbsp; WEATHER</span>
                <span style="color:#fff;font-weight:600;">Sunny (Dry)</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.3rem 0;">
                <span>🎮&nbsp; ASSISTS</span>
                <span style="color:#fff;font-weight:600;">League Rules</span>
            </div>
        </div>
    </div>
    """

    # 4. LEAGUE STATISTICS
    stats_html = ""
    if not st_tbl_latest.empty:
        most_wins = st_tbl_latest.sort_values("Wins", ascending=False).iloc[0]
        most_podiums = st_tbl_latest.sort_values("Podiums", ascending=False).iloc[0]
        best_avg = st_tbl_latest[st_tbl_latest["Races"]>0].sort_values("AvgFinish", ascending=True).iloc[0]
        
        stats_html += f"""
        <div class="p-stat-box">
            <div class="p-stat-icon">🏆</div>
            <div class="p-stat-label">MOST WINS</div>
            <div class="p-stat-driver">{most_wins['Driver']}</div>
            <div class="p-stat-val">{int(most_wins['Wins'])}</div>
        </div>
        <div class="p-stat-box">
            <div class="p-stat-icon">🥈</div>
            <div class="p-stat-label">MOST PODIUMS</div>
            <div class="p-stat-driver">{most_podiums['Driver']}</div>
            <div class="p-stat-val">{int(most_podiums['Podiums'])}</div>
        </div>
        <div class="p-stat-box">
            <div class="p-stat-icon">🎯</div>
            <div class="p-stat-label">BEST AVG FINISH</div>
            <div class="p-stat-driver">{best_avg['Driver']}</div>
            <div class="p-stat-val">{float(best_avg['AvgFinish']):.1f}</div>
        </div>
        """

    # 5. SEASON CALENDAR (show first 8 rows with flags + short track names)
    cal_top_html = ""
    cal_extra_html = ""
    if not calendar_raw.empty:
        cal = calendar_raw[calendar_raw["League Name"] == meta.get("League Name", "")]
        for i, (idx, row) in enumerate(cal.iterrows()):
            rnd = row.get("Round", "-")
            gp_name = str(row.get("GP Name", "-"))
            flag_icon = _flag_img(gp_name, 14)
            short_trk = GP_SHORT_TRACK.get(gp_name, gp_name.replace(" GP", ""))
            status = str(row.get("Status", "")).lower()

            winner = "–"
            if status == "done" and not latest_gp.empty:
                r_gp = latest_gp[(latest_gp["Round"] == rnd) & (latest_gp["Finish Pos"] == 1)]
                if not r_gp.empty:
                    winner = r_gp.iloc[0]["Driver"]

            status_cls = "status-done" if status == "done" else "status-up"
            status_txt = "Completed" if status == "done" else "Upcoming"
            row_html = f"""
            <div class="p-cal-row">
                <div class="p-cal-rnd">{rnd}</div>
                <div class="p-cal-track">{flag_icon} {short_trk}</div>
                <div class="p-cal-winner">{winner}</div>
                <div class="p-cal-status {status_cls}">{status_txt}</div>
            </div>
            """
            if i < 8:
                cal_top_html += row_html
            else:
                cal_extra_html += row_html

    # 6. DRIVER LINEUP – top 5 always visible, rest toggled by button
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
            best_str = f"{best_finish}{'st' if best_finish==1 else 'nd' if best_finish==2 else 'rd' if best_finish==3 else 'th'}" if isinstance(best_finish, int) else "-"
            style = _driving_style(wins, podiums, avg_f, consist)

            helmet_b64 = _get_helmet_b64(driver, team)
            helmet_html = f'<img src="{helmet_b64}" class="p-helmet-img" />' if helmet_b64 else '<div class="p-helmet-icon">🪖</div>'

            card = f"""
            <div class="p-driver-card-v2">
                <div class="p-helmet-area" style="background: linear-gradient(135deg, {color}33 0%, #0a0a0f 60%);">
                    {helmet_html}
                </div>
                <div class="p-drv-name">{driver}</div>
                <div class="p-drv-num">#{pos}</div>
                <div class="p-drv-team">{badge} {team}</div>
                <div class="p-drv-stats">
                    <div class="p-drv-stat"><span class="p-stat-lbl">WINS</span> <span class="p-stat-v">{wins}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">PODIUMS</span> <span class="p-stat-v">{podiums}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">BEST FINISH</span> <span class="p-stat-v">{best_str}</span></div>
                    <div class="p-drv-stat"><span class="p-stat-lbl">STYLE</span> <span class="p-stat-v">⚡ {style}</span></div>
                </div>
            </div>
            """
            if i < 5:
                drivers_top_html += card
            else:
                drivers_extra_html += card

    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@400;600;700&family=Inter:wght@400;600;800&display=swap');
    
    .puskas-container {
        font-family: 'Inter', sans-serif;
        background-color: #0b0b0f;
        color: #ffffff;
        padding: 0;
        margin: -1rem -2rem; /* negate streamlit padding */
    }

    .p-grid {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 1rem;
        padding: 1.5rem 2rem;
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
        gap: 0.8rem;
        overflow-x: auto;
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
    
    @media (max-width: 900px) {
        .puskas-container { margin: -1rem; }
        .p-grid, .p-grid-2 { grid-template-columns: 1fr; padding: 1rem; }
        .p-hof-grid { flex-direction: column; }
        .p-hof { padding: 0 1rem 1rem 1rem; }
        .p-stats-grid { flex-direction: column; }
        .p-col { font-size: 0.75rem; }
        .p-driver { font-size: 0.8rem; }
    }
    </style>
    """

    html = f"""
    {css}
    <div class="puskas-container">
        <!-- ROW 1 -->
        <div class="p-grid">
            <!-- STANDINGS -->
            <div class="p-card">
                <div class="p-card-title">🏆 CHAMPIONSHIP STANDINGS</div>
                <h3 style="margin:0 0 0.8rem 0;font-size:1.1rem;letter-spacing:1px;text-transform:uppercase;">{meta.get("League Name", "")}</h3>
                <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                    <div class="p-col p-pos">POS</div>
                    <div class="p-col p-driver">DRIVER</div>
                    <div class="p-col p-pts">POINTS</div>
                    <div class="p-col p-wins">WINS</div>
                    <div class="p-col p-gap">GAP</div>
                </div>
                {standings_top_html}
                <div id="standings-extra" style="display:none;">
                    {standings_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-standings">FULL STANDINGS</div>
            </div>

            <!-- LATEST RACE -->
            <div class="p-card">
                <div class="p-card-title">🏁 LATEST RACE<span style="float:right;color:#555;">Round {latest_round}</span></div>
                <h3 style="margin:0 0 0.8rem 0;font-size:1.1rem;letter-spacing:1px;">{latest_race_name.upper().replace(' GP',' GRAND PRIX')} {latest_flag_img}</h3>
                <div class="p-row" style="color:#555; font-size:0.65rem; font-weight:800;">
                    <div class="p-col p-pos">POS</div>
                    <div class="p-col p-driver">DRIVER</div>
                    <div class="p-time">TIME</div>
                    <div class="p-fl">FASTEST LAP</div>
                    <div class="p-col p-pts">POINTS</div>
                </div>
                {race_top_html}
                <div id="race-extra" style="display:none;">
                    {race_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-results">FULL RESULTS</div>
            </div>

            <!-- NEXT RACE -->
            <div class="p-card" style="{bg_style}">
                <div class="p-card-title" style="{bg_title_style}">📅 NEXT RACE</div>
                {next_race_card_html}
            </div>
        </div>

        <!-- ROW 2: LEAGUE STATS -->
        <div style="padding: 0 2rem;">
            <div class="p-card-title" style="margin-bottom:0;">📊 LEAGUE STATISTICS</div>
            <div class="p-stats-grid">
                {stats_html}
            </div>
        </div>
        <br>

        <!-- ROW 3 -->
        <div class="p-grid-2">
            <!-- CALENDAR -->
            <div class="p-card">
                <div class="p-card-title">📅 SEASON CALENDAR</div>
                <div class="p-cal-row" style="color:#555; font-size:0.6rem; font-weight:800; border-bottom: 1px solid #333;">
                    <div class="p-cal-rnd">RND</div>
                    <div class="p-cal-track">TRACK</div>
                    <div class="p-cal-winner">WINNER</div>
                    <div class="p-cal-status">STATUS</div>
                </div>
                {cal_top_html}
                <div id="cal-extra" style="display:none;">
                    {cal_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-full-calendar">FULL CALENDAR</div>
            </div>

            <!-- DRIVERS -->
            <div class="p-card">
                <div class="p-card-title">🏎️ DRIVER LINEUP</div>
                <div class="p-drivers-flex">
                    {drivers_top_html}
                </div>
                <div id="drivers-extra" class="p-drivers-extra" style="display:none;">
                    {drivers_extra_html}
                </div>
                <div class="p-btn-outline" id="btn-all-drivers">ALL DRIVERS</div>
                <script>
                (function() {{
                    function resizeIframe() {{
                        if (window.frameElement) {{
                            window.frameElement.style.height = (document.documentElement.scrollHeight + 50) + 'px';
                        }}
                    }}
                    
                    function setupToggle(btnId, elId, showText, hideText, displayStyle) {{
                        var btn = document.getElementById(btnId);
                        var el  = document.getElementById(elId);
                        if (btn && el) {{
                            btn.addEventListener('click', function() {{
                                if (el.style.display === 'none') {{
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
                    setupToggle('btn-all-drivers',    'drivers-extra',    'ALL DRIVERS',    'HIDE DRIVERS',    'flex');
                    setupToggle('btn-full-standings',  'standings-extra',  'FULL STANDINGS',  'HIDE STANDINGS',  'block');
                    setupToggle('btn-full-results',    'race-extra',       'FULL RESULTS',    'HIDE RESULTS',    'block');
                    setupToggle('btn-full-calendar',   'cal-extra',        'FULL CALENDAR',   'HIDE CALENDAR',   'block');
                    
                    // Initial resize
                    setTimeout(resizeIframe, 500);
                    // Also resize on window resize
                    window.addEventListener('resize', function() {{ setTimeout(resizeIframe, 200); }});

                    // Attach event listeners to hero buttons (which live in the parent window)
                    setTimeout(function() {{
                        var btn1 = window.parent.document.getElementById('btn-hero-alltime');
                        if (btn1) {{
                            btn1.addEventListener('click', function() {{
                                var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                                if (tabs.length > 3) tabs[3].click();
                            }});
                        }}
                        var btn2 = window.parent.document.getElementById('btn-hero-gpstats');
                        if (btn2) {{
                            btn2.addEventListener('click', function() {{
                                var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                                if (tabs.length > 1) tabs[1].click();
                            }});
                        }}
                    }}, 200);
                }})();
                </script>
            </div>
        </div>

        <!-- ROW 4: HOF -->
        <div class="p-hof">
            <div class="p-card-title">🏆 HALL OF FAME</div>
            <div class="p-hof-grid">
                <div class="p-hof-card">SEASON CHAMPIONS<br><br>Coming soon</div>
                <div class="p-hof-card">MOST DOMINANT SEASON<br><br>Coming soon</div>
                <div class="p-hof-card">BEST RACE EVER<br><br>Coming soon</div>
                <div class="p-hof-card">FUNNIEST CRASH<br><br>Coming soon</div>
            </div>
        </div>
    </div>
    """
    return "\n".join(line.lstrip() for line in html.split("\n"))
