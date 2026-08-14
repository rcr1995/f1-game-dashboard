"""Pure, fail-closed league configuration models and validation.

The workbook persistence layer deliberately lives elsewhere.  This module
owns only the normalized configuration schema, cloning/resolution rules, and
canonical review digests so it can be exercised without Streamlit, GitHub, or
OOXML mutation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import re
from typing import BinaryIO, Callable, Iterable, Mapping, Sequence
import unicodedata

import pandas as pd


LEAGUE_CONFIG_SHEET = "League Config"
ROSTER_CONFIG_SHEET = "Roster Config"
SCORING_PROFILES_SHEET = "Scoring Profiles"
SCORING_POINTS_SHEET = "Scoring Points"

SCHEMA_VERSION = 1
LEAGUE_STATUSES = frozenset({"Draft", "Active", "Completed"})
EVENT_TYPES = frozenset({"R", "SR"})

LEAGUE_CONFIG_COLUMNS = (
    "League ID",
    "Game",
    "Season",
    "League Name",
    "Status",
    "Cloned From League ID",
    "Created UTC",
    "Schema Version",
)
ROSTER_CONFIG_COLUMNS = (
    "League ID",
    "Effective From Round",
    "Driver Name",
    "Team Name",
    "OCR Aliases",
)
SCORING_PROFILE_COLUMNS = (
    "Profile ID",
    "League ID",
    "Event Type",
    "Effective From Round",
    "Fastest Lap Bonus",
    "Fastest Lap Max Finish",
)
SCORING_POINT_COLUMNS = (
    "Profile ID",
    "Position",
    "Points",
)

_SHEET_COLUMNS = {
    LEAGUE_CONFIG_SHEET: LEAGUE_CONFIG_COLUMNS,
    ROSTER_CONFIG_SHEET: ROSTER_CONFIG_COLUMNS,
    SCORING_PROFILES_SHEET: SCORING_PROFILE_COLUMNS,
    SCORING_POINTS_SHEET: SCORING_POINT_COLUMNS,
}
_LEAGUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
_FASTEST_LAP_RE = re.compile(r"^(\d{1,2}):([0-5]\d)\.(\d{3})$")
_NO_LAP_VALUES = frozenset({"N/A", "NA", "DNF", "DNS", "DSQ", "DQ", "RET", "NC", "DNQ"})


class LeagueConfigError(ValueError):
    """Base class for invalid or unresolvable league configuration."""


class LeagueConfigValidationError(LeagueConfigError):
    """Raised when one or more configuration invariants are broken."""

    def __init__(self, issues: Iterable[str]):
        self.issues = tuple(dict.fromkeys(str(issue) for issue in issues if str(issue).strip()))
        super().__init__("; ".join(self.issues) or "League configuration is invalid.")


class LeagueConfigResolutionError(LeagueConfigError):
    """Raised when no configured or legacy snapshot can resolve an event."""


@dataclass(frozen=True)
class LeagueKey:
    league_id: str
    game: str
    season: str
    league_name: str


@dataclass(frozen=True)
class CalendarRound:
    round_number: int
    date: date
    gp_name: str
    circuit: str
    status: str = "Upcoming"
    time_lisbon: time | None = None
    has_sprint: bool = False


@dataclass(frozen=True)
class RosterChange:
    """One member of a complete roster snapshot effective from one round."""

    league_id: str
    effective_from_round: int
    driver_name: str
    team_name: str
    ocr_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoringProfile:
    profile_id: str
    league_id: str
    event_type: str
    effective_from_round: int
    fastest_lap_bonus: float = 0.0
    fastest_lap_max_finish: int | None = None


@dataclass(frozen=True)
class ScoringPoint:
    profile_id: str
    position: int
    points: float


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LeagueSetup:
    key: LeagueKey
    calendar: tuple[CalendarRound, ...]
    roster: tuple[RosterChange, ...]
    scoring_profiles: tuple[ScoringProfile, ...]
    scoring_points: tuple[ScoringPoint, ...]
    status: str = "Draft"
    cloned_from_league_id: str = ""
    created_utc: datetime = field(default_factory=_utc_now)
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class RosterSnapshotUpdate:
    """One future complete-roster snapshot and optional scoring revisions."""

    league_id: str
    effective_from_round: int
    complete_roster: tuple[RosterChange, ...]
    scoring_profiles: tuple[ScoringProfile, ...] = ()
    scoring_points: tuple[ScoringPoint, ...] = ()


@dataclass(frozen=True)
class ConfigTables:
    league_config: pd.DataFrame
    roster_config: pd.DataFrame
    scoring_profiles: pd.DataFrame
    scoring_points: pd.DataFrame


@dataclass(frozen=True)
class ResolvedScoringProfile:
    profile_id: str
    league_id: str
    event_type: str
    effective_from_round: int
    finish_points: tuple[tuple[int, float], ...]
    fastest_lap_bonus: float = 0.0
    fastest_lap_max_finish: int | None = None

    @property
    def points(self) -> dict[int, float]:
        return dict(self.finish_points)


@dataclass(frozen=True)
class FastestLapAward:
    driver_name: str | None
    position: int | None
    lap_time: str | None
    bonus: float


LegacyRosterFallback = Callable[[int], Sequence[object]]
LegacyScoringFallback = Callable[[str, int, int], Mapping[int, float] | ResolvedScoringProfile]


def empty_config_tables() -> ConfigTables:
    return ConfigTables(
        league_config=pd.DataFrame(columns=LEAGUE_CONFIG_COLUMNS),
        roster_config=pd.DataFrame(columns=ROSTER_CONFIG_COLUMNS),
        scoring_profiles=pd.DataFrame(columns=SCORING_PROFILE_COLUMNS),
        scoring_points=pd.DataFrame(columns=SCORING_POINT_COLUMNS),
    )


def _clean_sheet(frame: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [str(column).strip() for column in result.columns]
    empty_unnamed = [
        column
        for column in result.columns
        if column.startswith("Unnamed:") and result[column].isna().all()
    ]
    if empty_unnamed:
        result = result.drop(columns=empty_unnamed)
    expected = list(_SHEET_COLUMNS[sheet_name])
    if list(result.columns) != expected:
        missing = [column for column in expected if column not in result.columns]
        extra = [column for column in result.columns if column not in expected]
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        if not missing and not extra:
            details.append("columns are out of order")
        raise LeagueConfigValidationError(
            [f"Sheet '{sheet_name}' does not match its locked schema ({'; '.join(details)})."]
        )
    result = result.loc[:, expected].dropna(how="all").reset_index(drop=True)
    if sheet_name == LEAGUE_CONFIG_SHEET:
        result["Cloned From League ID"] = result["Cloned From League ID"].fillna("")
    elif sheet_name == ROSTER_CONFIG_SHEET:
        result["OCR Aliases"] = result["OCR Aliases"].fillna("")
    return result


def load_config_tables(source: str | BinaryIO) -> ConfigTables:
    """Load all configuration sheets; absent sheets become empty frames.

    A present sheet must match the locked schema exactly.  Cross-sheet/domain
    invariants are intentionally exposed through :func:`validate_config_tables`
    so callers may load an entirely legacy workbook without error.
    """

    try:
        workbook = pd.ExcelFile(source)
    except Exception as exc:
        raise LeagueConfigError(f"Could not open the Excel workbook: {exc}") from exc
    try:
        frames: dict[str, pd.DataFrame] = {}
        for sheet_name, columns in _SHEET_COLUMNS.items():
            if sheet_name not in workbook.sheet_names:
                frames[sheet_name] = pd.DataFrame(columns=columns)
            else:
                frames[sheet_name] = _clean_sheet(
                    pd.read_excel(workbook, sheet_name=sheet_name), sheet_name
                )
    finally:
        workbook.close()
    return ConfigTables(
        frames[LEAGUE_CONFIG_SHEET],
        frames[ROSTER_CONFIG_SHEET],
        frames[SCORING_PROFILES_SHEET],
        frames[SCORING_POINTS_SHEET],
    )


def normalize_identity(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _text_value(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            missing = pd.isna(value)
        except (TypeError, ValueError):
            missing = False
        if isinstance(missing, bool) and missing:
            return ""
    return str(value).strip()


def parse_ocr_aliases(value: object) -> tuple[str, ...]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ()
    aliases = [part.strip() for part in re.split(r"[|;\n]+", str(value)) if part.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        normalized = normalize_identity(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(alias)
    return tuple(result)


def serialize_ocr_aliases(aliases: Iterable[str]) -> str:
    return " | ".join(parse_ocr_aliases(" | ".join(str(alias) for alias in aliases)))


def _required_text(value: object, label: str, issues: list[str]) -> str:
    text = _text_value(value)
    if not text:
        issues.append(f"{label} must not be blank.")
    elif any(ord(character) < 32 for character in text):
        issues.append(f"{label} contains a control character.")
    return text


def _positive_integer(value: object, label: str, issues: list[str]) -> int | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not float(numeric).is_integer() or int(numeric) < 1:
        issues.append(f"{label} must be a positive integer.")
        return None
    return int(numeric)


def _nonnegative_number(value: object, label: str, issues: list[str]) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not math.isfinite(float(numeric)) or float(numeric) < 0:
        issues.append(f"{label} must be a finite non-negative number.")
        return None
    return float(numeric)


def _created_datetime(value: object, label: str, issues: list[str]) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed_value = pd.to_datetime(value, errors="raise", utc=True)
            parsed = parsed_value.to_pydatetime()
        except Exception:
            issues.append(f"{label} must be a valid UTC timestamp.")
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        issues.append(f"{label} must include a timezone.")
        return None
    return parsed.astimezone(timezone.utc)


def _validate_key(key: LeagueKey, issues: list[str]) -> None:
    league_id = _required_text(key.league_id, "League ID", issues)
    if league_id and not _LEAGUE_ID_RE.fullmatch(league_id):
        issues.append("League ID may contain only letters, numbers, dot, underscore, colon, and hyphen.")
    _required_text(key.game, "Game", issues)
    _required_text(key.season, "Season", issues)
    league_name = _required_text(key.league_name, "League Name", issues)
    if league_name and not normalize_identity(league_name):
        issues.append("League Name must contain at least one letter or number.")


def _league_rows(tables: ConfigTables) -> list[dict[str, object]]:
    return tables.league_config.to_dict("records")


def validate_config_tables(
    tables: ConfigTables, *, require_clone_sources: bool = True
) -> None:
    """Validate the four locked sheets and their cross-sheet references."""

    for sheet_name, frame in (
        (LEAGUE_CONFIG_SHEET, tables.league_config),
        (ROSTER_CONFIG_SHEET, tables.roster_config),
        (SCORING_PROFILES_SHEET, tables.scoring_profiles),
        (SCORING_POINTS_SHEET, tables.scoring_points),
    ):
        _clean_sheet(frame, sheet_name)

    issues: list[str] = []
    league_ids: list[str] = []
    identities: list[tuple[str, str, str]] = []
    statuses: list[str] = []
    clones: list[tuple[str, str]] = []
    for index, row in enumerate(_league_rows(tables), start=2):
        key = LeagueKey(
            _text_value(row.get("League ID")),
            _text_value(row.get("Game")),
            _text_value(row.get("Season")),
            _text_value(row.get("League Name")),
        )
        row_issues: list[str] = []
        _validate_key(key, row_issues)
        status = _text_value(row.get("Status")).title()
        if status not in LEAGUE_STATUSES:
            row_issues.append("Status must be Draft, Active, or Completed.")
        clone_id = _text_value(row.get("Cloned From League ID"))
        if clone_id == key.league_id and clone_id:
            row_issues.append("A league cannot be cloned from itself.")
        _created_datetime(row.get("Created UTC"), "Created UTC", row_issues)
        version = _positive_integer(row.get("Schema Version"), "Schema Version", row_issues)
        if version is not None and version != SCHEMA_VERSION:
            row_issues.append(f"Unsupported Schema Version {version}; expected {SCHEMA_VERSION}.")
        issues.extend(f"League Config row {index}: {issue}" for issue in row_issues)
        league_ids.append(key.league_id)
        identities.append(tuple(normalize_identity(value) for value in (key.game, key.season, key.league_name)))
        statuses.append(status)
        clones.append((key.league_id, clone_id))

    duplicates = sorted({value for value in league_ids if value and league_ids.count(value) > 1})
    if duplicates:
        issues.append("Duplicate League ID(s): " + ", ".join(duplicates) + ".")
    duplicate_identities = sorted(
        {identity for identity in identities if all(identity) and identities.count(identity) > 1}
    )
    if duplicate_identities:
        issues.append("Game, Season, and League Name must identify exactly one configured league.")
    if statuses.count("Active") > 1:
        issues.append("Only one configured league may be Active.")
    league_id_set = set(league_ids)
    for league_id, clone_id in clones:
        if require_clone_sources and clone_id and clone_id not in league_id_set:
            issues.append(f"League {league_id!r} references unknown cloned source {clone_id!r}.")

    roster_groups: dict[tuple[str, int], list[tuple[str, str, tuple[str, ...]]]] = {}
    for index, row in enumerate(tables.roster_config.to_dict("records"), start=2):
        row_issues: list[str] = []
        league_id = _required_text(row.get("League ID"), "League ID", row_issues)
        effective = _positive_integer(
            row.get("Effective From Round"), "Effective From Round", row_issues
        )
        driver = _required_text(row.get("Driver Name"), "Driver Name", row_issues)
        team = _required_text(row.get("Team Name"), "Team Name", row_issues)
        aliases = parse_ocr_aliases(row.get("OCR Aliases"))
        if league_id and league_id not in league_id_set:
            row_issues.append(f"League ID {league_id!r} is not defined in League Config.")
        if any(not normalize_identity(alias) for alias in aliases):
            row_issues.append("OCR Aliases contains an empty normalized alias.")
        issues.extend(f"Roster Config row {index}: {issue}" for issue in row_issues)
        if league_id and effective is not None:
            roster_groups.setdefault((league_id, effective), []).append((driver, team, aliases))

    for (league_id, effective), rows in roster_groups.items():
        drivers = [normalize_identity(driver) for driver, _, _ in rows]
        if len(rows) != len(set(drivers)):
            issues.append(
                f"Roster snapshot {league_id!r} round {effective} contains duplicate driver names."
            )
        canonical_to_driver = {
            normalize_identity(driver): driver for driver, _, _ in rows if normalize_identity(driver)
        }
        alias_owner: dict[str, str] = {}
        for driver, _, aliases in rows:
            driver_key = normalize_identity(driver)
            for alias in aliases:
                alias_key = normalize_identity(alias)
                if alias_key in canonical_to_driver and alias_key != driver_key:
                    issues.append(
                        f"Roster snapshot {league_id!r} round {effective} alias {alias!r} matches another driver."
                    )
                previous = alias_owner.get(alias_key)
                if previous is not None and previous != driver_key:
                    issues.append(
                        f"Roster snapshot {league_id!r} round {effective} alias {alias!r} is assigned twice."
                    )
                alias_owner[alias_key] = driver_key

    for league_id in league_id_set:
        effective_rounds = [
            effective for configured_id, effective in roster_groups if configured_id == league_id
        ]
        if effective_rounds and min(effective_rounds) != 1:
            issues.append(f"Configured league {league_id!r} needs a roster snapshot from round 1.")

    profile_ids: list[str] = []
    profile_rows: dict[str, dict[str, object]] = {}
    profile_keys: list[tuple[str, str, int]] = []
    for index, row in enumerate(tables.scoring_profiles.to_dict("records"), start=2):
        row_issues: list[str] = []
        profile_id = _required_text(row.get("Profile ID"), "Profile ID", row_issues)
        league_id = _required_text(row.get("League ID"), "League ID", row_issues)
        event_type = _text_value(row.get("Event Type")).upper()
        if event_type not in EVENT_TYPES:
            row_issues.append("Event Type must be R or SR.")
        effective = _positive_integer(
            row.get("Effective From Round"), "Effective From Round", row_issues
        )
        _nonnegative_number(row.get("Fastest Lap Bonus"), "Fastest Lap Bonus", row_issues)
        max_finish_raw = row.get("Fastest Lap Max Finish")
        if max_finish_raw is not None and not pd.isna(max_finish_raw) and str(max_finish_raw).strip():
            _positive_integer(max_finish_raw, "Fastest Lap Max Finish", row_issues)
        if league_id and league_id not in league_id_set:
            row_issues.append(f"League ID {league_id!r} is not defined in League Config.")
        issues.extend(f"Scoring Profiles row {index}: {issue}" for issue in row_issues)
        profile_ids.append(profile_id)
        profile_rows[profile_id] = row
        if league_id and event_type in EVENT_TYPES and effective is not None:
            profile_keys.append((league_id, event_type, effective))
    duplicate_profiles = sorted(
        {value for value in profile_ids if value and profile_ids.count(value) > 1}
    )
    if duplicate_profiles:
        issues.append("Duplicate Profile ID(s): " + ", ".join(duplicate_profiles) + ".")
    if len(profile_keys) != len(set(profile_keys)):
        issues.append("Each league may have only one scoring profile per event type and effective round.")

    points_by_profile: dict[str, list[tuple[int, float]]] = {}
    for index, row in enumerate(tables.scoring_points.to_dict("records"), start=2):
        row_issues: list[str] = []
        profile_id = _required_text(row.get("Profile ID"), "Profile ID", row_issues)
        position = _positive_integer(row.get("Position"), "Position", row_issues)
        points = _nonnegative_number(row.get("Points"), "Points", row_issues)
        if profile_id and profile_id not in set(profile_ids):
            row_issues.append(f"Profile ID {profile_id!r} is not defined in Scoring Profiles.")
        issues.extend(f"Scoring Points row {index}: {issue}" for issue in row_issues)
        if profile_id and position is not None and points is not None:
            points_by_profile.setdefault(profile_id, []).append((position, points))

    for profile_id in profile_ids:
        positions = [position for position, _ in points_by_profile.get(profile_id, [])]
        if not positions:
            issues.append(f"Scoring profile {profile_id!r} has no position points.")
            continue
        if len(positions) != len(set(positions)):
            issues.append(f"Scoring profile {profile_id!r} contains duplicate positions.")
        if set(positions) != set(range(1, max(positions) + 1)):
            issues.append(f"Scoring profile {profile_id!r} positions must be contiguous from 1.")
        profile_row = profile_rows.get(profile_id)
        if profile_row is not None:
            max_finish_raw = profile_row.get("Fastest Lap Max Finish")
            if (
                max_finish_raw is not None
                and not pd.isna(max_finish_raw)
                and str(max_finish_raw).strip()
                and positions
                and int(max_finish_raw) > max(positions)
            ):
                issues.append(
                    f"Scoring profile {profile_id!r} fastest-lap eligibility exceeds its positions."
                )

    for league_id in league_id_set:
        if league_id and not any(key[0] == league_id for key in roster_groups):
            issues.append(f"Configured league {league_id!r} has no roster snapshot.")
        if league_id and not any(
            key[0] == league_id and key[1] == "R" for key in profile_keys
        ):
            issues.append(f"Configured league {league_id!r} has no Race scoring profile.")
        race_rounds = [
            effective
            for configured_id, event_type, effective in profile_keys
            if configured_id == league_id and event_type == "R"
        ]
        if race_rounds and min(race_rounds) != 1:
            issues.append(f"Configured league {league_id!r} needs Race scoring from round 1.")

    if issues:
        raise LeagueConfigValidationError(issues)


def _setup_tables_unchecked(setup: LeagueSetup) -> ConfigTables:
    created = setup.created_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    league = pd.DataFrame(
        [[
            setup.key.league_id,
            setup.key.game,
            setup.key.season,
            setup.key.league_name,
            setup.status,
            setup.cloned_from_league_id,
            created,
            setup.schema_version,
        ]],
        columns=LEAGUE_CONFIG_COLUMNS,
    )
    roster = pd.DataFrame(
        [
            [
                row.league_id,
                row.effective_from_round,
                row.driver_name,
                row.team_name,
                serialize_ocr_aliases(row.ocr_aliases),
            ]
            for row in setup.roster
        ],
        columns=ROSTER_CONFIG_COLUMNS,
    )
    profiles = pd.DataFrame(
        [
            [
                row.profile_id,
                row.league_id,
                row.event_type.upper(),
                row.effective_from_round,
                float(row.fastest_lap_bonus),
                row.fastest_lap_max_finish,
            ]
            for row in setup.scoring_profiles
        ],
        columns=SCORING_PROFILE_COLUMNS,
    )
    points = pd.DataFrame(
        [[row.profile_id, row.position, float(row.points)] for row in setup.scoring_points],
        columns=SCORING_POINT_COLUMNS,
    )
    return ConfigTables(league, roster, profiles, points)


def config_tables_from_setup(setup: LeagueSetup) -> ConfigTables:
    validate_league_setup(setup)
    return _setup_tables_unchecked(setup)


def _active_roster_from_changes(
    roster: Sequence[RosterChange], league_id: str, round_number: int
) -> tuple[RosterChange, ...]:
    eligible = [
        row
        for row in roster
        if row.league_id == league_id and row.effective_from_round <= round_number
    ]
    if not eligible:
        raise LeagueConfigResolutionError(
            f"No roster snapshot is configured for league {league_id!r} at round {round_number}."
        )
    effective = max(row.effective_from_round for row in eligible)
    return tuple(
        sorted(
            (row for row in eligible if row.effective_from_round == effective),
            key=lambda row: normalize_identity(row.driver_name),
        )
    )


def _resolved_profile_from_setup(
    setup: LeagueSetup, event_type: str, round_number: int
) -> ResolvedScoringProfile:
    event_type = event_type.upper()
    eligible = [
        profile
        for profile in setup.scoring_profiles
        if profile.league_id == setup.key.league_id
        and profile.event_type.upper() == event_type
        and profile.effective_from_round <= round_number
    ]
    if not eligible:
        raise LeagueConfigResolutionError(
            f"No {event_type} scoring profile is configured at round {round_number}."
        )
    profile = max(eligible, key=lambda row: row.effective_from_round)
    points = tuple(
        sorted(
            (
                (point.position, float(point.points))
                for point in setup.scoring_points
                if point.profile_id == profile.profile_id
            ),
            key=lambda item: item[0],
        )
    )
    return ResolvedScoringProfile(
        profile.profile_id,
        profile.league_id,
        event_type,
        profile.effective_from_round,
        points,
        float(profile.fastest_lap_bonus),
        profile.fastest_lap_max_finish,
    )


def validate_league_setup(
    setup: LeagueSetup, *, existing: ConfigTables | None = None
) -> None:
    """Validate a complete setup, including every scheduled event snapshot."""

    issues: list[str] = []
    _validate_key(setup.key, issues)
    if setup.status not in LEAGUE_STATUSES:
        issues.append("Status must be Draft, Active, or Completed.")
    if setup.schema_version != SCHEMA_VERSION:
        issues.append(f"Schema Version must be {SCHEMA_VERSION}.")
    _created_datetime(setup.created_utc, "Created UTC", issues)
    if setup.cloned_from_league_id == setup.key.league_id and setup.cloned_from_league_id:
        issues.append("A league cannot be cloned from itself.")

    if not setup.calendar:
        issues.append("A league setup must contain at least one Calendar round.")
    round_numbers: list[int] = []
    ordered_calendar = sorted(setup.calendar, key=lambda row: row.round_number)
    for item in ordered_calendar:
        round_number = _positive_integer(item.round_number, "Calendar round", issues)
        if round_number is not None:
            round_numbers.append(round_number)
        if not isinstance(item.date, date):
            issues.append(f"Calendar round {item.round_number} needs a valid date.")
        _required_text(item.gp_name, f"Calendar round {item.round_number} GP Name", issues)
        _required_text(item.circuit, f"Calendar round {item.round_number} Circuit", issues)
        if item.status not in {"Upcoming", "Done", "TBD"}:
            issues.append(
                f"Calendar round {item.round_number} Status must be Upcoming, Done, or TBD."
            )
        if item.time_lisbon is not None and not isinstance(item.time_lisbon, time):
            issues.append(f"Calendar round {item.round_number} has an invalid Lisbon time.")
        if not isinstance(item.has_sprint, bool):
            issues.append(
                f"Calendar round {item.round_number} Has Sprint must be a boolean."
            )
    if round_numbers and set(round_numbers) != set(range(1, max(round_numbers) + 1)):
        issues.append("Calendar rounds must be unique and contiguous from 1.")
    dates = [item.date for item in ordered_calendar if isinstance(item.date, date)]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        issues.append("Calendar dates must be unique and chronological by round.")

    if any(row.league_id != setup.key.league_id for row in setup.roster):
        issues.append("Every roster row must use the setup League ID.")
    if any(row.league_id != setup.key.league_id for row in setup.scoring_profiles):
        issues.append("Every scoring profile must use the setup League ID.")

    try:
        validate_config_tables(
            _setup_tables_unchecked(setup), require_clone_sources=False
        )
    except LeagueConfigValidationError as exc:
        issues.extend(exc.issues)

    calendar_round_set = set(round_numbers)
    effective_roster_rounds = {row.effective_from_round for row in setup.roster}
    effective_scoring_rounds = {row.effective_from_round for row in setup.scoring_profiles}
    invalid_roster_rounds = sorted(effective_roster_rounds - calendar_round_set)
    invalid_scoring_rounds = sorted(effective_scoring_rounds - calendar_round_set)
    if invalid_roster_rounds:
        issues.append(
            "Roster effective round(s) are outside the Calendar: "
            + ", ".join(map(str, invalid_roster_rounds))
            + "."
        )
    if invalid_scoring_rounds:
        issues.append(
            "Scoring effective round(s) are outside the Calendar: "
            + ", ".join(map(str, invalid_scoring_rounds))
            + "."
        )
    if setup.calendar and 1 not in effective_roster_rounds:
        issues.append("Roster Config must contain a complete snapshot effective from round 1.")

    for event in ordered_calendar:
        try:
            roster = _active_roster_from_changes(
                setup.roster, setup.key.league_id, event.round_number
            )
        except LeagueConfigResolutionError as exc:
            issues.append(str(exc))
            continue
        event_types = ("R", "SR") if event.has_sprint else ("R",)
        for event_type in event_types:
            try:
                profile = _resolved_profile_from_setup(setup, event_type, event.round_number)
            except LeagueConfigResolutionError as exc:
                issues.append(str(exc))
                continue
            expected_positions = set(range(1, len(roster) + 1))
            if set(profile.points) != expected_positions:
                issues.append(
                    f"{event_type} scoring at round {event.round_number} must cover positions 1-{len(roster)} exactly."
                )
            if (
                profile.fastest_lap_max_finish is not None
                and profile.fastest_lap_max_finish > len(roster)
            ):
                issues.append(
                    f"{event_type} fastest-lap eligibility at round {event.round_number} exceeds the roster size."
                )

    if existing is not None:
        try:
            validate_config_tables(existing)
        except LeagueConfigValidationError as exc:
            issues.extend(f"Existing configuration: {issue}" for issue in exc.issues)
        else:
            existing_rows = existing.league_config.copy()
            same_id = existing_rows[
                existing_rows["League ID"].astype(str).eq(setup.key.league_id)
            ]
            if not same_id.empty:
                old = same_id.iloc[0]
                old_identity = (
                    str(old["Game"]).strip(),
                    str(old["Season"]).strip(),
                    str(old["League Name"]).strip(),
                )
                if old_identity != (setup.key.game, setup.key.season, setup.key.league_name):
                    issues.append("An existing League ID cannot be assigned a different identity.")
            else:
                identity = tuple(
                    normalize_identity(value)
                    for value in (setup.key.game, setup.key.season, setup.key.league_name)
                )
                for row in existing_rows.to_dict("records"):
                    candidate = tuple(
                        normalize_identity(row[column])
                        for column in ("Game", "Season", "League Name")
                    )
                    if candidate == identity:
                        issues.append("Game, Season, and League Name already belong to another League ID.")
                        break
            if setup.cloned_from_league_id and setup.cloned_from_league_id not in set(
                existing_rows["League ID"].astype(str)
            ):
                issues.append("Cloned From League ID is not present in the existing configuration.")
            other_active = existing_rows[
                existing_rows["League ID"].astype(str).ne(setup.key.league_id)
                & existing_rows["Status"].astype(str).str.casefold().eq("active")
            ]
            if setup.status == "Active" and not other_active.empty:
                issues.append("Another configured league is already Active.")

    if issues:
        raise LeagueConfigValidationError(issues)


def merge_setup_into_config_tables(existing: ConfigTables, setup: LeagueSetup) -> ConfigTables:
    """Replace one league's config rows while preserving every other league."""

    validate_league_setup(setup, existing=existing)
    incoming = _setup_tables_unchecked(setup)
    league_id = setup.key.league_id
    old_profile_ids = set(
        existing.scoring_profiles.loc[
            existing.scoring_profiles["League ID"].astype(str).eq(league_id), "Profile ID"
        ].astype(str)
    )
    retained = ConfigTables(
        existing.league_config[
            ~existing.league_config["League ID"].astype(str).eq(league_id)
        ].copy(),
        existing.roster_config[
            ~existing.roster_config["League ID"].astype(str).eq(league_id)
        ].copy(),
        existing.scoring_profiles[
            ~existing.scoring_profiles["League ID"].astype(str).eq(league_id)
        ].copy(),
        existing.scoring_points[
            ~existing.scoring_points["Profile ID"].astype(str).isin(old_profile_ids)
        ].copy(),
    )
    merged = ConfigTables(
        pd.concat([retained.league_config, incoming.league_config], ignore_index=True),
        pd.concat([retained.roster_config, incoming.roster_config], ignore_index=True),
        pd.concat([retained.scoring_profiles, incoming.scoring_profiles], ignore_index=True),
        pd.concat([retained.scoring_points, incoming.scoring_points], ignore_index=True),
    )
    validate_config_tables(merged)
    return merged


