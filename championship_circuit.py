"""Immutable championship checkpoints, using published points and league scoring.

The renderer never scores a race. Rebuilding from the workbook also incorporates
revised results and adjustments without keeping a second results database.
"""
from __future__ import annotations

import hashlib
import math
import re

import pandas as pd

import dashboard_core as core
import league_config as config
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
    from puskas_html import get_calendar_for_league
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
    drivers = _drivers(names)
    model = {"drivers": drivers, "frames": [], "meta": dict(meta), "notes": notes,
             "playback": True, "defaultIndex": 0, "totalRaces": 0}
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
        explicit = calendar.attrs.get("has_explicit_sprint_schedule", "Has Sprint" in calendar.columns)
        if not explicit and str(meta.get("SeasonLabel", "")).startswith("2026"):
            cal["Has Sprint"] = cal["GP Name"].astype(str).str.strip().str.casefold().isin(SPRINT_VENUES_2026)
            notes.append("sprint_2026")
        elif "Has Sprint" not in cal:
            cal["Has Sprint"] = False
        cal["Has Sprint"] = cal["Has Sprint"].map(core._calendar_boolean) | cal["Round"].isin(observed_sprints)

    active_cal = cal[~cal.Status.isin(CANCELLED) | cal.Round.isin(race_rounds)] if not cal.empty else cal
    model["totalRaces"] = len(active_cal)
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
            if not group.empty and set(group["GP Name"].str.strip().str.casefold()) != {str(event["GP Name"]).strip().casefold()}:
                history_ok = False
            if event["Status"] in DONE and event["Round"] not in race_rounds:
                history_ok = False
            if event["Round"] in race_rounds and event["Has Sprint"] and event["Round"] not in observed_sprints:
                history_ok = False
    elif not cal.empty and cal.Status.isin(DONE).any():
        history_ok = False
    if not rows.empty and history.empty:
        history_ok = False

    if not history_ok:
        notes.append("history_unavailable")
        model["playback"] = False
        consumed = {(int(e["Round"]), kind) for e in cal.to_dict("records")
                    if e["Status"] in DONE or e["Round"] in race_rounds for kind in ("R", "SR")}
        summary = history.empty and not rows.empty
        selected = rows if summary else history
        model["frames"] = [frame(selected, name="current", rnd=None, completed=len(race_rounds) if not summary else len(cal[cal.Status.isin(DONE)]), consumed=consumed, summary=summary)]
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
    return model
