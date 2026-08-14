"""Transaction-safe, preservation-oriented updates for ``F1_Standings.xlsx``.

The workbook contains pivot caches, cached formulas, and modern comment parts
that normal Excel round-trips can discard. This writer therefore changes only
the two worksheet XML parts that own race results and calendar status, copies
every other OOXML part unchanged, validates a temporary workbook, and replaces
the original only after explicit approval.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import BinaryIO, Iterable, Iterator, Mapping
from uuid import uuid4
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

if os.name == "nt":
    import msvcrt
else:
    import fcntl

import pandas as pd

import dashboard_core as core
import race_import as race


class WorkbookUpdateError(RuntimeError):
    """Base class for a safe workbook update failure."""


class ApprovalRequiredError(WorkbookUpdateError):
    """Raised when code attempts to write an unapproved review."""


class StaleWorkbookError(WorkbookUpdateError):
    """Raised when the workbook changed after the review was created."""


class DuplicateEventError(WorkbookUpdateError):
    """Raised when an event is already present in the workbook."""


_WORKBOOK_LOCK_TIMEOUT_SECONDS = 30.0
_WORKBOOK_LOCK_POLL_SECONDS = 0.05
_LOCK_FILE_INITIALIZATION_GUARD = threading.Lock()
_PIVOT_SOURCE_PART = "xl/pivotCache/pivotCacheDefinition1.xml"
_PIVOT_SOURCE_PATTERN = re.compile(
    rb'(<worksheetSource\b[^>]*\bref=")([A-Z]+\d+):([A-Z]+)(\d+)("[^>]*\bsheet="Leagues"[^>]*/>)'
)
_MAIN_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DURATION_PATTERN = re.compile(
    r"^(?:(?P<hours>\d{1,3}):)?(?P<minutes>\d{1,3}):(?P<seconds>[0-5]\d)"
    r"(?:[.,](?P<fraction>\d{1,3}))?$"
)
_TIME_GAP_PATTERNS = (
    re.compile(r"^\+\d+(?:[.,]\d{1,3})?$"),
    re.compile(r"^\+\d{1,3}:[0-5]\d(?:[.,]\d{1,3})?$"),
    re.compile(r"^\+\d+\s+laps?$", re.IGNORECASE),
)
_TIMING_STATUSES = frozenset({"DNF", "DNS", "DSQ", "DQ", "RET", "NC", "DNQ", "N/A"})


def _workbook_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.race-import.lock")


def _open_workbook_lock_file(lock_path: Path) -> BinaryIO:
    with _LOCK_FILE_INITIALIZATION_GUARD:
        handle = lock_path.open("a+b")
        try:
            # ``msvcrt.locking`` locks a byte range, so the file must own at
            # least one byte. Serialize first-use initialization within this
            # process; the stable sidecar avoids a later inode race.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            return handle
        except BaseException:
            handle.close()
            raise


def _try_acquire_workbook_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_workbook_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lock_is_busy(exc: OSError) -> bool:
    return (
        isinstance(exc, BlockingIOError)
        or exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(exc, "winerror", None) in {33, 36}
    )


@contextmanager
def _workbook_lock(path: Path, *, timeout_seconds: float | None = None) -> Iterator[None]:
    timeout = _WORKBOOK_LOCK_TIMEOUT_SECONDS if timeout_seconds is None else max(0.0, timeout_seconds)
    try:
        handle = _open_workbook_lock_file(_workbook_lock_path(path))
    except OSError as exc:
        raise WorkbookUpdateError("Could not open the workbook update lock; the workbook was not changed.") from exc

    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while not acquired:
            try:
                _try_acquire_workbook_lock(handle)
                acquired = True
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue
                if not _lock_is_busy(exc):
                    raise WorkbookUpdateError(
                        "Could not acquire the workbook update lock; the workbook was not changed."
                    ) from exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkbookUpdateError(
                        "Another race import is already updating this workbook. Try again after it finishes; "
                        "the workbook was not changed."
                    ) from exc
                time.sleep(min(_WORKBOOK_LOCK_POLL_SECONDS, remaining))
        yield
    finally:
        if acquired:
            try:
                _release_workbook_lock(handle)
            except OSError:
                # Closing the descriptor also releases an advisory lock. Do
                # not report a failed import after an atomic replace succeeded.
                pass
        handle.close()


@dataclass(frozen=True)
class RaceMetadata:
    game: str
    season: str
    league: str
    round_number: int
    event_type: str
    gp_name: str
    # Immutable identity for configuration-backed leagues.  Legacy callers
    # may omit it; protected Admin setup always supplies it.
    league_id: str = ""


@dataclass(frozen=True)
class CommitResult:
    rows_added: int
    first_excel_row: int
    last_excel_row: int
    backup_path: Path
    calendar_updated: bool
    workbook_sha256: str


@dataclass(frozen=True)
class _TimingValue:
    """A validated, exact result-table timing value."""

    text: str


def workbook_fingerprint(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _event_mask(data: pd.DataFrame, metadata: RaceMetadata) -> pd.Series:
    season_column = "SeasonLabel" if "SeasonLabel" in data.columns else "Season"
    event_types = data["Type"] if "Type" in data.columns else pd.Series("R", index=data.index)
    return (
        data["Game"].astype(str).eq(metadata.game)
        & data[season_column].astype(str).eq(metadata.season)
        & data["League Name"].astype(str).eq(metadata.league)
        & pd.to_numeric(data["Round"], errors="coerce").eq(metadata.round_number)
        & event_types.fillna("R").astype(str).str.upper().eq(metadata.event_type.upper())
    )


def event_already_exists(data: pd.DataFrame, metadata: RaceMetadata) -> bool:
    return bool(_event_mask(data, metadata).any())


def _sheet_paths(archive: ZipFile) -> dict[str, str]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall(f"{{{rel_ns}}}Relationship")
    }
    paths: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
        relationship_id = sheet.attrib[f"{{{office_rel_ns}}}id"]
        target = targets[relationship_id].replace("\\", "/")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target.lstrip("./")
        paths[sheet.attrib["name"]] = target
    return paths


def _column_number(column: str) -> int:
    number = 0
    for character in column:
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _normalize_timing_value(value: object, *, field_name: str) -> _TimingValue | None:
    """Validate one approved timing cell without guessing its meaning.

    All accepted values remain exact text. In particular, a displayed gap is
    not converted into an invented total result time, and a duration-like value
    is not reinterpreted as an Excel date/time serial. Historical native Excel
    durations already in the workbook remain untouched.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            missing = pd.isna(value)
        except (TypeError, ValueError):
            missing = False
        if isinstance(missing, bool) and missing:
            return None
        raise WorkbookUpdateError(f"{field_name} must be supplied as reviewed text or left blank.")

    text = value.strip()
    if not text:
        return None

    duration_match = _DURATION_PATTERN.fullmatch(text)
    if duration_match:
        hours_text = duration_match.group("hours")
        minutes = int(duration_match.group("minutes"))
        if hours_text is not None and minutes >= 60:
            raise WorkbookUpdateError(f"{field_name} contains an invalid duration: {text!r}.")
        if not any(character != "0" for character in re.sub(r"\D", "", text)):
            raise WorkbookUpdateError(f"{field_name} must be a positive duration when a time is supplied.")
        return _TimingValue(text=text)

    status_allowed = text.upper() in _TIMING_STATUSES
    if field_name == "Time" and (
        status_allowed or any(pattern.fullmatch(text) for pattern in _TIME_GAP_PATTERNS)
    ):
        return _TimingValue(text=text)
    if field_name == "Fastest Lap" and status_allowed:
        return _TimingValue(text=text)

    allowed = "an absolute duration, a displayed gap/lap deficit, or a known status"
    if field_name == "Fastest Lap":
        allowed = "an absolute duration or a known status"
    raise WorkbookUpdateError(f"{field_name} must be {allowed}; got {text!r}.")