def _tables_with_roster_snapshot_unchecked(
    existing: ConfigTables, update: RosterSnapshotUpdate
) -> ConfigTables:
    roster_rows = pd.DataFrame(
        [
            [
                row.league_id,
                row.effective_from_round,
                row.driver_name,
                row.team_name,
                serialize_ocr_aliases(row.ocr_aliases),
            ]
            for row in update.complete_roster
        ],
        columns=ROSTER_CONFIG_COLUMNS,
    )
    profile_rows = pd.DataFrame(
        [
            [
                row.profile_id,
                row.league_id,
                row.event_type.upper(),
                row.effective_from_round,
                float(row.fastest_lap_bonus),
                row.fastest_lap_max_finish,
            ]
            for row in update.scoring_profiles
        ],
        columns=SCORING_PROFILE_COLUMNS,
    )
    point_rows = pd.DataFrame(
        [[row.profile_id, row.position, float(row.points)] for row in update.scoring_points],
        columns=SCORING_POINT_COLUMNS,
    )
    return ConfigTables(
        existing.league_config.copy(),
        pd.concat([existing.roster_config, roster_rows], ignore_index=True),
        pd.concat([existing.scoring_profiles, profile_rows], ignore_index=True),
        pd.concat([existing.scoring_points, point_rows], ignore_index=True),
    )


