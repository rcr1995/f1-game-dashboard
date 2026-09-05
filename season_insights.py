"""Round-by-round points from published event rows, for drivers and constructors."""

from __future__ import annotations

import html
import hashlib
import math

import pandas as pd


def season_points(results: pd.DataFrame, meta: dict, entity: str = "Drivers") -> dict:
    """Preserve Race/Sprint identity, absent results and the workbook's actual points."""
    empty = {"rounds": [], "drivers": [], "events": {}, "points": {}}
    required = {"Game", "SeasonLabel", "League Name", "Driver", "Round", "Type", "Points",
                "IsSeasonFinal", "Finish Pos", "GP Name"}
    if results is None or results.empty or not required.issubset(results.columns):
        return empty
    if entity not in ("Drivers", "Constructors"):
        raise ValueError("Unknown standings type")
    column = "Driver" if entity == "Drivers" else "Team"
    if column not in results:
        return empty
    rows = results.copy()
    for identity_column in ("Game", "SeasonLabel", "League Name"):
        expected = str(meta.get(identity_column, "")).strip()
        if not expected:
            return empty
        rows = rows[rows[identity_column].fillna("").astype(str).str.strip().eq(expected)]
    if "IsSeasonFinal" in rows:
        rows = rows[~rows["IsSeasonFinal"].fillna(False).astype(bool)]
    rows["Type"] = rows["Type"].astype(str).str.strip().str.upper().replace(
        {"RACE": "R", "SPRINT": "SR", "SPRINT RACE": "SR"}
    )
    rows = rows[rows["Type"].isin(["R", "SR"])].copy()
    if rows.empty:
        return empty
    rows["Round"] = pd.to_numeric(rows["Round"], errors="coerce")
    rows["Points"] = pd.to_numeric(rows["Points"], errors="coerce")
    if (rows[["Round", "Points"]].isna().any().any()
            or not rows["Points"].map(math.isfinite).all()
            or (rows["Round"] <= 0).any() or (rows["Round"] % 1 != 0).any()):
        raise ValueError("Invalid round or points in published results")
    rows["Round"] = rows["Round"].astype(int)
    rows["Driver"] = rows["Driver"].fillna("").astype(str).str.strip()
    if rows["Driver"].eq("").any() or rows.duplicated(["Driver", "Round", "Type"]).any():
        raise ValueError("Ambiguous driver results in published event")
    if (rows.groupby("Round")["GP Name"].nunique() > 1).any():
        raise ValueError("More than one Grand Prix assigned to a round")
    rounds = sorted(rows["Round"].unique().tolist())
    events = {rnd: [kind for kind in ("R", "SR")
                    if kind in set(rows.loc[rows["Round"].eq(rnd), "Type"])] for rnd in rounds}
    rows[column] = rows[column].fillna("").astype(str).str.strip()
    if rows[column].eq("").any():
        raise ValueError("Missing entity in published results")
    grouped = rows.groupby([column, "Round", "Type"], as_index=False)["Points"].sum()
    points = {(name, rnd, kind): float(value)
              for name, rnd, kind, value in grouped.itertuples(index=False, name=None)}
    # Team points stay with the team recorded for each event, including transfers.
    import dashboard_core
    ordered = dashboard_core.standings_table(rows, entity=entity)
    drivers = ordered[column].tolist()
    names = {}
    for rnd in rounds:
        gp_names = rows.loc[rows["Round"].eq(rnd), "GP Name"].dropna().unique() if "GP Name" in rows else []
        names[rnd] = str(gp_names[0]) if len(gp_names) == 1 else ""
    return {"rounds": rounds, "drivers": drivers, "events": events, "points": points, "names": names}


def _number(value: float) -> str:
    return f"{value:g}"