def _cell_xml(column: str, row_number: int, value: object) -> str:
    reference = f"{column}{row_number}"
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not pd.isna(value):
        numeric = int(value) if float(value).is_integer() else float(value)
        return f'<c r="{reference}"><v>{numeric}</v></c>'
    text = str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return f'<c r="{reference}" t="inlineStr"><is><t{preserve}>{xml_escape(text)}</t></is></c>'


def _replace_row_cells(
    worksheet_xml: bytes,
    row_number: int,
    values: Mapping[str, object | None],
    mutable_columns: Iterable[str],
) -> bytes:
    text = worksheet_xml.decode("utf-8")
    row_pattern = re.compile(
        rf'(<row\b(?=[^>]*\br="{row_number}")[^>]*>)(.*?)(</row>)',
        re.DOTALL,
    )
    match = row_pattern.search(text)
    mutable = set(mutable_columns)
    generated = {column: _cell_xml(column, row_number, value) for column, value in values.items() if value is not None and value != ""}

    if match:
        cell_pattern = re.compile(
            rf'<c\b(?=[^>]*\br="([A-Z]+){row_number}")[^>]*(?:/>|>.*?</c>)',
            re.DOTALL,
        )
        preserved: dict[str, str] = {}
        for cell_match in cell_pattern.finditer(match.group(2)):
            column = cell_match.group(1)
            if column not in mutable:
                preserved[column] = cell_match.group(0)
        cells = {**preserved, **generated}
        inner = "".join(cells[column] for column in sorted(cells, key=_column_number))
        replacement = match.group(1) + inner + match.group(3)
        return (text[: match.start()] + replacement + text[match.end() :]).encode("utf-8")

    cells = "".join(generated[column] for column in sorted(generated, key=_column_number))
    new_row = f'<row r="{row_number}">{cells}</row>'
    insert_at = None
    for candidate in re.finditer(r'<row\b(?=[^>]*\br="(\d+)")[^>]*>', text):
        if int(candidate.group(1)) > row_number:
            insert_at = candidate.start()
            break
    if insert_at is None:
        closing = text.find("</sheetData>")
        if closing < 0:
            raise WorkbookUpdateError("Worksheet XML does not contain sheetData.")
        insert_at = closing
    return (text[:insert_at] + new_row + text[insert_at:]).encode("utf-8")