def validate_roster_snapshot_update(
    existing: ConfigTables, update: RosterSnapshotUpdate
) -> None:
    """Validate a non-destructive future roster/scoring snapshot."""

    validate_config_tables(existing)
    issues: list[str] = []
    league_id = str(update.league_id).strip()
    target_count = int(
        existing.league_config["League ID"].astype(str).eq(league_id).sum()
    )
    if target_count != 1:
        issues.append("Roster snapshot target League ID must exist uniquely.")
    else:
        target = existing.league_config[
            existing.league_config["League ID"].astype(str).eq(league_id)
        ].iloc[0]
        if str(target["Status"]).strip().casefold() != "active":
            issues.append(
                "Roster and scoring snapshots may be added only to an Active league."
            )
    effective = _positive_integer(
        update.effective_from_round, "Effective From Round", issues
    )
    configured_rounds = pd.to_numeric(
        existing.roster_config.loc[
            existing.roster_config["League ID"].astype(str).eq(league_id),
            "Effective From Round",
        ],
        errors="coerce",
    ).dropna()
    if effective is not None and not configured_rounds.empty:
        if effective in set(configured_rounds.astype(int)):
            issues.append("A roster snapshot already exists at this effective round.")
        if effective <= int(configured_rounds.max()):
            issues.append("A roster snapshot update must start after every existing snapshot.")
    if not update.complete_roster:
        issues.append("Roster snapshot update must contain a complete non-empty roster.")
    for row in update.complete_roster:
        if row.league_id != league_id:
            issues.append("Every roster update row must use the target League ID.")
        if effective is not None and row.effective_from_round != effective:
            issues.append("Every roster update row must use the update effective round.")
        _required_text(row.driver_name, "Driver Name", issues)
        _required_text(row.team_name, "Team Name", issues)
    driver_keys = [normalize_identity(row.driver_name) for row in update.complete_roster]
    if len(driver_keys) != len(set(driver_keys)):
        issues.append("The complete roster snapshot contains duplicate driver names.")

    update_profile_ids = {profile.profile_id for profile in update.scoring_profiles}
    if update.scoring_points and not update.scoring_profiles:
        issues.append("Scoring Points cannot be supplied without update Scoring Profiles.")
    for profile in update.scoring_profiles:
        if profile.league_id != league_id:
            issues.append("Every update scoring profile must use the target League ID.")
        if effective is not None and profile.effective_from_round != effective:
            issues.append("Every update scoring profile must use the update effective round.")
    if any(point.profile_id not in update_profile_ids for point in update.scoring_points):
        issues.append("Every update Scoring Point must reference an update Scoring Profile.")

    if issues:
        raise LeagueConfigValidationError(issues)
    merged = _tables_with_roster_snapshot_unchecked(existing, update)
    try:
        validate_config_tables(merged)
    except LeagueConfigValidationError as exc:
        issues.extend(exc.issues)
    if effective is not None:
        event_types = sorted(
            set(
                merged.scoring_profiles.loc[
                    merged.scoring_profiles["League ID"].astype(str).eq(league_id),
                    "Event Type",
                ].astype(str).str.upper()
            )
        )
        if "R" not in event_types:
            issues.append("The target league needs Race scoring at the roster effective round.")
        for event_type in event_types:
            try:
                resolve_scoring_profile(
                    merged,
                    league_id,
                    event_type,
                    effective,
                    len(update.complete_roster),
                )
            except LeagueConfigError as exc:
                issues.append(str(exc))
    if issues:
        raise LeagueConfigValidationError(issues)


