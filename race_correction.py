"""Preservation-oriented corrections for one previously published event.

Corrections deliberately operate in place.  Replacements rewrite only A:L of
the exact rows already owned by the selected event; undos clear those cells
without deleting worksheet rows.  Later results, helper columns, formulas,
helper ranges, comments, and every unrelated OOXML package part therefore keep
their existing addresses and bytes.

The caller supplies the authoritative event roster and position scoring.  The
protected Admin configuration can provide those values once league setup is
integrated; this module never derives new identities from screenshots.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Mapping, Sequence
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd

import dashboard_core as core
import race_import as race
import race_metadata
import race_workbook as workbook


_RESULT_COLUMNS = tuple("ABCDEFGHIJKL")
_RESULT_HEADERS = (
    "Game",
    "Season",
    "League Name",
    "Round",
    "Type",
    "GP Name",
    "Driver",
    "Team",
    "Finish Pos",
    "Points",
    "Time",
    "Fastest Lap",
)
_CELL_PATTERN = re.compile(
    rb'<c\b(?=[^>]*\br="([A-Z]+)(\d+)")[^>]*(?:/>|>.*?</c>)',
    re.DOTALL,
)
_MAIN_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class CorrectionAction(str, Enum):
    """Supported audited changes to an existing event."""

    REPLACE = "replace"
    UNDO = "undo"


class EventCorrectionError(workbook.WorkbookUpdateError):
    """Raised when an existing event cannot be corrected safely."""


class EventNotFoundError(EventCorrectionError):
    """Raised when the selected event is absent or not one complete result."""


@dataclass(frozen=True)
class ExistingResultRow:
    excel_row: int
    position: int
    driver: str
    team: str
    points: float
    time: str | None
    fastest_lap: str | None


@dataclass(frozen=True)
class EventSnapshot:
    metadata: workbook.RaceMetadata
    rows: tuple[ExistingResultRow, ...]
    calendar_excel_row: int
    calendar_status: str
    digest: str


@dataclass(frozen=True)
class CorrectionResult:
    action: CorrectionAction
    affected_excel_rows: tuple[int, ...]
    rows_replaced: int
    rows_removed: int
    backup_path: Path
    calendar_updated: bool
    workbook_sha256: str


def _normalized_metadata(metadata: workbook.RaceMetadata) -> workbook.RaceMetadata:
    values = {
        "game": str(metadata.game or "").strip(),
        "season": str(metadata.season or "").strip(),
        "league": str(metadata.league or "").strip(),
        "gp_name": str(metadata.gp_name or "").strip(),
    }
    if not all(values.values()):
        raise EventCorrectionError("The selected event identity is incomplete.")
    try:
        round_number = int(metadata.round_number)
    except (TypeError, ValueError) as exc:
        raise EventCorrectionError("The selected event round is invalid.") from exc
    if round_number <= 0:
        raise EventCorrectionError("The selected event round is invalid.")
    event_type = str(metadata.event_type or "").strip().upper()
    if event_type not in {"R", "SR"}:
        raise EventCorrectionError("The selected event type must be Race or Sprint.")
    return race_metadata.make_race_metadata(
        game=values["game"],
        season=values["season"],
        league=values["league"],
        round_number=round_number,
        event_type=event_type,
        gp_name=values["gp_name"],
        league_id=str(getattr(metadata, "league_id", "") or "").strip(),
    )


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, bool) and missing


def _snapshot_text(value: object) -> str | None:
    if _missing(value):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return str(value.isoformat())
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    return text or None


def _raw_results(path: Path) -> pd.DataFrame:
    try:
        data = pd.read_excel(path, sheet_name="Leagues", usecols="A:L", dtype=object)
    except ValueError as exc:
        raise EventCorrectionError("Required sheet 'Leagues' was not found.") from exc
    data.columns = [str(column).strip() for column in data.columns]
    required = set(_RESULT_HEADERS[:10])
    missing = sorted(required - set(data.columns))
    if missing:
        raise EventCorrectionError(
            "Sheet 'Leagues' is missing correction column(s): " + ", ".join(missing)
        )
    for optional in ("Time", "Fastest Lap"):
        if optional not in data:
            data[optional] = pd.NA
    return data


def _raw_event_mask(data: pd.DataFrame, metadata: workbook.RaceMetadata) -> pd.Series:
    event_types = data["Type"].fillna("R").astype(str).str.strip().str.upper()
    return (
        data["Game"].fillna("").astype(str).str.strip().eq(metadata.game)
        & data["Season"].fillna("").astype(str).str.strip().eq(metadata.season)
        & data["League Name"].fillna("").astype(str).str.strip().eq(metadata.league)
        & pd.to_numeric(data["Round"], errors="coerce").eq(metadata.round_number)
        & event_types.eq(metadata.event_type)
        & data["GP Name"].fillna("").astype(str).str.strip().eq(metadata.gp_name)
    )


def _calendar_status(path: Path, excel_row: int) -> str:
    try:
        calendar = pd.read_excel(path, sheet_name="Calendar", dtype=object)
    except ValueError as exc:
        raise EventCorrectionError("Required sheet 'Calendar' was not found.") from exc
    if "Status" not in calendar:
        raise EventCorrectionError("Calendar is missing its Status column.")
    dataframe_index = excel_row - 2
    if dataframe_index < 0 or dataframe_index >= len(calendar):
        raise EventCorrectionError("The selected Calendar row is outside the worksheet data.")
    return _snapshot_text(calendar.iloc[dataframe_index]["Status"]) or ""


def _snapshot_digest(
    metadata: workbook.RaceMetadata,
    rows: Sequence[ExistingResultRow],
    *,
    calendar_excel_row: int,
    calendar_status: str,
) -> str:
    payload = {
        "metadata": asdict(metadata),
        "rows": [asdict(row) for row in rows],
        "calendar_excel_row": calendar_excel_row,
        "calendar_status": calendar_status,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_event_snapshot(path: Path, metadata: workbook.RaceMetadata) -> EventSnapshot:
    raw = _raw_results(path)
    event = raw.loc[_raw_event_mask(raw, metadata)].copy()
    if event.empty:
        raise EventNotFoundError("The selected race or sprint is not present in the workbook.")

    positions = pd.to_numeric(event["Finish Pos"], errors="coerce")
    if positions.isna().any() or not positions.map(lambda value: float(value).is_integer()).all():
        raise EventNotFoundError("The selected event does not contain one complete numeric finishing order.")
    event["_Position"] = positions.astype(int)
    expected_positions = set(range(1, len(event) + 1))
    actual_positions = event["_Position"].tolist()
    if set(actual_positions) != expected_positions or len(set(actual_positions)) != len(actual_positions):
        raise EventNotFoundError("The selected event is duplicated or does not contain one complete finishing order.")

    drivers = event["Driver"].fillna("").astype(str).str.strip()
    teams = event["Team"].fillna("").astype(str).str.strip()
    normalized_drivers = drivers.map(race.normalize_name)
    if (
        drivers.eq("").any()
        or teams.eq("").any()
        or normalized_drivers.eq("").any()
        or normalized_drivers.duplicated(keep=False).any()
    ):
        raise EventNotFoundError("The selected event does not contain one complete unique driver roster.")
    points = pd.to_numeric(event["Points"], errors="coerce")
    if points.isna().any() or any(not math.isfinite(float(value)) for value in points):
        raise EventNotFoundError("The selected event contains invalid points.")

    standings = core.load_standings_data(path)
    calendar_row = workbook._calendar_excel_row(path, metadata)
    if calendar_row is None:
        raise EventCorrectionError(
            "The selected event does not exactly match one Calendar row."
        )
    if not workbook._calendar_identity_is_unambiguous(standings, metadata):
        raise EventCorrectionError(
            "The Calendar league does not identify exactly this championship."
        )
    status = _calendar_status(path, calendar_row)

    rows = tuple(
        ExistingResultRow(
            excel_row=int(index) + 2,
            position=int(row["_Position"]),
            driver=str(row["Driver"]).strip(),
            team=str(row["Team"]).strip(),
            points=float(row["Points"]),
            time=_snapshot_text(row.get("Time")),
            fastest_lap=_snapshot_text(row.get("Fastest Lap")),
        )
        for index, row in event.sort_values("_Position").iterrows()
    )
    return EventSnapshot(
        metadata=metadata,
        rows=rows,
        calendar_excel_row=int(calendar_row),
        calendar_status=status,
        digest=_snapshot_digest(
            metadata,
            rows,
            calendar_excel_row=int(calendar_row),
            calendar_status=status,
        ),
    )


def load_event_snapshot(
    workbook_path: str | Path,
    metadata: workbook.RaceMetadata,
) -> EventSnapshot:
    """Return the immutable before-state used by a correction review."""

    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise EventCorrectionError(f"Workbook was not found: {path}")
    return _load_event_snapshot(path, _normalized_metadata(metadata))


def _authoritative_roster(
    values: Sequence[race.DriverEntry] | Sequence[Mapping[str, object]],
) -> tuple[race.DriverEntry, ...]:
    entries: list[race.DriverEntry] = []
    for value in values:
        if isinstance(value, race.DriverEntry):
            driver, team = value.driver, value.team
        elif isinstance(value, Mapping):
            driver, team = value.get("Driver"), value.get("Team")
        else:
            raise EventCorrectionError("The authoritative roster contains an invalid entry.")
        driver_text = str(driver or "").strip()
        team_text = str(team or "").strip()
        if not driver_text or not team_text:
            raise EventCorrectionError("Every authoritative roster entry needs a driver and team.")
        entries.append(race.DriverEntry(driver_text, team_text))
    normalized = [race.normalize_name(entry.driver) for entry in entries]
    if not entries or any(not name for name in normalized) or len(set(normalized)) != len(normalized):
        raise EventCorrectionError("The authoritative roster must contain unique drivers.")
    return tuple(entries)


def _authoritative_scoring(
    values: Mapping[int, float],
    grid_size: int,
) -> dict[int, float]:
    result: dict[int, float] = {}
    for raw_position, raw_points in values.items():
        if isinstance(raw_position, bool):
            raise EventCorrectionError("The authoritative scoring profile has an invalid position.")
        try:
            position = int(raw_position)
            points = float(raw_points)
        except (TypeError, ValueError) as exc:
            raise EventCorrectionError("The authoritative scoring profile is invalid.") from exc
        if position in result or not math.isfinite(points) or points < 0:
            raise EventCorrectionError("The authoritative scoring profile is invalid.")
        result[position] = points
    if set(result) != set(range(1, grid_size + 1)):
        raise EventCorrectionError(
            "The authoritative scoring profile must define every finishing position exactly once."
        )
    return result


def _mask_mutable_cells(payload: bytes, allowed: set[str]) -> bytes:
    return _CELL_PATTERN.sub(
        lambda match: b"" if (match.group(1) + match.group(2)).decode("ascii") in allowed else match.group(0),
        payload,
    )


def _verify_only_allowed_cells_changed(
    before: bytes,
    after: bytes,
    allowed: set[str],
    *,
    sheet_name: str,
) -> None:
    if _mask_mutable_cells(before, allowed) != _mask_mutable_cells(after, allowed):
        raise EventCorrectionError(
            f"Staged {sheet_name} content changed outside the selected correction cells."
        )


def _verify_strict_timing_cells(
    worksheet_xml: bytes,
    rows_by_excel_row: Mapping[int, Mapping[str, object]],
) -> None:
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError as exc:
        raise EventCorrectionError("Could not reopen staged timing cells.") from exc
    cells = {
        cell.attrib.get("r", ""): cell
        for cell in root.findall(".//m:sheetData/m:row/m:c", _MAIN_NS)
    }
    for excel_row, row in rows_by_excel_row.items():
        for column, key in (("K", "Time"), ("L", "Fastest Lap")):
            expected = row.get(key)
            if expected is None or not hasattr(expected, "text"):
                raise EventCorrectionError(f"Approved {key} value was not normalized.")
            cell = cells.get(f"{column}{excel_row}")
            if cell is None or cell.find("m:f", _MAIN_NS) is not None or cell.attrib.get("t") != "inlineStr":
                raise EventCorrectionError(f"Staged {key} cell is missing or unsafe.")
            actual = "".join(node.text or "" for node in cell.findall(".//m:t", _MAIN_NS))
            if actual != expected.text:
                raise EventCorrectionError(f"Staged {key} value does not match the approved review.")


def _expected_result_rows(
    normalized_rows: Sequence[Mapping[str, object]],
    excel_row_by_position: Mapping[int, int],
) -> tuple[ExistingResultRow, ...]:
    return tuple(
        ExistingResultRow(
            excel_row=excel_row_by_position[int(row["Position"])],
            position=int(row["Position"]),
            driver=str(row["Driver"]),
            team=str(row["Team"]),
            points=float(row["Points"]),
            time=row["Time"].text,  # type: ignore[union-attr]
            fastest_lap=row["Fastest Lap"].text,  # type: ignore[union-attr]
        )
        for row in sorted(normalized_rows, key=lambda item: int(item["Position"]))
    )


def _commit_event_correction_locked(
    path: Path,
    *,
    metadata: workbook.RaceMetadata,
    action: CorrectionAction,
    rows: Iterable[Mapping[str, object]],
    authoritative_roster: Sequence[race.DriverEntry] | Sequence[Mapping[str, object]],
    authoritative_scoring: Mapping[int, float],
    expected_event_digest: str,
    expected_sha256: str,
    backup_directory: str | Path | None,
) -> CorrectionResult:
    current_sha = workbook.workbook_fingerprint(path)
    if current_sha != expected_sha256:
        raise workbook.StaleWorkbookError(
            "The workbook changed after this correction review was created. Reload and review again."
        )
    snapshot = _load_event_snapshot(path, metadata)
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_event_digest or "").casefold()):
        raise workbook.StaleWorkbookError("The reviewed event snapshot is missing or invalid.")
    if snapshot.digest.casefold() != str(expected_event_digest).casefold():
        raise workbook.StaleWorkbookError(
            "The selected event changed after the correction review was created. Reload and review again."
        )

    import league_config
    import league_runtime

    tables = league_config.load_config_tables(path)
    configured_key = league_runtime.matching_configured_key(
        tables,
        game=metadata.game,
        season=metadata.season,
        league=metadata.league,
        league_id=metadata.league_id,
    )

    supplied_rows = [dict(row) for row in rows]
    normalized_rows: list[dict] = []
    if action is CorrectionAction.UNDO:
        if supplied_rows:
            raise EventCorrectionError("Undo must not include replacement result rows.")
        if configured_key is not None:
            try:
                league_config.require_active_configured_league(
                    tables, configured_key.league_id
                )
            except league_config.LeagueConfigError as exc:
                raise EventCorrectionError(
                    "A configured Draft or Completed league cannot undo a published "
                    "event because normal re-import is closed. Replace the event instead."
                ) from exc
    else:
        if configured_key is not None:
            authority = league_runtime.resolve_event_authority(
                path,
                core.load_standings_data(path),
                race_metadata.make_race_metadata(
                    game=metadata.game,
                    season=metadata.season,
                    league=metadata.league,
                    round_number=metadata.round_number,
                    event_type=metadata.event_type,
                    gp_name=metadata.gp_name,
                    league_id=configured_key.league_id,
                ),
            )
            roster = list(authority.roster)
            scoring = authority.base_points
            if authoritative_roster:
                supplied_roster = _authoritative_roster(authoritative_roster)
                if {(row.driver, row.team) for row in supplied_roster} != {
                    (row.driver, row.team) for row in roster
                }:
                    raise EventCorrectionError(
                        "The supplied correction roster does not match the configured round snapshot."
                    )
            if authoritative_scoring:
                supplied_scoring = _authoritative_scoring(authoritative_scoring, len(roster))
                if supplied_scoring != scoring:
                    raise EventCorrectionError(
                        "The supplied correction scoring does not match the configured event profile."
                    )
            supplied_row_list = [dict(row) for row in supplied_rows]
            scored_rows, _ = league_runtime.apply_configured_points(
                supplied_row_list,
                authority,
            )
            for supplied_row, expected_row in zip(supplied_row_list, scored_rows, strict=True):
                if "Points" in supplied_row and float(supplied_row["Points"]) != float(expected_row["Points"]):
                    raise EventCorrectionError(
                        f"Replacement points for position {expected_row['Position']} do not match configured rules."
                    )
            supplied_rows = scored_rows
            scoring = {
                int(row["Position"]): float(row["Points"])
                for row in scored_rows
            }
        else:
            roster = _authoritative_roster(authoritative_roster)
            scoring = _authoritative_scoring(authoritative_scoring, len(roster))
        if len(snapshot.rows) != len(roster):
            raise EventCorrectionError(
                "The selected event grid does not match the authoritative roster size."
            )
        snapshot_roster = {(row.driver, row.team) for row in snapshot.rows}
        expected_roster = {(entry.driver, entry.team) for entry in roster}
        if snapshot_roster != expected_roster:
            raise EventCorrectionError(
                "The selected event does not match the authoritative driver/team roster."
            )
        normalized_rows = workbook._validate_commit_rows(
            supplied_rows,
            scoring,
            require_complete_timing=True,
        )
        roster_map = {entry.driver: entry.team for entry in roster}
        if {row["Driver"] for row in normalized_rows} != set(roster_map):
            raise EventCorrectionError(
                "Replacement rows must contain every authoritative driver exactly once."
            )
        if any(roster_map[row["Driver"]] != row["Team"] for row in normalized_rows):
            raise EventCorrectionError(
                "A replacement team does not match the authoritative event roster."
            )

    before_standings = core.load_standings_data(path)
    excel_row_by_position = {row.position: row.excel_row for row in snapshot.rows}
    result_refs = {
        f"{column}{excel_row}"
        for excel_row in excel_row_by_position.values()
        for column in _RESULT_COLUMNS
    }

    with ZipFile(path, "r") as archive:
        sheet_paths = workbook._sheet_paths(archive)
        leagues_part = sheet_paths.get("Leagues")
        calendar_part = sheet_paths.get("Calendar")
        if not leagues_part or not calendar_part:
            raise EventCorrectionError("Required correction worksheets were not found in the package.")
        original_leagues_xml = archive.read(leagues_part)
        leagues_xml = original_leagues_xml
        rows_by_excel_row: dict[int, Mapping[str, object]] = {}
        if action is CorrectionAction.REPLACE:
            for row in normalized_rows:
                excel_row = excel_row_by_position[int(row["Position"])]
                rows_by_excel_row[excel_row] = row
                leagues_xml = workbook._replace_row_cells(
                    leagues_xml,
                    excel_row,
                    workbook._workbook_row(metadata, row),
                    _RESULT_COLUMNS,
                )
        else:
            for excel_row in excel_row_by_position.values():
                leagues_xml = workbook._replace_row_cells(
                    leagues_xml,
                    excel_row,
                    {},
                    _RESULT_COLUMNS,
                )
        replacements: dict[str, bytes] = {leagues_part: leagues_xml}

        original_calendar_xml = archive.read(calendar_part)
        desired_calendar_status = snapshot.calendar_status
        if metadata.event_type == "R":
            desired_calendar_status = "Done" if action is CorrectionAction.REPLACE else "Upcoming"
        calendar_updated = desired_calendar_status != snapshot.calendar_status
        calendar_ref = f"F{snapshot.calendar_excel_row}"
        if calendar_updated:
            replacements[calendar_part] = workbook._replace_row_cells(
                original_calendar_xml,
                snapshot.calendar_excel_row,
                {"F": desired_calendar_status},
                ("F",),
            )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.event-correction-",
        suffix=".xlsx",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        workbook._copy_archive_with_replacements(path, temporary_path, replacements)
        workbook._verify_untouched_parts(path, temporary_path, set(replacements))
        with ZipFile(temporary_path, "r") as candidate_archive:
            candidate_leagues_xml = candidate_archive.read(leagues_part)
            _verify_only_allowed_cells_changed(
                original_leagues_xml,
                candidate_leagues_xml,
                result_refs,
                sheet_name="Leagues",
            )
            if calendar_updated:
                _verify_only_allowed_cells_changed(
                    original_calendar_xml,
                    candidate_archive.read(calendar_part),
                    {calendar_ref},
                    sheet_name="Calendar",
                )
            if action is CorrectionAction.REPLACE:
                _verify_strict_timing_cells(candidate_leagues_xml, rows_by_excel_row)

        core.validate_workbook(temporary_path)
        after_standings = core.load_standings_data(temporary_path)
        if action is CorrectionAction.REPLACE:
            staged_snapshot = _load_event_snapshot(temporary_path, metadata)
            expected_rows = _expected_result_rows(normalized_rows, excel_row_by_position)
            if staged_snapshot.rows != expected_rows:
                raise EventCorrectionError(
                    "Staged replacement rows do not match the approved correction."
                )
            if len(after_standings) != len(before_standings):
                raise EventCorrectionError("Staged replacement changed the standings row count.")
        else:
            if workbook.event_already_exists(after_standings, metadata):
                raise EventCorrectionError("Staged undo did not remove the selected event.")
            if len(after_standings) != len(before_standings) - len(snapshot.rows):
                raise EventCorrectionError("Staged undo changed an unexpected number of result rows.")

        staged_status = _calendar_status(temporary_path, snapshot.calendar_excel_row)
        if staged_status != desired_calendar_status:
            raise EventCorrectionError("Staged Calendar status does not match the correction action.")

        if workbook.workbook_fingerprint(path) != current_sha:
            raise workbook.StaleWorkbookError(
                "The workbook changed while this correction was staged. Nothing was replaced."
            )
        backup_root = (
            Path(backup_directory)
            if backup_directory
            else path.parent / ".codex-tmp" / "race-correction-backups"
        )
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_root / f"{path.stem}.before-correction-{timestamp}-{current_sha[:8]}.xlsx"
        if backup_path.exists():
            backup_path = backup_root / (
                f"{path.stem}.before-correction-{timestamp}-{current_sha[:8]}-{uuid4().hex[:6]}.xlsx"
            )
        shutil.copy2(path, backup_path)
        if workbook.workbook_fingerprint(backup_path) != current_sha:
            raise workbook.StaleWorkbookError(
                "The correction recovery copy did not match the reviewed workbook."
            )
        shutil.copystat(path, temporary_path)
        if workbook.workbook_fingerprint(path) != current_sha:
            raise workbook.StaleWorkbookError(
                "The workbook changed after its correction recovery copy was verified."
            )
        try:
            os.replace(temporary_path, path)
        except PermissionError as exc:
            raise EventCorrectionError(
                "Excel appears to have the workbook open. Close it and confirm the correction again."
            ) from exc

        return CorrectionResult(
            action=action,
            affected_excel_rows=tuple(sorted(excel_row_by_position.values())),
            rows_replaced=len(snapshot.rows) if action is CorrectionAction.REPLACE else 0,
            rows_removed=len(snapshot.rows) if action is CorrectionAction.UNDO else 0,
            backup_path=backup_path,
            calendar_updated=calendar_updated,
            workbook_sha256=workbook.workbook_fingerprint(path),
        )
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def commit_event_correction(
    workbook_path: str | Path,
    *,
    metadata: workbook.RaceMetadata,
    action: CorrectionAction | str,
    rows: Iterable[Mapping[str, object]] = (),
    authoritative_roster: Sequence[race.DriverEntry] | Sequence[Mapping[str, object]] = (),
    authoritative_scoring: Mapping[int, float] | None = None,
    expected_event_digest: str,
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None = None,
) -> CorrectionResult:
    """Atomically replace or undo one reviewed, already-published event."""

    if not approved:
        raise workbook.ApprovalRequiredError(
            "Event correction requires explicit approval from the old-versus-new review."
        )
    try:
        correction_action = CorrectionAction(action)
    except ValueError as exc:
        raise EventCorrectionError("Correction action must be replace or undo.") from exc
    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise EventCorrectionError(f"Workbook was not found: {path}")
    normalized_metadata = _normalized_metadata(metadata)
    with workbook._workbook_lock(path):
        return _commit_event_correction_locked(
            path,
            metadata=normalized_metadata,
            action=correction_action,
            rows=rows,
            authoritative_roster=authoritative_roster,
            authoritative_scoring=authoritative_scoring or {},
            expected_event_digest=expected_event_digest,
            expected_sha256=expected_sha256,
            backup_directory=backup_directory,
        )