def _first_available_result_row(path: Path) -> int:
    raw = pd.read_excel(path, sheet_name="Leagues", usecols="A:J")
    populated = raw.notna().any(axis=1)
    if not populated.any():
        return 2
    last_dataframe_index = int(populated[populated].index.max())
    return last_dataframe_index + 3


def _calendar_excel_row(path: Path, metadata: RaceMetadata) -> int | None:
    try:
        calendar = pd.read_excel(path, sheet_name="Calendar")
    except ValueError:
        return None
    required = {"League Name", "Round", "GP Name"}
    if not required.issubset(calendar.columns):
        return None
    if metadata.league_id:
        if "League ID" not in calendar.columns:
            return None
        mask = (
            calendar["League ID"].fillna("").astype(str).str.strip().eq(metadata.league_id)
            & pd.to_numeric(calendar["Round"], errors="coerce").eq(metadata.round_number)
            & calendar["GP Name"].fillna("").astype(str).str.strip().eq(metadata.gp_name)
        )
        if "Game" in calendar.columns:
            mask &= calendar["Game"].fillna("").astype(str).str.strip().eq(metadata.game)
        if "Season" in calendar.columns:
            mask &= calendar["Season"].fillna("").astype(str).str.strip().eq(metadata.season)
    else:
        mask = (
            calendar["League Name"].fillna("").astype(str).str.strip().eq(metadata.league)
            & pd.to_numeric(calendar["Round"], errors="coerce").eq(metadata.round_number)
            & calendar["GP Name"].fillna("").astype(str).str.strip().eq(metadata.gp_name)
        )
    indexes = calendar.index[mask].tolist()
    if len(indexes) > 1:
        raise WorkbookUpdateError("Calendar contains more than one matching event row.")
    return int(indexes[0]) + 2 if indexes else None


def _calendar_identity_is_unambiguous(standings: pd.DataFrame, metadata: RaceMetadata) -> bool:
    """A Calendar row without Game/Season columns must map to one championship."""
    if metadata.league_id:
        # _calendar_excel_row already required the immutable ID and, when
        # present, exact Game/Season columns.  Reused display labels are safe.
        return True
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    league_rows = standings[standings["League Name"].astype(str).eq(metadata.league)]
    championships = league_rows[["Game", season_column]].astype(str).drop_duplicates()
    expected = (metadata.game, metadata.season)
    return len(championships) == 1 and tuple(championships.iloc[0]) == expected