def config_tables_with_roster_snapshot(
    existing: ConfigTables, update: RosterSnapshotUpdate
) -> ConfigTables:
    validate_roster_snapshot_update(existing, update)
    merged = _tables_with_roster_snapshot_unchecked(existing, update)
    validate_config_tables(merged)
    return merged


def roster_snapshot_update_digest(
    existing: ConfigTables, update: RosterSnapshotUpdate
) -> str:
    validate_roster_snapshot_update(existing, update)
    payload = {
        "league_id": update.league_id,
        "effective_from_round": update.effective_from_round,
        "complete_roster": [
            {
                "league_id": row.league_id,
                "effective_from_round": row.effective_from_round,
                "driver_name": row.driver_name,
                "team_name": row.team_name,
                "ocr_aliases": sorted(row.ocr_aliases, key=normalize_identity),
            }
            for row in sorted(
                update.complete_roster, key=lambda item: normalize_identity(item.driver_name)
            )
        ],
        "scoring_profiles": [
            {
                "profile_id": row.profile_id,
                "league_id": row.league_id,
                "event_type": row.event_type.upper(),
                "effective_from_round": row.effective_from_round,
                "fastest_lap_bonus": row.fastest_lap_bonus,
                "fastest_lap_max_finish": row.fastest_lap_max_finish,
            }
            for row in sorted(
                update.scoring_profiles,
                key=lambda item: (item.event_type.upper(), item.profile_id),
            )
        ],
        "scoring_points": [
            {
                "profile_id": row.profile_id,
                "position": row.position,
                "points": row.points,
            }
            for row in sorted(
                update.scoring_points, key=lambda item: (item.profile_id, item.position)
            )
        ],
    }
    return _digest_payload(payload)


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if pd.isna(value):
        return None
    return str(value).strip()


