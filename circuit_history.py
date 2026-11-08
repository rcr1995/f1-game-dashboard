"""Published circuit histories and three-driver comparisons, grouped by venue."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import math
import re

import pandas as pd

from circuit_records import CIRCUIT_RECORDS, circuit_key, get_circuit_record, _key, _lap_milliseconds
from circuit_explorer import country_metadata
from dashboard_core import season_sort_key


_CANONICAL_GP = {record.circuit: gp for gp, record in CIRCUIT_RECORDS.items()}
HEAD_TO_HEAD_DRIVERS = ("TomasRodri21", "Polingua", "Fatacuida")
_HUMAN_NAMES = {"tomasrodri": "TomasRodri21", "tomasrodri21": "TomasRodri21",
                "polingua": "Polingua", "fatacuida": "Fatacuida"}


def _driver(value) -> str | None:
    return _HUMAN_NAMES.get(_key(_text(value)))


def _head_to_head(sessions: dict[tuple, list[dict]]) -> list[dict]:
    """One appearance per published session/driver, with honest partial results."""
    stats = {driver: {"driver": driver, "starts": 0, "wins": 0, "podiums": 0,
                      "best_lap": None, "best_lap_season": None, "best_lap_ms": None,
                      "best_lap_type": None, "best_lap_league": None, "best_lap_game": None,
                      "has_results": False, "unresolved_results": 0}
             for driver in HEAD_TO_HEAD_DRIVERS}
    best = {}
    for session_key, rows in sessions.items():
        kind = session_key[-1]
        drivers = defaultdict(list)
        rank_owners = defaultdict(set)
        for row in rows:
            driver = _driver(row.get("Driver"))
            if driver:
                drivers[driver].append(row)
            position = _round(row.get("Finish Pos"))
            if position:
                owner = driver or _identity(row.get("Driver"))
                if owner:
                    rank_owners[position].add(owner)
        for driver, records in drivers.items():
            item = stats[driver]
            item["has_results"] = True
            positions = {_round(row.get("Finish Pos")) for row in records}
            conflicting_positions = len(positions) > 1
            unresolved = False
            if kind == "R":
                # Even a disputed classification is one recorded appearance.
                item["starts"] += 1
                position = next(iter(positions)) if len(positions) == 1 else None
                confirmed = position is not None and len(rank_owners[position]) == 1
                if confirmed:
                    item["wins"] += int(position == 1)
                    item["podiums"] += int(position <= 3)
                else:
                    unresolved = True
            laps = {_lap_milliseconds(row.get("Fastest Lap")) for row in records}
            known_laps = laps - {None}
            if len(known_laps) > 1 or conflicting_positions:
                # Duplicate aliases must not turn a revision conflict into a PB.
                unresolved = True
            elif known_laps:
                milliseconds = next(iter(known_laps))
                for row in records:
                    if _lap_milliseconds(row.get("Fastest Lap")) != milliseconds:
                        continue
                    candidate = (milliseconds, _season(row), _text(row.get("Game")),
                                 _text(row.get("League Name")), kind, _round(row.get("Round")) or 0)
                    if driver not in best or candidate < best[driver]:
                        best[driver] = candidate
            item["unresolved_results"] += int(unresolved)
    for driver, candidate in best.items():
        milliseconds, season, game, league, kind, _ = candidate
        minutes, remainder = divmod(milliseconds, 60_000)
        seconds, fraction = divmod(remainder, 1000)
        stats[driver].update(best_lap=f"{minutes}:{seconds:02}.{fraction:03}",
                             best_lap_season=season or None, best_lap_ms=milliseconds,
                             best_lap_type=kind, best_lap_league=league or None,
                             best_lap_game=game or None)
    return list(stats.values())


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _identity(value) -> str:
    return " ".join(_text(value).casefold().split())


def _round(value) -> int | None:
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number > 0 and number.is_integer() else None
    except (ValueError, TypeError):
        return None


def _date(value) -> str | None:
    if isinstance(value, (datetime, date, pd.Timestamp)) and not pd.isna(value):
        return value.strftime("%Y-%m-%d")
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    complete_iso = re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", text)
    named_month = re.fullmatch(r"(?:\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4})", text)
    if not (complete_iso or named_month):
        # 03/04/2026 has two valid meanings; a missing day is not a race date.
        return None
    try:
        # Numeric cells are not interpreted as nanoseconds or guessed Excel dates.
        parsed = pd.to_datetime(text, errors="raise")
        return parsed.strftime("%Y-%m-%d") if not pd.isna(parsed) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _season(row: dict) -> str:
    return _text(row.get("SeasonLabel")) or _text(row.get("Season"))


def _scope(row: dict) -> tuple[str, str, str]:
    return (_identity(row.get("Game")), _identity(_season(row)), _identity(row.get("League Name")))


def _event_calendar(row: dict, calendar: list[dict], scopes: set[tuple]) -> dict | None:
    """Match one calendar event without borrowing another season's date/venue."""
    rnd = _round(row.get("Round"))
    if rnd is None:
        return None
    row_scope = _scope(row)
    row_id = _identity(row.get("League ID"))
    row_gp, row_circuit = _text(row.get("GP Name")), _text(row.get("Circuit"))
    matches = []
    for item in calendar:
        if _round(item.get("Round")) != rnd:
            continue
        item_id = _identity(item.get("League ID"))
        if row_id and item_id and row_id != item_id:
            continue
        league = _identity(item.get("League Name"))
        if league and league != row_scope[2]:
            continue
        game, season = _identity(item.get("Game")), _identity(_season(item))
        if (game and game != row_scope[0]) or (season and season != row_scope[1]):
            continue
        id_match = bool(row_id and item_id and row_id == item_id)
        if not id_match:
            # Blank legacy championship fields are usable only if the remaining
            # fields identify exactly one published championship in this workbook.
            if not league or (item_id and not (game and season)):
                continue
            possible = {scope for scope in scopes
                        if scope[2] == league and (not game or scope[0] == game)
                        and (not season or scope[1] == season)}
            if possible != {row_scope}:
                continue
        item_gp, item_circuit = _text(item.get("GP Name")), _text(item.get("Circuit"))
        if row_circuit and item_circuit and circuit_key(row_gp, row_circuit) != circuit_key(item_gp, item_circuit):
            continue
        if (_identity(row_gp) != _identity(item_gp)
                and circuit_key(row_gp, row_circuit) != circuit_key(item_gp, item_circuit)):
            continue
        matches.append(item)
    return matches[0] if len(matches) == 1 else None


