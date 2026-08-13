"""Transaction-safe, preservation-oriented updates for ``F1_Standings.xlsx``.

The workbook contains pivot caches, cached formulas, and modern comment parts
that normal Excel round-trips can discard. This writer therefore changes only
the two worksheet XML parts that own race results and calendar status, copies
every other OOXML part unchanged, validates a temporary workbook, and replaces
the original only after explicit approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Mapping
from uuid import uuid4
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

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


@dataclass(frozen=True)
class RaceMetadata:
    game: str
    season: str
    league: str
    round_number: int
    event_type: str
    gp_name: str


@dataclass(frozen=True)
class CommitResult:
    rows_added: int
    first_excel_row: int
    last_excel_row: int
    backup_path: Path
    calendar_updated: bool
    workbook_sha256: str


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
        & data["GP Name"].astype(str).eq(metadata.gp_name)
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
    mask = (
        calendar["League Name"].fillna("").astype(str).str.strip().eq(metadata.league)
        & pd.to_numeric(calendar["Round"], errors="coerce").eq(metadata.round_number)
        & calendar["GP Name"].fillna("").astype(str).str.strip().eq(metadata.gp_name)
    )
    indexes = calendar.index[mask].tolist()
    if len(indexes) > 1:
        raise WorkbookUpdateError("Calendar contains more than one matching event row.")
    return int(indexes[0]) + 2 if indexes else None


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


def _validate_commit_rows(rows: Iterable[Mapping[str, object]], scoring_profile: Mapping[int, float]) -> list[dict]:
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
        normalized.append({"Position": position, "Driver": driver, "Team": team, "Points": expected_points})
    positions = [row["Position"] for row in normalized]
    drivers = [row["Driver"] for row in normalized]
    expected_positions = set(scoring_profile)
    if set(positions) != expected_positions or len(positions) != len(expected_positions):
        raise WorkbookUpdateError("Approved rows must contain every finishing position exactly once.")
    if len(drivers) != len(set(drivers)):
        raise WorkbookUpdateError("Approved rows contain a duplicate driver.")
    return sorted(normalized, key=lambda row: row["Position"])


def _workbook_row(metadata: RaceMetadata, row: Mapping[str, object]) -> dict[str, object]:
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
        "K": row.get("Time"),
        "L": row.get("Fastest Lap"),
    }


def commit_race_import(
    workbook_path: str | Path,
    *,
    metadata: RaceMetadata,
    rows: Iterable[Mapping[str, object]],
    scoring_profile: Mapping[int, float],
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None = None,
) -> CommitResult:
    """Validate, stage, back up, and atomically commit one complete event."""
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
    try:
        roster = race.derive_championship_roster(
            before,
            game=metadata.game,
            season=metadata.season,
            league=metadata.league,
        )
        verified_scoring = race.infer_scoring_profile(
            before,
            game=metadata.game,
            season=metadata.season,
            league=metadata.league,
            event_type=metadata.event_type,
            grid_size=len(roster),
        )
    except (race.RosterError, race.ScoringProfileError) as exc:
        raise WorkbookUpdateError(f"The workbook can no longer verify this import: {exc}") from exc

    supplied_scoring = {int(position): float(points) for position, points in scoring_profile.items()}
    if supplied_scoring != verified_scoring:
        raise WorkbookUpdateError("The approved scoring profile does not match the workbook's verified rules.")
    normalized_rows = _validate_commit_rows(rows, verified_scoring)
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

        calendar_row = _calendar_excel_row(path, metadata) if metadata.event_type.upper() == "R" else None
        calendar_part = sheet_paths.get("Calendar")
        calendar_updated = bool(calendar_row and calendar_part)
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
        after = core.load_standings_data(temporary_path)
        imported = after[_event_mask(after, metadata)].sort_values("Finish Pos")
        if len(after) != len(before) + len(normalized_rows) or len(imported) != len(normalized_rows):
            raise WorkbookUpdateError("Staged workbook row-count verification failed.")
        expected = pd.DataFrame(normalized_rows).sort_values("Position").reset_index(drop=True)
        actual = imported[["Finish Pos", "Driver", "Team", "Points"]].rename(columns={"Finish Pos": "Position"}).reset_index(drop=True)
        actual["Position"] = actual["Position"].astype(int)
        actual["Points"] = actual["Points"].astype(float)
        if not actual.equals(expected[["Position", "Driver", "Team", "Points"]]):
            raise WorkbookUpdateError("Staged workbook values do not match the approved review.")

        backup_root = Path(backup_directory) if backup_directory else path.parent / ".codex-tmp" / "race-import-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_root / f"{path.stem}.before-{timestamp}-{current_sha[:8]}.xlsx"
        if backup_path.exists():
            backup_path = backup_root / f"{path.stem}.before-{timestamp}-{current_sha[:8]}-{uuid4().hex[:6]}.xlsx"
        shutil.copy2(path, backup_path)
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