def _digest_payload(payload: object) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def league_setup_digest(setup: LeagueSetup) -> str:
    validate_league_setup(setup)
    payload = {
        "key": {
            "league_id": setup.key.league_id,
            "game": setup.key.game,
            "season": setup.key.season,
            "league_name": setup.key.league_name,
        },
        "status": setup.status,
        "cloned_from_league_id": setup.cloned_from_league_id,
        "created_utc": _json_value(setup.created_utc),
        "schema_version": setup.schema_version,
        "calendar": [
            {
                "round_number": row.round_number,
                "date": row.date.isoformat(),
                "gp_name": row.gp_name,
                "circuit": row.circuit,
                "status": row.status,
                "time_lisbon": row.time_lisbon.isoformat() if row.time_lisbon else None,
                "has_sprint": row.has_sprint,
            }
            for row in sorted(setup.calendar, key=lambda item: item.round_number)
        ],
        "roster": [
            {
                "league_id": row.league_id,
                "effective_from_round": row.effective_from_round,
                "driver_name": row.driver_name,
                "team_name": row.team_name,
                "ocr_aliases": sorted(row.ocr_aliases, key=normalize_identity),
            }
            for row in sorted(
                setup.roster,
                key=lambda item: (
                    item.effective_from_round,
                    normalize_identity(item.driver_name),
                ),
            )
        ],
        "scoring_profiles": [
            {
                "profile_id": row.profile_id,
                "league_id": row.league_id,
                "event_type": row.event_type.upper(),
                "effective_from_round": row.effective_from_round,
                "fastest_lap_bonus": row.fastest_lap_bonus,
                "fastest_lap_max_finish": row.fastest_lap_max_finish,
            }
            for row in sorted(
                setup.scoring_profiles,
                key=lambda item: (item.event_type.upper(), item.effective_from_round),
            )
        ],
        "scoring_points": [
            {
                "profile_id": row.profile_id,
                "position": row.position,
                "points": row.points,
            }
            for row in sorted(
                setup.scoring_points, key=lambda item: (item.profile_id, item.position)
            )
        ],
    }
    return _digest_payload(payload)


