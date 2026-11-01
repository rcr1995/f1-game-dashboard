"""Immutable championship checkpoints, using published points and league scoring.

The renderer never scores a race. Rebuilding from the workbook also incorporates
revised results and adjustments without keeping a second results database.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import pandas as pd

import dashboard_core as core
import league_config as config
from circuit_records import circuit_key
from league_runtime import matching_configured_key, LeagueAuthorityError
from race_import import infer_scoring_profile, ScoringProfileError

# User-authorized fallback for calendars without a Has Sprint column. These are
# 2026 season venues, including league rounds rescheduled into calendar year 2027.
# https://www.fia.com/news/fia-and-formula-1-announce-2026-sprint-calendar
SPRINT_VENUES_2026 = frozenset({
    "chinese gp", "miami gp", "canadian gp", "british gp", "dutch gp", "singapore gp",
})
CANCELLED = {"cancelled", "canceled", "cancelado", "cancelada"}
DONE = {"done", "completed", "complete", "finished", "concluído", "concluída"}
COLORS = ("#ffad45", "#57d3ff", "#e6a0ff", "#a8e45c", "#ff708e", "#8caaFF",
          "#ffdc74", "#5ae0b1", "#eaa278", "#cfb6ff", "#65d3ce", "#ff9fd8")


def championship_catalog(results: pd.DataFrame) -> list[dict]:
    """Published league seasons, with stable keys independent of row ordering.

    The exact three-part identity is also used by the existing league selector.
    Labels carry no standings or winner information before playback starts.
    """
    columns = ["Game", "SeasonLabel", "League Name"]
    if results is None or results.empty or not set(columns).issubset(results.columns):
        return []
    catalog = []
    for _, rows in results.groupby(columns, sort=False, dropna=False):
        if any(pd.isna(rows.iloc[0][column]) or not str(rows.iloc[0][column]).strip()
               for column in columns):
            continue
        _, meta = core.latest_league_slice(rows)
        identity = [str(meta[column]) for column in columns]
        encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
        catalog.append({"key": hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24],
                        "label": " · ".join(identity), "meta": meta})
    return sorted(catalog, key=lambda item: (
        -core.season_sort_key(item["meta"]["SeasonLabel"]),
        str(item["meta"]["SeasonLabel"]).casefold(), str(item["meta"]["SeasonLabel"]),
        str(item["meta"]["Game"]).casefold(), str(item["meta"]["Game"]),
        str(item["meta"]["League Name"]).casefold(), str(item["meta"]["League Name"])))


def select_championship(results: pd.DataFrame, key: str | None = None) -> dict | None:
    """Resolve only a catalog key; an unknown key uses the app's latest league."""
    catalog = championship_catalog(results)
    if not catalog:
        return None
    selected = next((item for item in catalog if item["key"] == key), None)
    if selected is not None:
        return selected
    _, latest = core.latest_league_slice(results)
    return next((item for item in catalog if item["meta"] == latest), catalog[0])


def event_maximum(profile: config.ResolvedScoringProfile) -> float:
    """Maximum *one driver* can earn, respecting bonus finish eligibility."""
    return max((points + (profile.fastest_lap_bonus if profile.fastest_lap_max_finish is None
                          or position <= profile.fastest_lap_max_finish else 0)
                for position, points in profile.finish_points), default=0.0)


def team_event_maximum(profile: config.ResolvedScoringProfile, team_size: int) -> float:
    """A constructor can earn multiple finishes but only one fastest-lap bonus."""
    count = max(0, team_size)
    base = sum(sorted(profile.points.values(), reverse=True)[:count])
    if not count:
        return 0.0
    return max([base] + [points + profile.fastest_lap_bonus
                         + sum(sorted((value for pos, value in profile.finish_points if pos != position), reverse=True)[:count-1])
                         for position, points in profile.finish_points
                         if profile.fastest_lap_max_finish is None or position <= profile.fastest_lap_max_finish])


def _slice(results: pd.DataFrame, meta: dict) -> pd.DataFrame:
    rows = results.copy()
    for column in ("Game", "SeasonLabel", "League Name"):
        if column not in rows:
            return rows.iloc[:0]
        rows = rows[rows[column].fillna("").astype(str).str.strip().eq(str(meta.get(column, "")).strip())]
    return rows