def _extend_pivot_source_if_needed(
    archive: ZipFile,
    replacements: dict[str, bytes],
    *,
    last_excel_row: int,
) -> None:
    """Extend the cached Leagues pivot source so imported rows remain visible."""
    if _PIVOT_SOURCE_PART not in archive.namelist():
        raise WorkbookUpdateError("Workbook is missing the Leagues pivot-cache definition.")
    payload = archive.read(_PIVOT_SOURCE_PART)
    match = _PIVOT_SOURCE_PATTERN.search(payload)
    if match is None:
        raise WorkbookUpdateError("Could not verify the Leagues pivot-cache source range.")
    current_last_row = int(match.group(4))
    if last_excel_row <= current_last_row:
        return
    updated = (
        payload[: match.start()]
        + match.group(1)
        + re.sub(rb"\d+$", b"", match.group(2))
        + b"1:"
        + match.group(3)
        + str(last_excel_row).encode("ascii")
        + match.group(5)
        + payload[match.end() :]
    )
    replacements[_PIVOT_SOURCE_PART] = updated


def _copy_archive_with_replacements(source: Path, destination: Path, replacements: Mapping[str, bytes]) -> None:
    try:
        with ZipFile(source, "r") as source_zip, ZipFile(destination, "w", compression=ZIP_DEFLATED, allowZip64=True) as target_zip:
            existing = set(source_zip.namelist())
            missing = set(replacements) - existing
            if missing:
                raise WorkbookUpdateError("Workbook is missing expected XML part(s): " + ", ".join(sorted(missing)))
            for info in source_zip.infolist():
                target_zip.writestr(info, replacements.get(info.filename, source_zip.read(info.filename)))
    except BadZipFile as exc:
        raise WorkbookUpdateError("The Excel workbook is not a valid OOXML archive.") from exc


def _verify_untouched_parts(source: Path, candidate: Path, changed_parts: set[str]) -> None:
    with ZipFile(source, "r") as original, ZipFile(candidate, "r") as updated:
        if original.namelist() != updated.namelist():
            raise WorkbookUpdateError("Workbook package parts changed unexpectedly during staging.")
        for name in original.namelist():
            if name not in changed_parts and original.read(name) != updated.read(name):
                raise WorkbookUpdateError(f"Workbook part '{name}' changed unexpectedly during staging.")