def config_tables_digest(tables: ConfigTables) -> str:
    validate_config_tables(tables)
    payload: dict[str, list[dict[str, object]]] = {}
    for sheet_name, frame in (
        (LEAGUE_CONFIG_SHEET, tables.league_config),
        (ROSTER_CONFIG_SHEET, tables.roster_config),
        (SCORING_PROFILES_SHEET, tables.scoring_profiles),
        (SCORING_POINTS_SHEET, tables.scoring_points),
    ):
        records = [
            {column: _json_value(row[column]) for column in _SHEET_COLUMNS[sheet_name]}
            for row in frame.to_dict("records")
        ]
        payload[sheet_name] = sorted(
            records,
            key=lambda record: json.dumps(record, ensure_ascii=False, sort_keys=True),
        )
    return _digest_payload(payload)


def configured_league_keys(tables: ConfigTables) -> tuple[LeagueKey, ...]:
    validate_config_tables(tables)
    keys = [
        LeagueKey(
            _text_value(row["League ID"]),
            _text_value(row["Game"]),
            _text_value(row["Season"]),
            _text_value(row["League Name"]),
        )
        for row in tables.league_config.to_dict("records")
    ]
    return tuple(sorted(keys, key=lambda key: (key.season, key.game, key.league_name, key.league_id)))


def configured_league_status(tables: ConfigTables, league_id: str) -> str:
    """Return one configured league status, rejecting a missing/ambiguous ID."""

    validate_config_tables(tables)
    normalized_id = _text_value(league_id)
    selected = tables.league_config[
        tables.league_config["League ID"].astype(str).str.strip().eq(normalized_id)
    ]
    if len(selected) != 1:
        raise LeagueConfigResolutionError(
            "The configured League ID was not found uniquely."
        )
    return _text_value(selected.iloc[0]["Status"]).title()


def require_active_configured_league(
    tables: ConfigTables, league_id: str
) -> LeagueKey:
    """Resolve one configured key only while its authoritative status is Active."""

    status = configured_league_status(tables, league_id)
    if status != "Active":
        raise LeagueConfigResolutionError(
            f"Configured league {league_id!r} is {status or 'not active'}; "
            "only an Active league may receive new results or snapshots."
        )
    selected = [
        key for key in configured_league_keys(tables) if key.league_id == league_id
    ]
    if len(selected) != 1:
        raise LeagueConfigResolutionError(
            "The configured League ID was not found uniquely."
        )
    return selected[0]


def _fallback_roster_row(value: object, league_id: str, round_number: int) -> RosterChange:
    if isinstance(value, RosterChange):
        return RosterChange(
            league_id,
            round_number,
            value.driver_name,
            value.team_name,
            value.ocr_aliases,
        )
    if isinstance(value, Mapping):
        driver = value.get("Driver Name", value.get("Driver", ""))
        team = value.get("Team Name", value.get("Team", ""))
        aliases = parse_ocr_aliases(value.get("OCR Aliases", ""))
    else:
        driver = getattr(value, "driver_name", getattr(value, "driver", ""))
        team = getattr(value, "team_name", getattr(value, "team", ""))
        aliases = tuple(getattr(value, "ocr_aliases", ()))
    return RosterChange(
        league_id, round_number, _text_value(driver), _text_value(team), aliases
    )


def resolve_roster_snapshot(
    tables: ConfigTables,
    league_id: str,
    round_number: int,
    legacy_fallback: LegacyRosterFallback | None = None,
) -> tuple[RosterChange, ...]:
    validate_config_tables(tables)
    round_number = int(round_number)
    configured = tables.roster_config[
        tables.roster_config["League ID"].astype(str).eq(str(league_id))
        & pd.to_numeric(
            tables.roster_config["Effective From Round"], errors="coerce"
        ).le(round_number)
    ].copy()
    if not configured.empty:
        effective = int(
            pd.to_numeric(configured["Effective From Round"], errors="raise").max()
        )
        configured = configured[
            pd.to_numeric(configured["Effective From Round"], errors="raise").eq(effective)
        ]
        return tuple(
            sorted(
                (
                    RosterChange(
                        _text_value(row["League ID"]),
                        effective,
                        _text_value(row["Driver Name"]),
                        _text_value(row["Team Name"]),
                        parse_ocr_aliases(row["OCR Aliases"]),
                    )
                    for row in configured.to_dict("records")
                ),
                key=lambda row: normalize_identity(row.driver_name),
            )
        )
    if legacy_fallback is None:
        raise LeagueConfigResolutionError(
            f"No roster snapshot is configured for league {league_id!r} at round {round_number}."
        )
    rows = tuple(
        _fallback_roster_row(value, str(league_id), round_number)
        for value in legacy_fallback(round_number)
    )
    if not rows:
        raise LeagueConfigResolutionError("The legacy roster fallback returned no drivers.")
    drivers = [normalize_identity(row.driver_name) for row in rows]
    if any(not row.driver_name or not row.team_name for row in rows) or len(drivers) != len(set(drivers)):
        raise LeagueConfigResolutionError("The legacy roster fallback is incomplete or contains duplicates.")
    return tuple(sorted(rows, key=lambda row: normalize_identity(row.driver_name)))