def render_season_insights(results: pd.DataFrame, meta: dict, lang: str = "en", *,
                           entity: str = "Drivers", show_details: bool = True) -> str:
    pt = lang == "pt"
    constructors = entity == "Constructors"
    entity_label = ("Construtor" if pt else "Constructor") if constructors else ("Piloto" if pt else "Driver")
    search_label = ("Procurar construtor" if pt else "Find constructor") if constructors else ("Procurar piloto" if pt else "Find driver")
    title = "A época, ronda a ronda" if pt else "The season, round by round"
    section_id = "points-" + hashlib.sha256(repr((meta, entity)).encode()).hexdigest()[:12]
    try:
        model = season_points(results, meta, entity)
    except ValueError:
        return '<section class="si-section"><p>' + (
            "A classificação por ronda requer a correção de resultados ambíguos no Excel."
            if pt else "Round standings require ambiguous results in Excel to be corrected."
        ) + '</p></section>'
    rounds, drivers, events, points = (model[key] for key in ("rounds", "drivers", "events", "points"))
    if not rounds:
        return ""
    esc = lambda value: html.escape(str(value), quote=True)
    totals = {driver: sum(value for (name, _, _), value in points.items() if name == driver)
              for driver in drivers}
    round_total = lambda driver, rnd: sum(points.get((driver, rnd, kind), 0) for kind in events[rnd])
    heading = '<tr><th rowspan="2" scope="col">#</th><th rowspan="2" scope="col">' + entity_label + '</th>'
    subheading = '<tr>'
    for rnd in rounds:
        count = (len(events[rnd]) if show_details else 0) + 1
        heading += f'<th colspan="{count}" scope="colgroup" title="{esc(model["names"][rnd])}">R{rnd} <span>{esc(model["names"][rnd].replace(" GP", ""))}</span></th>'
        for kind in (events[rnd] if show_details else []):
            subheading += '<th scope="col">' + ("Sprint" if kind == "SR" else ("Corrida" if pt else "Race")) + '</th>'
        subheading += '<th class="si-weekend" scope="col">Total</th>'
    heading += '<th rowspan="2" scope="col" class="si-total">' + ("Época" if pt else "Season") + '</th></tr>'
    subheading += '</tr>'
    body = ''
    for rank, driver in enumerate(drivers, 1):
        body += f'<tr data-driver="{esc(driver.casefold())}"><td>{rank:02d}</td><th scope="row">{esc(driver)}</th>'
        for rnd in rounds:
            for kind in (events[rnd] if show_details else []):
                value = points.get((driver, rnd, kind))
                cell = '—' if value is None else _number(value)
                intensity = 0 if value is None else min(max(value / 25, 0), 1)
                body += f'<td style="background:rgba(225,6,0,{intensity * .2:.3f})">{cell}</td>'
            total = _number(round_total(driver, rnd)) if any((driver, rnd, kind) in points for kind in events[rnd]) else '—'
            body += f'<td class="si-weekend">{total}</td>'
        body += f'<td class="si-total">{_number(totals[driver])}</td></tr>'
    foot = '<tr><th colspan="2" scope="row">' + ("Total geral" if pt else "Grand total") + '</th>'
    for rnd in rounds:
        for kind in (events[rnd] if show_details else []):
            foot += '<td>' + _number(sum(points.get((d, rnd, kind), 0) for d in drivers)) + '</td>'
        foot += '<td class="si-weekend">' + _number(sum(round_total(d, rnd) for d in drivers)) + '</td>'
    foot += '<td class="si-total">' + _number(sum(totals.values())) + '</td></tr>'

    return f"""
    <section class="si-section" id="{section_id}" aria-labelledby="{section_id}-heading">
      <div class="si-heading"><div><p class="si-eyebrow"> {'CAMPEONATO' if pt else 'CHAMPIONSHIP'}</p>
      <h2 id="{section_id}-heading">{title}</h2><p>{'Cada ponto conta. Corrida, Sprint e total de cada fim de semana.' if pt else 'Every point counts. Race, Sprint and the total from every weekend.'}</p></div>
      <span class="si-count">{len(rounds)} {'rondas publicadas' if pt else 'published rounds'}</span></div>
      <div class="si-table-tools"><h3>{'Pontos por ronda' if pt else 'Points by round'}</h3>
      <label>{search_label} <input type="search" class="si-search" placeholder="{entity_label}" /></label></div>
      <div class="si-table-scroll" tabindex="0" role="region" aria-label="{esc(title)}">
      <table class="si-table"><caption>{esc(meta.get('Game',''))} · {esc(meta.get('League Name',''))} · {esc(meta.get('SeasonLabel',''))} · {entity_label}</caption>
      <thead>{heading}{subheading}</thead><tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div>
      <p class="si-note">{'Desliza para ver todas as rondas. — = sem resultado publicado; 0 = resultado sem pontos. Os totais usam os pontos do Excel.' if pt else 'Scroll to explore all rounds. — = no published result; 0 = a result with no points. Totals use the points recorded in Excel.'}</p>
      <p class="si-empty" hidden>{'Nenhum resultado encontrado.' if pt else 'No matches found.'}</p>
    </section>
    <script>
    (() => {{
      const section = document.currentScript.previousElementSibling;
      section.querySelector('.si-search').addEventListener('input', event => {{
        const term = event.target.value.trim().toLocaleLowerCase();
        let visible = 0;
        section.querySelectorAll('tbody tr').forEach(row => {{
          row.hidden = !row.dataset.driver.includes(term); if (!row.hidden) visible++;
        }});
        section.querySelector('.si-empty').hidden = visible > 0;
      }});
    }})();
    </script>
    """