def _archived_calendar(results: pd.DataFrame, calendar: pd.DataFrame, history: pd.DataFrame,
                       meta: dict, tables: config.ConfigTables, key) -> pd.DataFrame:
    """Recover only published rounds of a closed archive, never a future schedule.

    Older legacy seasons without upcoming calendars are treated as finished by
    the existing Hall of Fame. Their numeric published round order is the only
    available chronology. An active/configured league or an ambiguous calendar
    must retain the normal unavailable-calendar fallback.
    """
    if history.empty:
        return pd.DataFrame()
    if calendar is not None and not calendar.empty and "League Name" in calendar:
        names = calendar["League Name"].fillna("").astype(str).str.strip().str.casefold()
        if names.eq(str(meta.get("League Name", "")).strip().casefold()).any():
            return pd.DataFrame()
    if key:
        if config.configured_league_status(tables, key.league_id) != "Completed":
            return pd.DataFrame()
    else:
        _, latest = core.latest_league_slice(results)
        season = core.season_sort_key(meta.get("SeasonLabel", ""))
        if not 0 < season < core.season_sort_key(latest.get("SeasonLabel", "")):
            return pd.DataFrame()
    rounds = pd.to_numeric(history["Round"], errors="coerce")
    if rounds.isna().any() or (rounds <= 0).any() or (rounds % 1 != 0).any():
        return pd.DataFrame()
    published = history.assign(Round=rounds.astype(int))
    unique_rounds = sorted(published.Round.unique())
    if unique_rounds != list(range(1, int(rounds.max()) + 1)):
        return pd.DataFrame()
    entries = []
    for rnd, rows in published.groupby("Round", sort=True):
        names = rows["GP Name"].fillna("").astype(str).str.strip()
        if names.eq("").any() or names.str.casefold().nunique() != 1 or not rows.Type.eq("R").any():
            return pd.DataFrame()
        entries.append({"League Name": meta["League Name"], "Round": int(rnd),
                        "GP Name": names.iloc[0], "Date": pd.NaT, "Status": "Done",
                        "Has Sprint": bool(rows.Type.eq("SR").any())})
    recovered = pd.DataFrame(entries)
    recovered.attrs["has_explicit_sprint_schedule"] = True
    return recovered


def _drivers(names: set[str]) -> list[dict]:
    used = set()
    output = []
    for name in sorted(names, key=str.casefold):
        words = re.findall(r"[\w]+", name, flags=re.UNICODE)
        if len(words) > 1 and words[-1].casefold() in {"jr", "sr"}:
            words.pop()
        code = (words[-1][:3] if len(words) > 1 else name[:3]).upper()
        candidate = code
        number = 2
        while candidate in used:
            candidate = code[:2] + str(number)
            number += 1
        used.add(candidate)
        digest = hashlib.sha256(name.encode()).hexdigest()
        output.append({"id": digest[:12], "name": name, "label": candidate,
                       "color": COLORS[int(digest[:8], 16) % len(COLORS)]})
    return output


def _driver_teams(rows: pd.DataFrame, history: pd.DataFrame, calendar: pd.DataFrame,
                  tables: config.ConfigTables, key) -> dict[str, str]:
    """Latest scoped team assignments, with the current configured roster authoritative."""
    selected = history if not history.empty else rows
    teams: dict[str, str] = {}
    if not selected.empty and {"Driver", "Team", "Round"}.issubset(selected.columns):
        selected = selected.copy()
        selected["_round"] = pd.to_numeric(selected["Round"], errors="coerce").fillna(0)
        # Calendar dates preserve the actual publication sequence for postponed GPs.
        calendar_order = {int(rnd): i for i, rnd in enumerate(calendar.get("Round", [])) if pd.notna(rnd)}
        selected["_event_order"] = selected["_round"].map(calendar_order).fillna(selected["_round"])
        selected["_session_order"] = selected.get("Type", pd.Series("", index=selected.index)).eq("R").astype(int)
        selected["Team"] = selected["Team"].fillna("").astype(str).str.strip()
        selected = selected[selected["Team"].ne("")].sort_values(
            ["_event_order", "_round", "_session_order"], kind="stable")
        for name, group in selected.groupby("Driver", sort=False):
            latest = group.iloc[-1]
            same_event = group[
                group["_event_order"].eq(latest["_event_order"])
                & group["_round"].eq(latest["_round"])
                & group["_session_order"].eq(latest["_session_order"])
            ]["Team"].unique()
            teams[str(name)] = str(same_event[0]) if len(same_event) == 1 else ""
    if key:
        rounds = pd.to_numeric(history.get("Round", pd.Series(dtype=float)), errors="coerce").dropna()
        current_round = max(1, int(rounds.max())) if not rounds.empty else 1
        try:
            for member in config.resolve_roster_snapshot(tables, key.league_id, current_round):
                teams[member.driver_name] = member.team_name
        except (config.LeagueConfigError, ValueError, TypeError):
            # Team labels must not make otherwise readable published standings fail.
            pass
    return teams