def resolve_scoring_profile(
    tables: ConfigTables,
    league_id: str,
    event_type: str,
    round_number: int,
    grid_size: int,
    legacy_fallback: LegacyScoringFallback | None = None,
) -> ResolvedScoringProfile:
    validate_config_tables(tables)
    event_type = str(event_type).upper()
    if event_type not in EVENT_TYPES:
        raise LeagueConfigResolutionError("Event Type must be R or SR.")
    profiles = tables.scoring_profiles[
        tables.scoring_profiles["League ID"].astype(str).eq(str(league_id))
        & tables.scoring_profiles["Event Type"].astype(str).str.upper().eq(event_type)
        & pd.to_numeric(
            tables.scoring_profiles["Effective From Round"], errors="coerce"
        ).le(int(round_number))
    ].copy()
    if not profiles.empty:
        effective = int(
            pd.to_numeric(profiles["Effective From Round"], errors="raise").max()
        )
        profile_row = profiles[
            pd.to_numeric(profiles["Effective From Round"], errors="raise").eq(effective)
        ].iloc[0]
        profile_id = str(profile_row["Profile ID"]).strip()
        point_rows = tables.scoring_points[
            tables.scoring_points["Profile ID"].astype(str).eq(profile_id)
        ]
        points = tuple(
            sorted(
                (
                    (int(row["Position"]), float(row["Points"]))
                    for row in point_rows.to_dict("records")
                ),
                key=lambda item: item[0],
            )
        )
        if set(dict(points)) != set(range(1, int(grid_size) + 1)):
            raise LeagueConfigResolutionError(
                f"Configured {event_type} scoring does not cover positions 1-{grid_size} exactly."
            )
        max_finish_raw = profile_row["Fastest Lap Max Finish"]
        max_finish = (
            None
            if max_finish_raw is None or pd.isna(max_finish_raw) or str(max_finish_raw).strip() == ""
            else int(max_finish_raw)
        )
        return ResolvedScoringProfile(
            profile_id,
            str(league_id),
            event_type,
            effective,
            points,
            float(profile_row["Fastest Lap Bonus"]),
            max_finish,
        )
    if legacy_fallback is None:
        raise LeagueConfigResolutionError(
            f"No {event_type} scoring profile is configured at round {round_number}."
        )
    fallback = legacy_fallback(event_type, int(round_number), int(grid_size))
    if isinstance(fallback, ResolvedScoringProfile):
        resolved = fallback
    else:
        points = tuple(sorted((int(position), float(points)) for position, points in fallback.items()))
        resolved = ResolvedScoringProfile(
            "legacy",
            str(league_id),
            event_type,
            1,
            points,
            0.0,
            None,
        )
    if set(resolved.points) != set(range(1, int(grid_size) + 1)):
        raise LeagueConfigResolutionError(
            f"Legacy {event_type} scoring does not cover positions 1-{grid_size} exactly."
        )
    return resolved


def _new_profile_id(
    league_id: str, event_type: str, used: set[str], effective_from_round: int = 1
) -> str:
    base = f"{league_id}:{event_type}:{effective_from_round}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}:{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def clone_configured_league(
    tables: ConfigTables,
    *,
    source_league_id: str,
    new_key: LeagueKey,
    calendar: Sequence[CalendarRound],
    created_utc: datetime | None = None,
    status: str = "Draft",
) -> LeagueSetup:
    """Clone the latest configured roster and each latest scoring profile."""

    validate_config_tables(tables)
    source_rows = tables.league_config[
        tables.league_config["League ID"].astype(str).eq(str(source_league_id))
    ]
    if len(source_rows) != 1:
        raise LeagueConfigResolutionError("The configured clone source was not found uniquely.")
    source_roster = tables.roster_config[
        tables.roster_config["League ID"].astype(str).eq(str(source_league_id))
    ]
    latest_round = int(
        pd.to_numeric(source_roster["Effective From Round"], errors="raise").max()
    )
    current_roster = resolve_roster_snapshot(tables, source_league_id, latest_round)
    roster = tuple(
        RosterChange(new_key.league_id, 1, row.driver_name, row.team_name, row.ocr_aliases)
        for row in current_roster
    )

    used_ids = set(tables.scoring_profiles["Profile ID"].astype(str))
    profiles: list[ScoringProfile] = []
    points: list[ScoringPoint] = []
    for event_type in sorted(EVENT_TYPES):
        candidates = tables.scoring_profiles[
            tables.scoring_profiles["League ID"].astype(str).eq(str(source_league_id))
            & tables.scoring_profiles["Event Type"].astype(str).str.upper().eq(event_type)
        ]
        if candidates.empty:
            continue
        effective = int(
            pd.to_numeric(candidates["Effective From Round"], errors="raise").max()
        )
        source_profile = candidates[
            pd.to_numeric(candidates["Effective From Round"], errors="raise").eq(effective)
        ].iloc[0]
        profile_id = _new_profile_id(new_key.league_id, event_type, used_ids)
        max_finish_raw = source_profile["Fastest Lap Max Finish"]
        max_finish = None if pd.isna(max_finish_raw) else int(max_finish_raw)
        profiles.append(
            ScoringProfile(
                profile_id,
                new_key.league_id,
                event_type,
                1,
                float(source_profile["Fastest Lap Bonus"]),
                max_finish,
            )
        )
        source_points = tables.scoring_points[
            tables.scoring_points["Profile ID"].astype(str).eq(
                str(source_profile["Profile ID"])
            )
        ]
        points.extend(
            ScoringPoint(profile_id, int(row["Position"]), float(row["Points"]))
            for row in source_points.to_dict("records")
        )
    setup = LeagueSetup(
        new_key,
        tuple(calendar),
        roster,
        tuple(profiles),
        tuple(points),
        status,
        str(source_league_id),
        created_utc or _utc_now(),
        SCHEMA_VERSION,
    )
    validate_league_setup(setup, existing=tables)
    return setup


def _legacy_selected(
    standings: pd.DataFrame, game: str, season: str, league: str
) -> pd.DataFrame:
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    required = {"Game", season_column, "League Name", "Round", "Driver", "Team", "Finish Pos", "Points"}
    missing = sorted(required - set(standings.columns))
    if missing:
        raise LeagueConfigResolutionError(
            "Legacy standings are missing columns: " + ", ".join(missing) + "."
        )
    selected = standings[
        standings["Game"].astype(str).eq(str(game))
        & standings[season_column].astype(str).eq(str(season))
        & standings["League Name"].astype(str).eq(str(league))
    ].copy()
    if "IsSeasonFinal" in selected.columns:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    return selected