def circuit_history(results: pd.DataFrame | None, calendar: pd.DataFrame | None = None,
                    meta: dict | None = None) -> list[dict]:
    """Build cards and complete winner lists from published Race results only.

    Sprint-only venues remain in the layout catalog with no main-race winners.
    An optional Game/SeasonLabel/League Name identity limits the visible history.
    Calendar ambiguity is checked against the full source even when filtering.
    Dates are included only when recorded directly or matched unambiguously to
    the event calendar. Summary-only seasons do not supply invented GP winners.
    Human comparisons count unique main-race results; lap records may also come
    from Sprints, and conflicting duplicate results are marked as partial.
    """
    required = {"GP Name", "Type", "Driver", "Finish Pos"}
    if results is None or results.empty or not required.issubset(results.columns):
        return []
    all_rows = results.to_dict("records")
    scopes = {_scope(row) for row in all_rows}
    if meta is not None:
        # The selector uses exact source identities. Case/spacing variants must
        # not combine histories from separate catalog entries.
        columns = ('Game', 'SeasonLabel', 'League Name')
        all_rows = [row for row in all_rows if all(str(row.get(column, '')) == str(meta.get(column, ''))
                                                 for column in columns)]
    calendar_rows = calendar.to_dict("records") if calendar is not None else []
    cards: dict[str, dict] = {}
    resolved_keys: set[str] = set()
    events: dict[tuple, list[dict]] = defaultdict(list)
    sessions: dict[str, dict[tuple, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in all_rows:
        final = _identity(row.get("IsSeasonFinal")) in {"true", "1", "yes"}
        kind = _text(row.get("Type")).upper()
        if final or kind not in {"R", "SR"} or _identity(row.get("GP Name")) == "season final":
            continue
        gp = _text(row.get("GP Name"))
        if not gp:
            continue
        matched = _event_calendar(row, calendar_rows, scopes)
        venue = _text(row.get("Circuit")) or (_text(matched.get("Circuit")) if matched else "")
        record = get_circuit_record(gp, venue)
        # Generic Spanish GP has been used at several venues. Without explicit
        # evidence it must not be silently added to Madrid's modern record.
        unresolved_spanish = not venue and _identity(gp) in {"spanish gp", "spanish grand prix"}
        key = "unrecordedspanishgp" if unresolved_spanish else circuit_key(gp, venue)
        if not key:
            continue
        canonical_gp = ("Spanish GP" if unresolved_spanish else
                        _CANONICAL_GP.get(record.circuit, gp) if record else gp)
        circuit_name = record.circuit if record and not unresolved_spanish else venue
        card = cards.setdefault(key, {"key": key, "gp_name": canonical_gp, "circuit_name": circuit_name,
                                      "venue_recorded": bool(circuit_name), "winners": [], "leaders": [],
                                      "race_count": 0, "unresolved_events": 0})
        if record and not unresolved_spanish:
            # A known venue is authoritative even if an earlier GP string
            # created this same key without enough display metadata.
            card["gp_name"] = canonical_gp
            card["circuit_name"] = circuit_name
            card["venue_recorded"] = True
            resolved_keys.add(key)
        elif key not in resolved_keys:
            card["gp_name"] = min((card["gp_name"], canonical_gp), key=lambda value: (value.casefold(), value))
            names = [name for name in (card["circuit_name"], circuit_name) if name]
            card["circuit_name"] = min(names, key=lambda value: (value.casefold(), value), default="")
            card["venue_recorded"] = bool(card["circuit_name"])
        if _round(row.get("Round")) is None:
            continue
        event_key = (key, *_scope(row), _identity(row.get("League ID")), _round(row.get("Round")))
        sessions[key][(*event_key, kind)].append(row)
        if kind != "R":
            continue
        event_date = _date(row.get("Date")) or (_date(matched.get("Date")) if matched else None)
        events[event_key].append({**row, "_date": event_date})

    for event_key, rows in events.items():
        card = cards[event_key[0]]
        classifications = defaultdict(set)
        for row in rows:
            owner = _driver(row.get("Driver")) or _text(row.get("Driver"))
            if owner:
                classifications[owner].add(_round(row.get("Finish Pos")))
        first_place = [row for row in rows if _round(row.get("Finish Pos")) == 1
                       and _text(row.get("Driver"))]
        first_owners = {_driver(row["Driver"]) or _text(row["Driver"]) for row in first_place}
        # A disputed P1 owner cannot make a second P1 claim authoritative merely
        # by being filtered out. Preserve the original event-level ambiguity.
        candidates = [row for row in first_place
                      if classifications[_driver(row["Driver"]) or _text(row["Driver"])] == {1}
                      ] if len(first_owners) == 1 else []
        names = {_driver(row["Driver"]) or _text(row["Driver"]) for row in candidates}
        if len(names) != 1:
            card["unresolved_events"] += 1
            continue
        first = min(candidates, key=lambda row: tuple(_text(row.get(field)) for field in ("Game", "SeasonLabel", "Season", "League Name", "GP Name")))
        dates = {row["_date"] for row in candidates if row["_date"]}
        card["winners"].append({"driver": next(iter(names)), "game": _text(first.get("Game")),
                                "season": _season(first), "league": _text(first.get("League Name")),
                                "round": _round(first.get("Round")), "date": next(iter(dates)) if len(dates) == 1 else None,
                                "gp_name": _text(first.get("GP Name"))})
    for card in cards.values():
        card.update(country_metadata(card["gp_name"], card["circuit_name"]))
        card["head_to_head"] = _head_to_head(sessions[card["key"]])
        card["winners"].sort(key=lambda row: (-season_sort_key(row["season"]), -(row["round"] or 0),
                                               row["game"].casefold(), row["league"].casefold(), row["driver"].casefold()))
        counts = Counter(row["driver"] for row in card["winners"])
        card["leaders"] = [{"driver": driver, "wins": wins} for driver, wins in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].casefold(), pair[0]))]
        card["race_count"] = len(card["winners"])
    return sorted(cards.values(), key=lambda card: (card["gp_name"].casefold(), card["key"]))