STYLE = """
<style>
html {overflow-x:clip!important;overflow-y:auto;color-scheme:dark}
body {overflow:visible!important}
.puskas-container {max-width:1600px;margin:auto!important}
.p-card:not(.p-next-race) {background:linear-gradient(145deg,#15171f,#101116)!important;border-color:#282c38!important;border-radius:16px!important;box-shadow:0 10px 28px #0002}
.p-next-race {border-color:#282c38!important;border-radius:16px!important;box-shadow:0 10px 28px #0002}
.p-card-title {color:#b5bdcd!important;font-size:.7rem!important;letter-spacing:.1em}
.p-grid,.p-grid-2,.p-grid-3 {gap:20px!important;padding:20px 28px!important}
.p-section-nav {position:sticky;top:0;z-index:100;box-shadow:0 6px 18px #0006;display:flex;gap:8px;padding:16px 28px;border-bottom:1px solid #272b36;flex-wrap:wrap;background:#0b0b0f}
.p-section-nav button {color:#c5cada;background:transparent;cursor:pointer;font:600 12px Inter,system-ui;padding:10px 16px;border:1px solid #303643;border-radius:24px;transition:background .18s}
.p-section-nav button:hover,.p-section-nav button:focus-visible {background:#e10600;color:white;border-color:#e10600}
.p-section-label {padding:24px 28px 0;display:flex;gap:16px;align-items:center;font:800 13px Inter,system-ui;letter-spacing:.1em;text-transform:uppercase;color:#edf0f7;scroll-margin-top:85px}
.p-section-label span {font-size:11px;color:#ff6464}
.si-section {margin:28px;padding:28px;background:#11131b;border:1px solid #2b3040;border-radius:18px;scroll-margin-top:85px;font-family:Inter,system-ui}
.si-heading {display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:24px}
.si-heading h2 {font-size:clamp(22px,3vw,34px);letter-spacing:-.04em;margin:6px 0;color:#fff}
.si-eyebrow {color:#ff6464!important;font-size:10px!important;letter-spacing:.18em;font-weight:800}
.si-heading p,.si-note {color:#929aaf;font-size:12px;line-height:1.6;margin:6px 0}
.si-count {padding:9px 13px;border:1px solid #33394b;border-radius:30px;font-size:11px;white-space:nowrap;color:#c9d0e1}
.si-table-tools h3 {margin:0;font-size:14px;color:#fff}
.si-table-tools {display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:12px}
.si-table-tools label {font-size:11px;color:#9fa8bb;display:flex;gap:8px;align-items:center}
.si-table-tools input {font:12px Inter,system-ui;border:1px solid #343b4c;border-radius:8px;padding:10px;background:#0b0d14;color:#fff;width:180px}
.si-table-scroll {overflow-x:auto;border:1px solid #2d3444;border-radius:10px}
.si-table-scroll:focus-visible {outline:2px solid #ff5757;outline-offset:3px}
.si-table {border-collapse:separate;border-spacing:0;width:100%;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.si-table caption {text-align:left;padding:12px 16px;color:#aab4c9;font-size:11px;background:#151923}
.si-table th,.si-table td {padding:11px 12px;text-align:right;border-bottom:1px solid #242a39;min-width:40px}
.si-table thead th {color:#bcc6dc;background:#1a2030;text-align:center}
.si-table thead tr:first-child th {height:25px;border-bottom-color:#384159}
.si-table thead th span {display:block;font-size:9px;color:#8f9bb4;margin-top:3px}
.si-table tbody th {text-align:left;font-weight:600;color:#f3f5fa;min-width:150px;background:#151923;position:sticky;left:0;z-index:1;border-right:1px solid #323a4d}
.si-table tbody td:first-child {color:#79859c;font-size:10px}
.si-table tbody tr:hover td,.si-table tbody tr:hover th {background:#252e43!important}
.si-table .si-weekend {background:#1c2130;font-weight:700;color:#dbe3f5;border-right:1px solid #3b455c}
.si-table .si-total {background:#372026;font-weight:800;color:#ffb2b2;font-size:14px}
.si-table tfoot th,.si-table tfoot td {background:#242c3e;font-weight:800;border-top:1px solid #53617c}
.si-table [hidden] {display:none}
.si-note {margin-top:12px}
@media(max-width:700px) {
 .p-grid,.p-grid-2,.p-grid-3 {padding:12px!important;gap:12px!important}
 .p-section-nav {padding:12px;gap:6px}.p-section-nav button {padding:8px 10px;font-size:10px}
 .p-section-label {padding:20px 12px 4px;font-size:11px}
 .si-section {margin:16px 12px;padding:16px 12px}.si-heading {display:block}.si-count {display:inline-block;margin-top:10px}
 .si-table-tools {align-items:flex-start;flex-direction:column}
  .si-table th,.si-table td {padding:10px 8px}.si-table tbody th {min-width:120px;font-size:11px}
}
@media(prefers-reduced-motion:reduce) {* {scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style>
"""