def _legacy_latest_roster(selected: pd.DataFrame) -> tuple[tuple[str, str], ...]:
    event_types = (
        selected["Type"].fillna("R").astype(str).str.upper()
        if "Type" in selected.columns
        else pd.Series("R", index=selected.index)
    )
    races = selected[event_types.eq("R")].copy()
    candidates: list[tuple[int, int, pd.DataFrame]] = []
    for round_value, event in races.groupby("Round", dropna=False, sort=False):
        clean = event.dropna(subset=["Driver", "Team", "Finish Pos"]).copy()
        positions = pd.to_numeric(clean["Finish Pos"], errors="coerce")
        if positions.isna().any():
            continue
        position_set = set(positions.astype(int))
        drivers = clean["Driver"].astype(str).str.strip()
        if (
            len(clean)
            and drivers.nunique() == len(clean)
            and position_set == set(range(1, len(clean) + 1))
        ):
            candidates.append((len(clean), int(round_value), clean.assign(_Position=positions)))
    if not candidates:
        raise LeagueConfigResolutionError("Legacy standings contain no complete main-race roster.")
    maximum_grid = max(size for size, _, _ in candidates)
    _, _, latest = max(
        (item for item in candidates if item[0] == maximum_grid), key=lambda item: item[1]
    )
    return tuple(
        (str(row.Driver).strip(), str(row.Team).strip())
        for row in latest.sort_values("_Position").itertuples(index=False)
    )


def _legacy_points(
    selected: pd.DataFrame, event_type: str, grid_size: int
) -> dict[int, float] | None:
    event_types = (
        selected["Type"].fillna("R").astype(str).str.upper()
        if "Type" in selected.columns
        else pd.Series("R", index=selected.index)
    )
    event_rows = selected[event_types.eq(event_type)].copy()
    if event_rows.empty:
        return None
    event_rows["_Position"] = pd.to_numeric(event_rows["Finish Pos"], errors="coerce")
    event_rows["_Points"] = pd.to_numeric(event_rows["Points"], errors="coerce")
    profile: dict[int, float] = {}
    for position in range(1, grid_size + 1):
        values = event_rows.loc[event_rows["_Position"].eq(position), "_Points"].dropna().unique()
        if len(values) != 1:
            raise LeagueConfigResolutionError(
                f"Legacy {event_type} points are not uniquely determined at position {position}."
            )
        profile[position] = float(values[0])
    return profile


def clone_legacy_league(
    standings: pd.DataFrame,
    *,
    source_game: str,
    source_season: str,
    source_league: str,
    new_key: LeagueKey,
    calendar: Sequence[CalendarRound],
    race_points: Mapping[int, float] | None = None,
    sprint_points: Mapping[int, float] | None = None,
    fastest_lap_rules: Mapping[str, tuple[float, int | None]] | None = None,
    created_utc: datetime | None = None,
    status: str = "Draft",
) -> LeagueSetup:
    """Clone the latest complete legacy Race roster and verified point maps."""

    selected = _legacy_selected(
        standings, source_game, source_season, source_league
    )
    roster_source = _legacy_latest_roster(selected)
    roster = tuple(
        RosterChange(new_key.league_id, 1, driver, team)
        for driver, team in roster_source
    )
    grid_size = len(roster)
    rule_map = {str(key).upper(): value for key, value in (fastest_lap_rules or {}).items()}
    used_ids: set[str] = set()
    profiles: list[ScoringProfile] = []
    points: list[ScoringPoint] = []
    supplied = {"R": race_points, "SR": sprint_points}
    for event_type in ("R", "SR"):
        point_map = supplied[event_type]
        if point_map is None:
            point_map = _legacy_points(selected, event_type, grid_size)
        if point_map is None:
            continue
        normalized = {int(position): float(value) for position, value in point_map.items()}
        if set(normalized) != set(range(1, grid_size + 1)):
            raise LeagueConfigResolutionError(
                f"{event_type} scoring must cover positions 1-{grid_size} exactly."
            )
        bonus, max_finish = rule_map.get(event_type, (0.0, None))
        profile_id = _new_profile_id(new_key.league_id, event_type, used_ids)
        profiles.append(
            ScoringProfile(
                profile_id,
                new_key.league_id,
                event_type,
                1,
                float(bonus),
                max_finish,
            )
        )
        points.extend(
            ScoringPoint(profile_id, position, value)
            for position, value in sorted(normalized.items())
        )
    setup = LeagueSetup(
        new_key,
        tuple(calendar),
        roster,
        tuple(profiles),
        tuple(points),
        status,
        "",
        created_utc or _utc_now(),
        SCHEMA_VERSION,
    )
    validate_league_setup(setup)
    return setup


def _lap_milliseconds(value: object) -> int | None:
    text = str(value or "").strip().upper()
    if text in _NO_LAP_VALUES:
        return None
    match = _FASTEST_LAP_RE.fullmatch(text)
    if match is None:
        raise LeagueConfigResolutionError(
            f"Fastest Lap {value!r} is missing or is not canonical M:SS.mmm text."
        )
    return (int(match.group(1)) * 60 + int(match.group(2))) * 1000 + int(match.group(3))


def derive_fastest_lap_bonus(
    rows: Iterable[Mapping[str, object]], profile: ResolvedScoringProfile
) -> FastestLapAward:
    """Return the unique fastest eligible reviewed lap for a configured bonus.

    Blank or malformed eligible laps and exact ties block the award.  Explicit
    no-lap statuses such as ``N/A`` and ``DNF`` are known non-candidates.
    """

    if profile.fastest_lap_bonus <= 0:
        return FastestLapAward(None, None, None, 0.0)
    candidates: list[tuple[int, str, int, str]] = []
    drivers: set[str] = set()
    positions: set[int] = set()
    for index, row in enumerate(rows, start=1):
        driver = _text_value(row.get("Driver", row.get("Driver Name", "")))
        position_value = pd.to_numeric(row.get("Position"), errors="coerce")
        if not driver or pd.isna(position_value) or not float(position_value).is_integer():
            raise LeagueConfigResolutionError(
                f"Reviewed row {index} needs a canonical Driver and Position for fastest-lap scoring."
            )
        position = int(position_value)
        driver_key = normalize_identity(driver)
        if driver_key in drivers or position in positions:
            raise LeagueConfigResolutionError(
                "Reviewed fastest-lap rows contain a duplicate driver or position."
            )
        drivers.add(driver_key)
        positions.add(position)
        if (
            profile.fastest_lap_max_finish is not None
            and position > profile.fastest_lap_max_finish
        ):
            continue
        raw_lap = row.get("Fastest Lap")
        if raw_lap is None or not str(raw_lap).strip():
            raise LeagueConfigResolutionError(
                f"Eligible driver {driver!r} is missing a confirmed fastest lap."
            )
        milliseconds = _lap_milliseconds(raw_lap)
        if milliseconds is not None:
            candidates.append((milliseconds, driver, position, str(raw_lap).strip()))
    if not candidates:
        raise LeagueConfigResolutionError(
            "No eligible driver has a canonical fastest lap for the configured bonus."
        )
    fastest = min(milliseconds for milliseconds, _, _, _ in candidates)
    winners = [candidate for candidate in candidates if candidate[0] == fastest]
    if len(winners) != 1:
        raise LeagueConfigResolutionError(
            "The fastest eligible lap is tied; the bonus cannot be assigned automatically."
        )
    _, driver, position, lap_time = winners[0]
    return FastestLapAward(
        driver, position, lap_time, float(profile.fastest_lap_bonus)
    )
