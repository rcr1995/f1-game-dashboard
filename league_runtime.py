"""Resolve authoritative roster and scoring for one Admin event.

Configuration-backed leagues are preferred. Legacy championships continue to
use their completed result history, preserving the manual Excel workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

import league_config as config
import race_import as race
import race_workbook as workbook


class LeagueAuthorityError(workbook.WorkbookUpdateError):
    """Raised when an event has no single authoritative roster/rule set."""


@dataclass(frozen=True)
class EventAuthority:
    league_key: config.LeagueKey | None
    roster: tuple[race.DriverEntry, ...]
    scoring: config.ResolvedScoringProfile

    @property
    def league_id(self) -> str:
        return self.league_key.league_id if self.league_key else ""

    @property
    def base_points(self) -> dict[int, float]:
        return self.scoring.points


def _identity(value: object) -> str:
    return config.normalize_identity(value)


def matching_configured_key(
    tables: config.ConfigTables,
    *,
    game: str,
    season: str,
    league: str,
    league_id: str = "",
) -> config.LeagueKey | None:
    keys = config.configured_league_keys(tables)
    if league_id:
        selected = [key for key in keys if key.league_id == league_id]
        if len(selected) != 1:
            raise LeagueAuthorityError("The configured League ID was not found uniquely.")
        key = selected[0]
        if (_identity(key.game), _identity(key.season), _identity(key.league_name)) != (
            _identity(game),
            _identity(season),
            _identity(league),
        ):
            raise LeagueAuthorityError("The configured League ID does not match the selected championship.")
        return key
    selected = [
        key
        for key in keys
        if (_identity(key.game), _identity(key.season), _identity(key.league_name))
        == (_identity(game), _identity(season), _identity(league))
    ]
    if len(selected) > 1:
        raise LeagueAuthorityError("The selected championship maps to more than one configured League ID.")
    return selected[0] if selected else None


def resolve_event_authority(
    source: str | Path,
    standings: pd.DataFrame,
    metadata: workbook.RaceMetadata,
) -> EventAuthority:
    """Resolve one round's complete roster and event-specific scoring."""
    try:
        tables = config.load_config_tables(source)
        key = matching_configured_key(
            tables,
            game=metadata.game,
            season=metadata.season,
            league=metadata.league,
            league_id=metadata.league_id,
        )
        if key is not None:
            roster_rows = config.resolve_roster_snapshot(
                tables,
                key.league_id,
                metadata.round_number,
            )
            roster = tuple(
                race.DriverEntry(row.driver_name, row.team_name, row.ocr_aliases)
                for row in roster_rows
            )
            scoring = config.resolve_scoring_profile(
                tables,
                key.league_id,
                metadata.event_type,
                metadata.round_number,
                len(roster),
            )
            return EventAuthority(key, roster, scoring)

        legacy_roster = tuple(
            race.derive_championship_roster(
                standings,
                game=metadata.game,
                season=metadata.season,
                league=metadata.league,
            )
        )
        legacy_points = race.infer_scoring_profile(
            standings,
            game=metadata.game,
            season=metadata.season,
            league=metadata.league,
            event_type=metadata.event_type,
            grid_size=len(legacy_roster),
        )
        scoring = config.ResolvedScoringProfile(
            "legacy",
            "",
            metadata.event_type.upper(),
            1,
            tuple(sorted((int(position), float(points)) for position, points in legacy_points.items())),
            0.0,
            None,
        )
        return EventAuthority(None, legacy_roster, scoring)
    except (
        config.LeagueConfigError,
        race.RosterError,
        race.ScoringProfileError,
        ValueError,
    ) as exc:
        raise LeagueAuthorityError(f"The workbook cannot resolve this event's roster and scoring: {exc}") from exc


def apply_configured_points(
    rows: Iterable[Mapping[str, object]],
    authority: EventAuthority,
) -> tuple[list[dict[str, object]], config.FastestLapAward]:
    """Apply base and optional unique fastest-lap points to reviewed rows."""
    normalized = [dict(row) for row in rows]
    try:
        award = config.derive_fastest_lap_bonus(normalized, authority.scoring)
    except config.LeagueConfigError as exc:
        raise LeagueAuthorityError(str(exc)) from exc
    points = authority.scoring.points
    output: list[dict[str, object]] = []
    for row in normalized:
        try:
            position = int(row["Position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LeagueAuthorityError("Every reviewed row needs a valid Position before scoring.") from exc
        base = float(points.get(position, 0.0))
        bonus = float(award.bonus) if award.position == position else 0.0
        row["Base Points"] = base
        row["Fastest Lap Bonus"] = bonus
        row["Points"] = base + bonus
        output.append(row)
    return output, award


def championship_options(
    standings: pd.DataFrame,
    tables: config.ConfigTables,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return unmanaged legacy plus Active configured championship identities.

    Once an identity is configuration-backed, its workbook status is
    authoritative.  Draft and Completed identities must not re-enter the
    normal importer merely because historical result rows exist.
    """
    values: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
    configured = config.configured_league_keys(tables)
    managed_identities = {
        tuple(_identity(item) for item in (key.game, key.season, key.league_name))
        for key in configured
    }
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    if {"Game", season_column, "League Name"}.issubset(standings.columns):
        for game, season, league in standings[["Game", season_column, "League Name"]].dropna().itertuples(
            index=False, name=None
        ):
            identity = (str(game).strip(), str(season).strip(), str(league).strip())
            normalized = tuple(_identity(item) for item in identity)
            if normalized not in managed_identities:
                values[normalized] = (*identity, "")
    active_ids = set(
        tables.league_config.loc[
            tables.league_config["Status"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq("active"),
            "League ID",
        ].astype(str).str.strip()
    )
    for key in configured:
        if key.league_id not in active_ids:
            continue
        identity = (key.game, key.season, key.league_name)
        values[tuple(_identity(item) for item in identity)] = (*identity, key.league_id)
    return tuple(
        sorted(values.values(), key=lambda value: (value[1], value[2], value[0], value[3]), reverse=True)
    )