def _validate_commit_rows(
    rows: Iterable[Mapping[str, object]],
    scoring_profile: Mapping[int, float],
    *,
    require_complete_timing: bool = False,
) -> list[dict]:
    """Normalize approved rows, including optional exact-text timing fields.

    By default, ``Time`` and ``Fastest Lap`` may be omitted/blank. Strict
    protected-Admin mode requires both and independently canonicalizes them
    through ``race.normalize_race_time`` and ``race.normalize_fastest_lap``.
    Numeric Excel serials are deliberately not accepted at this trust boundary.
    """
    normalized: list[dict] = []
    for raw in rows:
        try:
            position = int(raw["Position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkbookUpdateError("Every approved row needs a numeric Position.") from exc
        driver = str(raw.get("Driver") or "").strip()
        team = str(raw.get("Team") or "").strip()
        if not driver or not team:
            raise WorkbookUpdateError("Every approved row needs a canonical Driver and Team.")
        expected_points = float(scoring_profile.get(position, 0))
        provided_points = float(raw.get("Points", expected_points))
        if provided_points != expected_points:
            raise WorkbookUpdateError(f"Points for position {position} do not match the verified scoring profile.")
        if require_complete_timing:
            time_text = race.normalize_race_time(raw.get("Time"))
            fastest_lap_text = race.normalize_fastest_lap(raw.get("Fastest Lap"))
            if time_text is None:
                raise WorkbookUpdateError(
                    f"Position {position} needs a complete canonical Time before publication."
                )
            if fastest_lap_text is None:
                raise WorkbookUpdateError(
                    f"Position {position} needs a complete canonical Fastest Lap before publication."
                )
            time_value = _TimingValue(time_text)
            fastest_lap_value = _TimingValue(fastest_lap_text)
        else:
            time_value = _normalize_timing_value(raw.get("Time"), field_name="Time")
            fastest_lap_value = _normalize_timing_value(
                raw.get("Fastest Lap"), field_name="Fastest Lap"
            )
        normalized.append(
            {
                "Position": position,
                "Driver": driver,
                "Team": team,
                "Points": expected_points,
                "Time": time_value,
                "Fastest Lap": fastest_lap_value,
            }
        )
    positions = [row["Position"] for row in normalized]
    drivers = [row["Driver"] for row in normalized]
    expected_positions = set(scoring_profile)
    if set(positions) != expected_positions or len(positions) != len(expected_positions):
        raise WorkbookUpdateError("Approved rows must contain every finishing position exactly once.")
    if len(drivers) != len(set(drivers)):
        raise WorkbookUpdateError("Approved rows contain a duplicate driver.")
    return sorted(normalized, key=lambda row: row["Position"])


def _workbook_row(metadata: RaceMetadata, row: Mapping[str, object]) -> dict[str, object]:
    def timing_text(key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        if not isinstance(value, _TimingValue):
            raise WorkbookUpdateError("An approved timing value was not normalized before writing.")
        return value.text

    return {
        "A": metadata.game,
        "B": metadata.season,
        "C": metadata.league,
        "D": metadata.round_number,
        "E": metadata.event_type.upper(),
        "F": metadata.gp_name,
        "G": row["Driver"],
        "H": row["Team"],
        "I": row["Position"],
        "J": row["Points"],
        "K": timing_text("Time"),
        "L": timing_text("Fastest Lap"),
    }


def _verify_timing_cells(
    candidate: Path,
    *,
    worksheet_part: str,
    first_excel_row: int,
    rows: list[dict],
) -> None:
    """Reopen the staged package and compare K:L to the approved review."""
    try:
        with ZipFile(candidate, "r") as archive:
            worksheet_root = ET.fromstring(archive.read(worksheet_part))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise WorkbookUpdateError("Could not reopen staged timing cells for verification.") from exc

    namespace = {"m": _MAIN_SPREADSHEET_NS}
    cells = {
        cell.attrib.get("r", ""): cell
        for cell in worksheet_root.findall(".//m:sheetData/m:row/m:c", namespace)
    }
    for offset, row in enumerate(rows):
        excel_row = first_excel_row + offset
        for column, key in (("K", "Time"), ("L", "Fastest Lap")):
            expected = row.get(key)
            cell = cells.get(f"{column}{excel_row}")
            if expected is None:
                if cell is not None:
                    raise WorkbookUpdateError(f"Staged {key} cell should be blank.")
                continue
            if not isinstance(expected, _TimingValue):
                raise WorkbookUpdateError(f"Approved {key} value was not normalized.")
            if cell is None or cell.find("m:f", namespace) is not None:
                raise WorkbookUpdateError(f"Staged {key} cell is missing or unsafe.")
            if cell.attrib.get("t") != "inlineStr":
                raise WorkbookUpdateError(f"Staged {key} value is not stored as safe text.")
            actual_text = "".join(
                text_node.text or "" for text_node in cell.findall(".//m:t", namespace)
            )
            if actual_text != expected.text:
                raise WorkbookUpdateError(f"Staged {key} value does not match the approved review.")


def _commit_race_import_locked(
    workbook_path: str | Path,
    *,
    metadata: RaceMetadata,
    rows: Iterable[Mapping[str, object]],
    scoring_profile: Mapping[int, float],
    expected_sha256: str,
    approved: bool,
    require_complete_timing: bool = False,
    backup_directory: str | Path | None = None,
) -> CommitResult:
    """Run a complete import while the caller holds the workbook lock."""
    if not approved:
        raise ApprovalRequiredError("Workbook update requires explicit approval from the review screen.")

    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise WorkbookUpdateError(f"Workbook was not found: {path}")
    current_sha = workbook_fingerprint(path)
    if current_sha != expected_sha256:
        raise StaleWorkbookError("The workbook changed after this review was created. Extract and review again.")

    before = core.load_standings_data(path)
    if event_already_exists(before, metadata):
        raise DuplicateEventError("This race or sprint is already present in the workbook.")
    calendar_row = _calendar_excel_row(path, metadata)
    if calendar_row is None:
        raise WorkbookUpdateError(
            "The event does not exactly match one Calendar row for this league, round, and Grand Prix."
        )
    if not _calendar_identity_is_unambiguous(before, metadata):
        raise WorkbookUpdateError(
            "The Calendar league does not identify exactly this championship; use the manual Excel workflow."
        )
    # Resolve configured snapshots first so a new league's very first event,
    # replacement drivers, team changes, custom Sprint rules, and optional
    # fastest-lap bonus all have an authoritative workbook source. Legacy
    # championships continue to derive the same values from result history.
    import league_runtime

    authority = league_runtime.resolve_event_authority(path, before, metadata)
    if authority.league_key is not None:
        import league_config

        try:
            league_config.require_active_configured_league(
                league_config.load_config_tables(path),
                authority.league_key.league_id,
            )
        except league_config.LeagueConfigError as exc:
            raise WorkbookUpdateError(
                f"The configured league cannot accept new results: {exc}"
            ) from exc
    roster = list(authority.roster)
    verified_scoring = authority.base_points

    supplied_scoring = {int(position): float(points) for position, points in scoring_profile.items()}
    if supplied_scoring != verified_scoring:
        raise WorkbookUpdateError("The approved scoring profile does not match the workbook's verified rules.")
    supplied_rows = [dict(row) for row in rows]
    scored_rows, _ = league_runtime.apply_configured_points(supplied_rows, authority)
    total_scoring = {
        int(row["Position"]): float(row["Points"])
        for row in scored_rows
    }
    for supplied, expected in zip(supplied_rows, scored_rows, strict=True):
        if "Points" in supplied and float(supplied["Points"]) != float(expected["Points"]):
            raise WorkbookUpdateError(
                f"Points for position {expected['Position']} do not match the configured rules."
            )
    normalized_rows = _validate_commit_rows(
        scored_rows,
        total_scoring,
        require_complete_timing=require_complete_timing,
    )
    roster_map = {entry.driver: entry.team for entry in roster}
    if {row["Driver"] for row in normalized_rows} != set(roster_map):
        raise WorkbookUpdateError("Approved rows must contain every controlled-roster driver exactly once.")
    if any(roster_map[row["Driver"]] != row["Team"] for row in normalized_rows):
        raise WorkbookUpdateError("An approved team does not match the controlled championship roster.")

    first_row = _first_available_result_row(path)
    last_row = first_row + len(normalized_rows) - 1
    existing_a_l = pd.read_excel(path, sheet_name="Leagues", usecols="A:L")
    for excel_row in range(first_row, last_row + 1):
        dataframe_index = excel_row - 2
        if dataframe_index < len(existing_a_l) and existing_a_l.iloc[dataframe_index].notna().any():
            raise WorkbookUpdateError(f"Target worksheet row {excel_row} is not empty in columns A:L.")

    with ZipFile(path, "r") as archive:
        sheet_paths = _sheet_paths(archive)
        if "Leagues" not in sheet_paths:
            raise WorkbookUpdateError("Required sheet 'Leagues' was not found in the workbook package.")
        leagues_part = sheet_paths["Leagues"]
        leagues_xml = archive.read(leagues_part)
        for offset, row in enumerate(normalized_rows):
            leagues_xml = _replace_row_cells(
                leagues_xml,
                first_row + offset,
                _workbook_row(metadata, row),
                tuple("ABCDEFGHIJKL"),
            )
        replacements: dict[str, bytes] = {leagues_part: leagues_xml}
        _extend_pivot_source_if_needed(
            archive,
            replacements,
            last_excel_row=last_row,
        )

        calendar_part = sheet_paths.get("Calendar")
        calendar_updated = bool(metadata.event_type.upper() == "R" and calendar_row and calendar_part)
        if calendar_updated and calendar_part:
            calendar_xml = archive.read(calendar_part)
            replacements[calendar_part] = _replace_row_cells(
                calendar_xml,
                int(calendar_row),
                {"F": "Done"},
                ("F",),
            )

    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.race-import-", suffix=".xlsx", dir=path.parent)
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        _copy_archive_with_replacements(path, temporary_path, replacements)
        _verify_untouched_parts(path, temporary_path, set(replacements))
        core.validate_workbook(temporary_path)
        _verify_timing_cells(
            temporary_path,
            worksheet_part=leagues_part,
            first_excel_row=first_row,
            rows=normalized_rows,
        )
        after = core.load_standings_data(temporary_path)
        imported = after[_event_mask(after, metadata)].sort_values("Finish Pos")
        if len(after) != len(before) + len(normalized_rows) or len(imported) != len(normalized_rows):
            raise WorkbookUpdateError("Staged workbook row-count verification failed.")
        expected = pd.DataFrame(normalized_rows).sort_values("Position").reset_index(drop=True)
        actual = imported[["Finish Pos", "Driver", "Team", "Points"]].rename(columns={"Finish Pos": "Position"}).reset_index(drop=True)
        actual["Position"] = actual["Position"].astype(int)
        actual["Points"] = actual["Points"].astype(float)
        expected_values = expected[["Position", "Driver", "Team", "Points"]].copy()
        expected_values["Position"] = expected_values["Position"].astype(int)
        expected_values["Points"] = expected_values["Points"].astype(float)
        if not actual.equals(expected_values):
            raise WorkbookUpdateError("Staged workbook values do not match the approved review.")

        # The advisory lock serializes importer sessions. This final hash also
        # detects a non-cooperating Excel/manual writer before replacement.
        if workbook_fingerprint(path) != current_sha:
            raise StaleWorkbookError(
                "The workbook changed while this update was staged. Review the current workbook and try again."
            )
        backup_root = Path(backup_directory) if backup_directory else path.parent / ".codex-tmp" / "race-import-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_root / f"{path.stem}.before-{timestamp}-{current_sha[:8]}.xlsx"
        if backup_path.exists():
            backup_path = backup_root / f"{path.stem}.before-{timestamp}-{current_sha[:8]}-{uuid4().hex[:6]}.xlsx"
        shutil.copy2(path, backup_path)
        if workbook_fingerprint(backup_path) != current_sha:
            raise StaleWorkbookError("The recovery copy did not match the reviewed workbook; nothing was replaced.")
        # Preserve the original file's basic metadata and POSIX mode rather
        # than replacing it with mkstemp's restrictive defaults.
        shutil.copystat(path, temporary_path)
        if workbook_fingerprint(path) != current_sha:
            raise StaleWorkbookError(
                "The workbook changed after its recovery copy was verified. Nothing was replaced."
            )
        try:
            os.replace(temporary_path, path)
        except PermissionError as exc:
            raise WorkbookUpdateError(
                "Excel appears to have the workbook open. Close it and confirm again; the original was not changed."
            ) from exc
        return CommitResult(
            rows_added=len(normalized_rows),
            first_excel_row=first_row,
            last_excel_row=last_row,
            backup_path=backup_path,
            calendar_updated=calendar_updated,
            workbook_sha256=workbook_fingerprint(path),
        )
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def commit_race_import(
    workbook_path: str | Path,
    *,
    metadata: RaceMetadata,
    rows: Iterable[Mapping[str, object]],
    scoring_profile: Mapping[int, float],
    expected_sha256: str,
    approved: bool,
    require_complete_timing: bool = False,
    backup_directory: str | Path | None = None,
) -> CommitResult:
    """Validate, stage, back up, and atomically commit one complete event.

    Approved row mappings may contain optional ``Time`` and ``Fastest Lap``
    strings. Accepted values are stored exactly as reviewed text in columns K
    and L; missing values leave those cells blank. Protected Admin callers set
    ``require_complete_timing=True`` to require both fields on every row and
    canonicalize them through the importer timing rules immediately before the
    transaction is staged.
    """
    if not approved:
        raise ApprovalRequiredError("Workbook update requires explicit approval from the review screen.")

    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise WorkbookUpdateError(f"Workbook was not found: {path}")

    # The stale-review check is deliberately performed inside this lock by
    # ``_commit_race_import_locked``. The lock remains held through staging,
    # backup creation, atomic replacement, and the final fingerprint.
    with _workbook_lock(path):
        return _commit_race_import_locked(
            path,
            metadata=metadata,
            rows=rows,
            scoring_profile=scoring_profile,
            expected_sha256=expected_sha256,
            approved=approved,
            require_complete_timing=require_complete_timing,
            backup_directory=backup_directory,
        )