def _standings(rows: pd.DataFrame, drivers: list[dict], *, summary=False) -> list[dict]:
    if rows.empty:
        table = pd.DataFrame(columns=["Driver", "Points", "Pos"])
    elif summary:
        table = rows.groupby("Driver", as_index=False).agg(Points=("Points", "sum"), Pos=("Finish Pos", "min"))
        table = table.sort_values(["Points", "Pos", "Driver"], ascending=[False, True, True])
    else:
        # Same wins / podiums / average finish / name ordering as Race Centre.
        table = core.standings_table(rows, "Drivers")
    values = {str(row.Driver): float(row.Points) for row in table.itertuples()}
    # Unclassified entrants have no finish statistics. They follow classified
    # drivers on equal points, but still precede a driver with a negative total.
    order = {name: i for i, name in enumerate(table.Driver)}
    ordered = sorted(drivers, key=lambda d: (-values.get(d["name"], 0), order.get(d["name"], math.inf), d["name"]))
    leader = max((values.get(d["name"], 0) for d in drivers), default=0)
    return [{"id": d["id"], "position": i, "points": values.get(d["name"], 0),
             "gap": leader - values.get(d["name"], 0)} for i, d in enumerate(ordered, 1)]


def build_model(results: pd.DataFrame, calendar: pd.DataFrame, meta: dict,
                tables: config.ConfigTables | None = None) -> dict:
    """Build a start grid and a checkpoint after each completed main Race.

    Race dates, not round numbers, determine playback order after postponements.
    A weekend checkpoint includes its Sprint; stand-alone Sprints wait for their
    main Race checkpoint. Future/unpublished events never gain invented results.
    """
    from puskas_html import get_calendar_for_league, TEAM_COLORS
    tables = tables if tables is not None else config.empty_config_tables()
    rows = _slice(results, meta)
    history = core.filter_event_results(rows) if not rows.empty else rows.copy()
    cal = get_calendar_for_league(calendar, meta).copy()
    names = set(rows.get("Driver", pd.Series(dtype=str)).dropna().astype(str)) - {""}
    notes: list[str] = []
    key = None
    config_error = False
    try:
        key = matching_configured_key(tables, game=meta.get("Game", ""), season=meta.get("SeasonLabel", ""),
                                      league=meta.get("League Name", ""), league_id=meta.get("League ID", ""))
        if key:
            roster = tables.roster_config[tables.roster_config["League ID"].eq(key.league_id)]
            names.update(roster["Driver Name"].astype(str))
    except (config.LeagueConfigError, LeagueAuthorityError, ValueError):
        config_error = True
    if cal.empty and not config_error:
        cal = _archived_calendar(results, calendar, history, meta, tables, key)
        if not cal.empty:
            notes.append("archive_calendar")
    drivers = _drivers(names)
    final_summary = (not rows.empty and history.empty and "IsSeasonFinal" in rows
                     and rows["IsSeasonFinal"].fillna(False).astype(bool).all())
    model = {"drivers": drivers, "frames": [], "meta": dict(meta), "notes": notes,
             "playback": True, "defaultIndex": 0, "totalRaces": 0,
             "completedSeason": bool(final_summary)}
    if not drivers:
        notes.append("no_drivers")
    observed_sprints = set(history.loc[history.Type.eq("SR"), "Round"]) if not history.empty else set()
    race_rounds = set(history.loc[history.Type.eq("R"), "Round"]) if not history.empty else set()
    if not cal.empty and (cal["Round"].isna().any() or cal["Round"].duplicated().any()):
        cal = cal.iloc[:0]
    if cal.empty:
        notes.append("calendar_unavailable")
    else:
        cal["Round"] = cal["Round"].astype(int)
        cal["Status"] = cal["Status"].astype(str).str.strip().str.casefold()
        cal = cal.sort_values(["Date", "Round"], na_position="last", kind="stable")
        # Explicit flags are authoritative. A legacy workbook without the column
        # uses the user's agreed real-life 2026 venue rule, never another year.
        explicit = cal.attrs.get("has_explicit_sprint_schedule",
                                 calendar.attrs.get("has_explicit_sprint_schedule", "Has Sprint" in calendar.columns))
        if (not explicit and not cal.Status.isin(DONE).all()
                and str(meta.get("SeasonLabel", "")).startswith("2026")):
            cal["Has Sprint"] = cal["GP Name"].astype(str).str.strip().str.casefold().isin(SPRINT_VENUES_2026)
            notes.append("sprint_2026")
        elif "Has Sprint" not in cal:
            cal["Has Sprint"] = False
        cal["Has Sprint"] = cal["Has Sprint"].map(core._calendar_boolean) | cal["Round"].isin(observed_sprints)

    active_cal = cal[~cal.Status.isin(CANCELLED) | cal.Round.isin(race_rounds)] if not cal.empty else cal
    model["totalRaces"] = len(active_cal)
    if not active_cal.empty and active_cal.Status.isin(DONE).all():
        model["completedSeason"] = True
    opportunities = {}
    team_opportunities = {}
    scoring_ok = not cal.empty and not config_error
    legacy_profiles = {}
    try:
        for event in cal.to_dict("records"):
            rnd = int(event["Round"])
            kinds = (["R"] if event["Status"] not in CANCELLED or rnd in race_rounds else [])
            if event["Has Sprint"] and (event["Status"] not in CANCELLED or rnd in observed_sprints):
                kinds.insert(0, "SR")
            for kind in kinds:
                if key:
                    roster = config.resolve_roster_snapshot(tables, key.league_id, rnd)
                    profile = config.resolve_scoring_profile(tables, key.league_id, kind, rnd, len(roster))
                    team_size = max((sum(r.team_name == member.team_name for r in roster) for member in roster), default=0)
                else:
                    if kind not in legacy_profiles:
                        points_map = infer_scoring_profile(rows, game=meta["Game"], season=meta["SeasonLabel"],
                                                        league=meta["League Name"], event_type=kind,
                                                        grid_size=int(history["Finish Pos"].max()) if not history.empty else len(drivers))
                        legacy_profiles[kind] = config.ResolvedScoringProfile("legacy", "", kind, 1, tuple(points_map.items()))
                    profile = legacy_profiles[kind]
                    team_size = int(history.groupby(["Round", "Type", "Team"]).Driver.nunique().max()) if not history.empty else 0
                maximum = event_maximum(profile)
                if not math.isfinite(maximum) or maximum < 0:
                    raise ValueError("Invalid scoring maximum")
                opportunities[(rnd, kind)] = maximum
                team_opportunities[(rnd, kind)] = team_event_maximum(profile, team_size)
    except (config.LeagueConfigError, ScoringProfileError, ValueError, TypeError):
        scoring_ok = False
    if not scoring_ok and not cal.empty:
        notes.append("scoring_unavailable")

    def frame(selected, *, name, rnd, completed, consumed, summary=False):
        standings = _standings(selected, drivers, summary=summary)
        remaining = sum(maximum for event, maximum in opportunities.items() if event not in consumed) if scoring_ok else None
        # A fully completed calendar proves there is nothing left to earn even
        # if old position-only scoring cannot be reconstructed from a summary.
        if not cal.empty and all((int(e["Round"]), kind) in consumed
                                 for e in active_cal.to_dict("records")
                                 for kind in (("SR", "R") if e["Has Sprint"] else ("R",))):
            remaining = 0.0
        elif final_summary and cal.empty:
            # A saved Season Final is an explicit completed championship. Its
            # totals are usable without guessing the missing races or scoring.
            remaining = 0.0
        leader = standings[0]["points"] if standings else 0.0
        target = leader + remaining if remaining is not None else None
        pending = [event for event in opportunities if event not in consumed]
        next_round = pending[0][0] if pending else None
        for entry in standings:
            entry["progress"] = entry["points"] / target if target is not None and target > 0 else (0.0 if target is not None else None)
        return {"name": name, "round": rnd, "completed": completed, "remaining": remaining,
                "target": target, "standings": standings,
                "remainingTeam": sum(team_opportunities[e] for e in pending) if remaining is not None else None,
                "nextWeekendMaximum": sum(opportunities[e] for e in pending if e[0] == next_round),
                "nextTeamWeekendMaximum": sum(team_opportunities[e] for e in pending if e[0] == next_round),
                "remainingRaces": sum(1 for event in opportunities if event[1] == "R" and event not in consumed),
                "remainingSprints": sum(1 for event in opportunities if event[1] == "SR" and event not in consumed)}

    # Check that a historical sequence can be reconstructed without duplication,
    # missing completed rounds, or assigning an unrelated GP to a round.
    history_ok = not cal.empty
    if not history.empty:
        if history.duplicated(["Driver", "Round", "Type"]).any() or not history.Points.map(lambda x: math.isfinite(float(x))).all():
            history_ok = False
        if not set(history.Round).issubset(set(cal.get("Round", []))):
            history_ok = False
        for event in cal.to_dict("records"):
            group = history[history.Round.eq(event["Round"])]
            if not group.empty and {circuit_key(name) for name in group["GP Name"].astype(str)} != {circuit_key(str(event["GP Name"]))}:
                history_ok = False
            if event["Status"] in DONE and event["Round"] not in race_rounds:
                history_ok = False
            if event["Round"] in race_rounds and event["Has Sprint"] and event["Round"] not in observed_sprints:
                history_ok = False
    elif not cal.empty and cal.Status.isin(DONE).any():
        history_ok = False
    if not rows.empty and history.empty:
        history_ok = False
    if model["completedSeason"] and not scoring_ok:
        # Archived points alone cannot establish each historical finish-line
        # target. Offer the exact final snapshot instead of stationary-car replay.
        history_ok = False

    if not history_ok:
        notes.append("history_unavailable")
        model["playback"] = False
        consumed = {(int(e["Round"]), kind) for e in cal.to_dict("records")
                    if e["Status"] in DONE or e["Round"] in race_rounds for kind in ("R", "SR")}
        summary = history.empty and not rows.empty
        selected = rows if summary else history
        completed = len(race_rounds)
        if summary:
            completed = int(cal["Status"].isin(DONE).sum()) if "Status" in cal else 0
        model["frames"] = [frame(selected, name="current", rnd=None, completed=completed,
                                 consumed=consumed, summary=summary)]
    else:
        model["frames"].append(frame(history.iloc[:0], name="grid", rnd=0, completed=0, consumed=set()))
        consumed = set()
        completed = []
        visited = []
        for event in cal.to_dict("records"):
            rnd = int(event["Round"])
            visited.append(rnd)
            if rnd in observed_sprints:
                consumed.add((rnd, "SR"))
            if rnd not in race_rounds:
                continue
            completed.append(rnd)
            consumed.update((rnd, kind) for kind in ("R", "SR"))
            selected = history[history.Round.isin(visited)]
            model["frames"].append(frame(selected, name=str(event["GP Name"]), rnd=rnd,
                                         completed=len(completed), consumed=consumed))
        model["defaultIndex"] = len(model["frames"]) - 1
    teams = _driver_teams(rows, history, cal, tables, key)
    known_teams = {name.casefold(): name for name in TEAM_COLORS}
    for driver in drivers:
        team = teams.get(driver["name"], "")
        driver["team"] = known_teams.get(team.casefold(), team)
        fallback = COLORS[int(hashlib.sha256(team.casefold().encode()).hexdigest()[:8], 16) % len(COLORS)] if team else driver["color"]
        color = TEAM_COLORS.get(driver["team"], fallback)
        driver["teamColor"] = color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else fallback
    return model
