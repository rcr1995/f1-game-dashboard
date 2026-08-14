"""Preservation-oriented workbook transactions for protected league setup.

The public dashboard workbook contains OOXML parts that ordinary spreadsheet
round-trips can discard.  This module therefore appends only explicit
configuration rows and Calendar rows, adds missing configuration worksheets as
minimal OOXML parts, verifies every unrelated archive member byte-for-byte,
creates a recovery copy, and atomically replaces the reviewed workbook.

Business validation lives in :mod:`league_config`.  This module is the final
structural trust boundary: it rejects duplicate identities and unsafe cell
values even when called outside the Streamlit UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as wall_time, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Mapping, Sequence
from uuid import uuid4
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

import pandas as pd

import dashboard_core as core
import race_workbook as race_book


class LeagueWorkbookError(race_book.WorkbookUpdateError):
    """Raised when a protected league configuration cannot be committed."""


CONFIG_SHEET_HEADERS: dict[str, tuple[str, ...]] = {
    "League Config": (
        "League ID",
        "Game",
        "Season",
        "League Name",
        "Status",
        "Cloned From League ID",
        "Created UTC",
        "Schema Version",
    ),
    "Roster Config": (
        "League ID",
        "Effective From Round",
        "Driver Name",
        "Team Name",
        "OCR Aliases",
    ),
    "Scoring Profiles": (
        "Profile ID",
        "League ID",
        "Event Type",
        "Effective From Round",
        "Fastest Lap Bonus",
        "Fastest Lap Max Finish",
    ),
    "Scoring Points": (
        "Profile ID",
        "Position",
        "Points",
    ),
}

CALENDAR_COLUMNS: tuple[str, ...] = (
    "League Name",
    "Round",
    "Date",
    "GP Name",
    "Circuit",
    "Status",
    "Time (Lisbon)",
    "Game",
    "Season",
    "Has Sprint",
    "GP Lookup",
    "Circuit Lookup",
    "League ID",
)

_CALENDAR_COLUMN_LETTERS = dict(zip(CALENDAR_COLUMNS, tuple("ABCDEFGHIJKLM"), strict=True))
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
_INVALID_CELL_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class LeagueWorkbookMutation:
    """Normalized rows to append in one approved transaction."""

    league_config: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    roster_config: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    scoring_profiles: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    scoring_points: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    calendar: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    # Existing configured leagues that the reviewed setup explicitly closes
    # as part of activating the next league. Only the Status cell is changed.
    complete_league_ids: tuple[str, ...] = field(default_factory=tuple)

    def by_sheet(self) -> dict[str, tuple[Mapping[str, object], ...]]:
        return {
            "League Config": tuple(self.league_config),
            "Roster Config": tuple(self.roster_config),
            "Scoring Profiles": tuple(self.scoring_profiles),
            "Scoring Points": tuple(self.scoring_points),
        }

    def is_empty(self) -> bool:
        return not any(self.by_sheet().values()) and not self.calendar and not self.complete_league_ids


@dataclass(frozen=True)
class LeagueWorkbookCommitResult:
    workbook_sha256: str
    backup_path: Path
    rows_added_by_sheet: Mapping[str, int]
    calendar_rows_added: int
    changed_parts: tuple[str, ...]


def _safe_text(value: object, *, label: str, allow_blank: bool = True) -> str:
    if value is None or (not isinstance(value, str) and bool(pd.isna(value))):
        if allow_blank:
            return ""
        raise LeagueWorkbookError(f"{label} cannot be blank.")
    text = str(value).strip()
    if not text and not allow_blank:
        raise LeagueWorkbookError(f"{label} cannot be blank.")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
        raise LeagueWorkbookError(f"{label} contains unsupported control characters.")
    # Inline strings do not execute as formulas, but reject formula-shaped
    # administrator text at this trust boundary as an additional safeguard.
    if text.startswith(_INVALID_CELL_PREFIXES):
        raise LeagueWorkbookError(f"{label} cannot start with a spreadsheet formula prefix.")
    return text


def _cell_xml(column: str, row_number: int, value: object, *, style: int | None = None) -> str:
    reference = f"{column}{row_number}"
    style_attribute = f' s="{style}"' if style is not None else ""
    if isinstance(value, bool):
        return f'<c r="{reference}"{style_attribute} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not pd.isna(value):
        numeric = int(value) if float(value).is_integer() else format(float(value), ".15g")
        return f'<c r="{reference}"{style_attribute}><v>{numeric}</v></c>'
    text = _safe_text(value, label=reference)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f'<c r="{reference}"{style_attribute} t="inlineStr">'
        f'<is><t{preserve}>{xml_escape(text)}</t></is></c>'
    )


def _row_xml(
    row_number: int,
    values: Sequence[object],
    *,
    header: bool = False,
    styles: Mapping[int, int] | None = None,
) -> str:
    styles = styles or {}
    cells = []
    for index, value in enumerate(values, start=1):
        if value is None or value == "":
            continue
        column = _column_letter(index)
        cells.append(
            _cell_xml(
                column,
                row_number,
                value,
                style=7 if header else styles.get(index),
            )
        )
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _column_letter(index: int) -> str:
    output = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        output = chr(65 + remainder) + output
    return output


def _worksheet_xml(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    last_column = _column_letter(len(headers))
    last_row = len(rows) + 1
    body = [_row_xml(1, headers, header=True)]
    body.extend(_row_xml(index + 2, row) for index, row in enumerate(rows))
    def display_length(value: object) -> int:
        if value is None or (not isinstance(value, str) and bool(pd.isna(value))):
            return 0
        if isinstance(value, datetime):
            return 24
        if isinstance(value, date):
            return 10
        if isinstance(value, wall_time):
            return 8
        return len(str(value))

    widths = "".join(
        f'<col min="{index}" max="{index}" width="{min(42, max(12, len(header) + 3, max((display_length(row[index - 1]) + 2 for row in rows), default=0)))}" customWidth="1"/>'
        for index, header in enumerate(headers, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{_MAIN_NS}">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{widths}</cols>'
        f'<sheetData>{"".join(body)}</sheetData>'
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        '</worksheet>'
    ).encode("utf-8")


def _last_worksheet_row(payload: bytes) -> int:
    rows = [int(match) for match in re.findall(rb'<row\b[^>]*\br="(\d+)"', payload)]
    return max(rows, default=0)


def _append_rows_to_worksheet(
    payload: bytes,
    rows: Sequence[Sequence[object]],
    *,
    width: int,
) -> tuple[bytes, int, int]:
    text = payload.decode("utf-8")
    closing_index = text.find("</sheetData>")
    if closing_index < 0:
        raise LeagueWorkbookError("Worksheet XML does not contain sheetData.")
    first_row = _last_worksheet_row(payload) + 1
    generated = "".join(_row_xml(first_row + offset, row) for offset, row in enumerate(rows))
    text = text[:closing_index] + generated + text[closing_index:]
    last_row = first_row + len(rows) - 1
    last_column = _column_letter(width)
    dimension = f"A1:{last_column}{last_row}"
    if re.search(r'<dimension\b[^>]*/>', text):
        text = re.sub(r'<dimension\b[^>]*/>', f'<dimension ref="{dimension}"/>', text, count=1)
    else:
        insert_at = text.find(">") + 1
        text = text[:insert_at] + f'<dimension ref="{dimension}"/>' + text[insert_at:]
    if re.search(r'<autoFilter\b[^>]*/>', text):
        text = re.sub(r'<autoFilter\b[^>]*/>', f'<autoFilter ref="{dimension}"/>', text, count=1)
    return text.encode("utf-8"), first_row, last_row


def _excel_date_serial(value: object) -> float:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise LeagueWorkbookError(f"Calendar Date is invalid: {value!r}.") from exc
    return float((parsed - date(1899, 12, 30)).days)


def _excel_time_serial(value: object) -> float:
    if isinstance(value, datetime):
        parsed = value.time().replace(tzinfo=None)
    elif isinstance(value, wall_time):
        parsed = value.replace(tzinfo=None)
    else:
        raw = str(value).strip()
        try:
            parsed = wall_time.fromisoformat(raw)
        except ValueError as exc:
            raise LeagueWorkbookError(f"Calendar Time (Lisbon) is invalid: {value!r}.") from exc
    total_seconds = parsed.hour * 3600 + parsed.minute * 60 + parsed.second
    return total_seconds / 86400.0


def _calendar_boolean(value: object, *, label: str = "Has Sprint") -> bool:
    try:
        return core._calendar_boolean(value, column=label)
    except core.WorkbookValidationError as exc:
        raise LeagueWorkbookError(str(exc)) from exc


def _calendar_values(row: Mapping[str, object]) -> tuple[object, ...]:
    required = ("League Name", "Round", "Date", "GP Name", "Circuit", "Time (Lisbon)")
    missing = [name for name in required if row.get(name) in {None, ""}]
    if missing:
        raise LeagueWorkbookError("Calendar row is missing: " + ", ".join(missing))
    try:
        round_number = int(row["Round"])
    except (TypeError, ValueError) as exc:
        raise LeagueWorkbookError("Calendar Round must be a positive integer.") from exc
    if round_number < 1:
        raise LeagueWorkbookError("Calendar Round must be a positive integer.")
    league = _safe_text(row["League Name"], label="Calendar League Name", allow_blank=False)
    gp_name = _safe_text(row["GP Name"], label="Calendar GP Name", allow_blank=False)
    circuit = _safe_text(row["Circuit"], label="Calendar Circuit", allow_blank=False)
    status = _safe_text(row.get("Status") or "Upcoming", label="Calendar Status", allow_blank=False)
    if status.casefold() != "upcoming":
        raise LeagueWorkbookError("New Calendar rows must start with Status 'Upcoming'.")
    return (
        league,
        round_number,
        _excel_date_serial(row["Date"]),
        gp_name,
        circuit,
        "Upcoming",
        _excel_time_serial(row["Time (Lisbon)"]),
        _safe_text(row.get("Game"), label="Calendar Game"),
        _safe_text(row.get("Season"), label="Calendar Season"),
        _calendar_boolean(row.get("Has Sprint", False)),
        _safe_text(row.get("GP Lookup") or gp_name, label="Calendar GP Lookup"),
        _safe_text(row.get("Circuit Lookup") or circuit, label="Calendar Circuit Lookup"),
        _safe_text(row.get("League ID"), label="Calendar League ID"),
    )


def _append_calendar_rows(payload: bytes, rows: Sequence[Mapping[str, object]]) -> tuple[bytes, int, int]:
    # A:G are the long-standing public Calendar schema and K:L are the
    # workbook's existing GP/circuit lookup helper.  Use previously blank
    # H:J and M for protected identity metadata without moving either range.
    payload = race_book._replace_row_cells(
        payload,
        1,
        {"H": "Game", "I": "Season", "J": "Has Sprint", "M": "League ID"},
        ("H", "I", "J", "M"),
    )
    values = [_calendar_values(row) for row in rows]
    updated, first_row, last_row = _append_rows_to_worksheet(payload, values, width=13)
    text = updated.decode("utf-8")
    for column in ("H", "I", "J", "M"):
        text = text.replace(f'<c r="{column}1" t="inlineStr">', f'<c r="{column}1" s="7" t="inlineStr">')
    for excel_row in range(first_row, last_row + 1):
        text = text.replace(f'<c r="C{excel_row}">', f'<c r="C{excel_row}" s="9">')
        text = text.replace(f'<c r="G{excel_row}">', f'<c r="G{excel_row}" s="12">')
    return text.encode("utf-8"), first_row, last_row


def _normalize_config_row(sheet: str, row: Mapping[str, object]) -> tuple[object, ...]:
    headers = CONFIG_SHEET_HEADERS[sheet]
    extra = set(row) - set(headers)
    if extra:
        raise LeagueWorkbookError(f"{sheet} row contains unsupported field(s): {', '.join(sorted(extra))}.")
    required_by_sheet = {
        "League Config": {"League ID", "Game", "Season", "League Name", "Status", "Created UTC", "Schema Version"},
        "Roster Config": {"League ID", "Effective From Round", "Driver Name", "Team Name"},
        "Scoring Profiles": {"Profile ID", "League ID", "Event Type", "Effective From Round", "Fastest Lap Bonus"},
        "Scoring Points": {"Profile ID", "Position", "Points"},
    }
    missing = [header for header in required_by_sheet[sheet] if row.get(header) in {None, ""}]
    if missing:
        raise LeagueWorkbookError(f"{sheet} row is missing: {', '.join(sorted(missing))}.")
    values: list[object] = []
    numeric_headers = {
        "Effective From Round",
        "Position",
        "Points",
        "Fastest Lap Bonus",
        "Fastest Lap Max Finish",
        "Schema Version",
    }
    for header in headers:
        value = row.get(header, "")
        if header in numeric_headers and value not in {None, ""}:
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise LeagueWorkbookError(f"{sheet} {header} must be numeric.") from exc
            if not number >= 0:
                raise LeagueWorkbookError(f"{sheet} {header} cannot be negative.")
            value = int(number) if number.is_integer() else number
        elif value not in {None, ""}:
            value = _safe_text(value, label=f"{sheet} {header}")
        values.append("" if value is None else value)
    return tuple(values)


def _dataframe_if_present(path: Path, sheet: str) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet, dtype=object)
    except ValueError:
        return pd.DataFrame(columns=CONFIG_SHEET_HEADERS[sheet])


def _key_set(data: pd.DataFrame, columns: Sequence[str]) -> set[tuple[str, ...]]:
    if data.empty or not set(columns).issubset(data.columns):
        return set()
    return {
        tuple(str(value).strip().casefold() for value in values)
        for values in data[list(columns)].fillna("").itertuples(index=False, name=None)
    }


def _assert_no_duplicate_keys(path: Path, mutation: LeagueWorkbookMutation) -> None:
    key_columns = {
        "League Config": (("League ID",), ("Game", "Season", "League Name")),
        "Roster Config": (("League ID", "Effective From Round", "Driver Name"),),
        "Scoring Profiles": (("Profile ID",), ("League ID", "Event Type", "Effective From Round")),
        "Scoring Points": (("Profile ID", "Position"),),
    }
    for sheet, rows in mutation.by_sheet().items():
        if not rows:
            continue
        existing = _dataframe_if_present(path, sheet)
        normalized = [dict(zip(CONFIG_SHEET_HEADERS[sheet], _normalize_config_row(sheet, row), strict=True)) for row in rows]
        incoming = pd.DataFrame(normalized)
        for columns in key_columns[sheet]:
            existing_keys = _key_set(existing, columns)
            incoming_keys = _key_set(incoming, columns)
            if len(incoming_keys) != len(incoming):
                raise LeagueWorkbookError(f"{sheet} contains duplicate {'/'.join(columns)} values.")
            if existing_keys & incoming_keys:
                raise LeagueWorkbookError(f"{sheet} already contains this {'/'.join(columns)} value.")

    if mutation.calendar:
        calendar = core.load_calendar_data(path)
        legacy_keys = {
            (
                str(row.get("League Name", "")).strip().casefold(),
                int(row["Round"]),
                str(row.get("GP Name", "")).strip().casefold(),
            )
            for row in mutation.calendar
        }
        if len(legacy_keys) != len(mutation.calendar):
            raise LeagueWorkbookError("Calendar contains duplicate league/round/Grand Prix rows.")
        existing_keys = {
            (str(league).strip().casefold(), int(round_number), str(gp).strip().casefold())
            for league, round_number, gp in calendar[["League Name", "Round", "GP Name"]]
            .dropna(subset=["Round"])
            .itertuples(index=False, name=None)
        }
        if existing_keys & legacy_keys:
            raise LeagueWorkbookError("Calendar already contains one of the proposed events.")


def _assert_leagues_finished_before_completion(
    path: Path,
    league_ids: Sequence[str],
) -> None:
    if not league_ids:
        return
    try:
        calendar = pd.read_excel(path, sheet_name="Calendar", dtype=object)
    except ValueError as exc:
        raise LeagueWorkbookError("Calendar is required before completing an active league.") from exc
    required_calendar = {
        "League ID",
        "League Name",
        "Round",
        "GP Name",
        "Status",
        "Game",
        "Season",
        "Has Sprint",
    }
    if not required_calendar.issubset(calendar.columns):
        raise LeagueWorkbookError(
            "The active managed league Calendar lacks protected identity or Sprint metadata "
            "and cannot be completed automatically."
        )
    try:
        results = pd.read_excel(path, sheet_name="Leagues", usecols="A:L", dtype=object)
    except ValueError as exc:
        raise LeagueWorkbookError(
            "Published results are required before completing an active league."
        ) from exc
    required_results = {
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
    }
    if not required_results.issubset(results.columns):
        raise LeagueWorkbookError(
            "Published results do not contain the protected event schema."
        )

    import league_config as config

    tables = config.load_config_tables(path)
    keys = {key.league_id: key for key in config.configured_league_keys(tables)}

    def event_is_complete(
        *,
        key: object,
        round_number: int,
        gp_name: str,
        event_type: str,
        expected_roster: Sequence[object],
    ) -> bool:
        event_types = results["Type"].fillna("R").astype(str).str.strip().str.upper()
        selected_results = results[
            results["Game"].fillna("").astype(str).str.strip().eq(key.game)
            & results["Season"].fillna("").astype(str).str.strip().eq(key.season)
            & results["League Name"].fillna("").astype(str).str.strip().eq(key.league_name)
            & pd.to_numeric(results["Round"], errors="coerce").eq(round_number)
            & event_types.eq(event_type)
            & results["GP Name"].fillna("").astype(str).str.strip().eq(gp_name)
        ].copy()
        if len(selected_results) != len(expected_roster) or selected_results.empty:
            return False
        positions = pd.to_numeric(selected_results["Finish Pos"], errors="coerce")
        points = pd.to_numeric(selected_results["Points"], errors="coerce")
        if (
            positions.isna().any()
            or points.isna().any()
            or points.lt(0).any()
            or not points.map(lambda value: math.isfinite(float(value))).all()
            or not positions.map(lambda value: float(value).is_integer()).all()
            or set(positions.astype(int)) != set(range(1, len(expected_roster) + 1))
        ):
            return False
        actual_roster = {
            (
                config.normalize_identity(driver),
                config.normalize_identity(team),
            )
            for driver, team in selected_results[["Driver", "Team"]]
            .fillna("")
            .itertuples(index=False, name=None)
        }
        expected = {
            (
                config.normalize_identity(row.driver_name),
                config.normalize_identity(row.team_name),
            )
            for row in expected_roster
        }
        return (
            len(actual_roster) == len(expected_roster)
            and all(driver and team for driver, team in actual_roster)
            and actual_roster == expected
        )

    for league_id in league_ids:
        key = keys.get(str(league_id).strip())
        if key is None:
            raise LeagueWorkbookError(
                f"Active league {league_id!r} has no unique protected configuration."
            )
        selected = calendar[
            calendar["League ID"].fillna("").astype(str).str.strip().eq(str(league_id).strip())
        ].copy()
        if selected.empty:
            raise LeagueWorkbookError(f"Active league {league_id!r} has no managed Calendar rows.")
        numeric_rounds = pd.to_numeric(selected["Round"], errors="coerce")
        if (
            numeric_rounds.isna().any()
            or not numeric_rounds.map(lambda value: float(value).is_integer()).all()
            or numeric_rounds.astype(int).duplicated(keep=False).any()
        ):
            raise LeagueWorkbookError(
                f"Active league {league_id!r} Calendar rounds are invalid or duplicated."
            )
        unfinished = selected[
            ~selected["Status"].fillna("").astype(str).str.strip().str.casefold().eq("done")
        ]
        if not unfinished.empty:
            raise LeagueWorkbookError(
                f"Active league {league_id!r} still has unfinished Calendar rounds and cannot be completed."
            )
        for index, calendar_row in selected.iterrows():
            round_number = int(numeric_rounds.loc[index])
            def cell_text(column: str) -> str:
                value = calendar_row[column]
                return "" if value is None or pd.isna(value) else str(value).strip()

            gp_name = cell_text("GP Name")
            if not gp_name or (
                cell_text("Game"),
                cell_text("Season"),
                cell_text("League Name"),
            ) != (key.game, key.season, key.league_name):
                raise LeagueWorkbookError(
                    f"Active league {league_id!r} Calendar identity is inconsistent at round {round_number}."
                )
            try:
                expected_roster = config.resolve_roster_snapshot(
                    tables, key.league_id, round_number
                )
            except config.LeagueConfigError as exc:
                raise LeagueWorkbookError(
                    f"Active league {league_id!r} has no valid roster at round {round_number}."
                ) from exc
            required_types = ["R"]
            if _calendar_boolean(
                calendar_row["Has Sprint"], label=f"Has Sprint at round {round_number}"
            ):
                required_types.append("SR")
            for event_type in required_types:
                if not event_is_complete(
                    key=key,
                    round_number=round_number,
                    gp_name=gp_name,
                    event_type=event_type,
                    expected_roster=expected_roster,
                ):
                    session = "Sprint" if event_type == "SR" else "Race"
                    raise LeagueWorkbookError(
                        f"Active league {league_id!r} round {round_number} has no complete exact {session} result."
                    )


def _assert_snapshot_targets_are_active_and_scheduled(
    path: Path,
    mutation: LeagueWorkbookMutation,
) -> None:
    snapshot_keys: set[tuple[str, int]] = set()
    for sheet, rows in (
        ("Roster Config", mutation.roster_config),
        ("Scoring Profiles", mutation.scoring_profiles),
    ):
        for row in rows:
            normalized = dict(
                zip(
                    CONFIG_SHEET_HEADERS[sheet],
                    _normalize_config_row(sheet, row),
                    strict=True,
                )
            )
            league_id = str(normalized["League ID"]).strip()
            effective = int(normalized["Effective From Round"])
            snapshot_keys.add((league_id, effective))
    if not snapshot_keys:
        return

    statuses: dict[str, str] = {}
    existing_ids: set[str] = set()
    existing = _dataframe_if_present(path, "League Config")
    if {"League ID", "Status"}.issubset(existing.columns):
        for league_id, status in existing[["League ID", "Status"]].fillna("").itertuples(
            index=False, name=None
        ):
            normalized_id = str(league_id).strip()
            if normalized_id:
                existing_ids.add(normalized_id)
                statuses[normalized_id] = str(status).strip().title()
    for row in mutation.league_config:
        normalized = dict(
            zip(
                CONFIG_SHEET_HEADERS["League Config"],
                _normalize_config_row("League Config", row),
                strict=True,
            )
        )
        statuses[str(normalized["League ID"]).strip()] = str(
            normalized["Status"]
        ).strip().title()
    for league_id, _ in snapshot_keys:
        if league_id in existing_ids and statuses.get(league_id) != "Active":
            raise LeagueWorkbookError(
                f"Roster and scoring snapshots may be added only to an Active league: {league_id!r}."
            )

    calendar_counts: dict[tuple[str, int], int] = {}
    calendar = core.load_calendar_data(path)
    if {"League ID", "Round"}.issubset(calendar.columns):
        for league_id, round_value in calendar[["League ID", "Round"]].itertuples(
            index=False, name=None
        ):
            normalized_id = str(league_id or "").strip()
            numeric = pd.to_numeric(round_value, errors="coerce")
            if not normalized_id or pd.isna(numeric) or not float(numeric).is_integer():
                continue
            key = (normalized_id, int(numeric))
            calendar_counts[key] = calendar_counts.get(key, 0) + 1
    for row in mutation.calendar:
        values = _calendar_values(row)
        league_id = str(values[12]).strip()
        if not league_id:
            raise LeagueWorkbookError(
                "A managed Calendar row must contain its immutable League ID."
            )
        key = (league_id, int(values[1]))
        calendar_counts[key] = calendar_counts.get(key, 0) + 1
    for league_id, effective in sorted(snapshot_keys):
        if calendar_counts.get((league_id, effective), 0) != 1:
            raise LeagueWorkbookError(
                f"Snapshot round {effective} for league {league_id!r} must match exactly one managed Calendar row."
            )


def _assert_snapshots_do_not_redefine_published_rounds(
    path: Path,
    mutation: LeagueWorkbookMutation,
) -> None:
    effective_by_league: dict[str, int] = {}
    for row in (*mutation.roster_config, *mutation.scoring_profiles):
        league_id = str(row.get("League ID") or "").strip()
        if not league_id:
            continue
        try:
            effective = int(row["Effective From Round"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LeagueWorkbookError("Snapshot Effective From Round is invalid.") from exc
        effective_by_league[league_id] = min(
            effective,
            effective_by_league.get(league_id, effective),
        )
    if not effective_by_league:
        return

    import league_config as config

    tables = config.load_config_tables(path)
    keys = {key.league_id: key for key in config.configured_league_keys(tables)}
    standings = core.load_standings_data(path)
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    for league_id, effective in effective_by_league.items():
        # A new League ID has no historical result authority to redefine.
        key = keys.get(league_id)
        if key is None:
            continue
        selected = standings[
            standings["Game"].astype(str).eq(key.game)
            & standings[season_column].astype(str).eq(key.season)
            & standings["League Name"].astype(str).eq(key.league_name)
            & pd.to_numeric(standings["Round"], errors="coerce").ge(effective)
        ]
        if "IsSeasonFinal" in selected.columns:
            selected = selected[~selected["IsSeasonFinal"].fillna(False)]
        if not selected.empty:
            raise LeagueWorkbookError(
                f"League {league_id!r} already has published results at or after round {effective}; "
                "choose the next unpublished round."
            )


def _assert_new_league_names_are_unique(
    path: Path,
    mutation: LeagueWorkbookMutation,
) -> None:
    if not mutation.league_config:
        return
    import league_config as config

    standings = core.load_standings_data(path)
    used_names = {
        config.normalize_identity(value)
        for value in standings["League Name"].dropna().tolist()
        if config.normalize_identity(value)
    }
    existing_config = _dataframe_if_present(path, "League Config")
    if "League Name" in existing_config:
        used_names.update(
            config.normalize_identity(value)
            for value in existing_config["League Name"].dropna().tolist()
            if config.normalize_identity(value)
        )
    incoming_names = [
        config.normalize_identity(
            _safe_text(row.get("League Name"), label="League Name", allow_blank=False)
        )
        for row in mutation.league_config
    ]
    if any(not name for name in incoming_names):
        raise LeagueWorkbookError(
            "A new managed League Name must contain at least one letter or number."
        )
    if len(incoming_names) != len(set(incoming_names)):
        raise LeagueWorkbookError("The proposed setup contains duplicate League Names.")
    collision = sorted(set(incoming_names) & used_names)
    if collision:
        raise LeagueWorkbookError(
            "A new managed league must use a League Name that has never been used before."
        )


def _add_sheet_parts(
    archive: ZipFile,
    sheets_to_add: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, str]]:
    replacements: dict[str, bytes] = {}
    additions: dict[str, bytes] = {}
    assigned_parts: dict[str, str] = {}
    if not sheets_to_add:
        return replacements, additions, assigned_parts

    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    content_types = ET.fromstring(archive.read("[Content_Types].xml"))

    sheets_element = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets_element is None:
        raise LeagueWorkbookError("Workbook package does not contain a sheets collection.")
    existing_sheet_ids = [int(sheet.attrib.get("sheetId", "0")) for sheet in sheets_element]
    existing_rel_ids = []
    existing_sheet_numbers = []
    for relationship in relationships.findall(f"{{{_REL_NS}}}Relationship"):
        match = re.fullmatch(r"rId(\d+)", relationship.attrib.get("Id", ""))
        if match:
            existing_rel_ids.append(int(match.group(1)))
        target_match = re.search(r"worksheets/sheet(\d+)\.xml$", relationship.attrib.get("Target", ""))
        if target_match:
            existing_sheet_numbers.append(int(target_match.group(1)))

    next_sheet_id = max(existing_sheet_ids, default=0) + 1
    next_rel_id = max(existing_rel_ids, default=0) + 1
    next_sheet_number = max(existing_sheet_numbers, default=0) + 1
    for sheet_name, payload in sheets_to_add.items():
        relationship_id = f"rId{next_rel_id}"
        part_name = f"xl/worksheets/sheet{next_sheet_number}.xml"
        ET.SubElement(
            sheets_element,
            f"{{{_MAIN_NS}}}sheet",
            {
                "name": sheet_name,
                "sheetId": str(next_sheet_id),
                f"{{{_DOC_REL_NS}}}id": relationship_id,
            },
        )
        ET.SubElement(
            relationships,
            f"{{{_REL_NS}}}Relationship",
            {
                "Id": relationship_id,
                "Type": f"{_DOC_REL_NS}/worksheet",
                "Target": f"worksheets/sheet{next_sheet_number}.xml",
            },
        )
        ET.SubElement(
            content_types,
            f"{{{_CONTENT_TYPES_NS}}}Override",
            {"PartName": f"/{part_name}", "ContentType": _WORKSHEET_CONTENT_TYPE},
        )
        additions[part_name] = payload
        assigned_parts[sheet_name] = part_name
        next_sheet_id += 1
        next_rel_id += 1
        next_sheet_number += 1

    # ElementTree keeps namespace registrations globally, so registering three
    # different default namespaces up-front gives only the final one a default
    # prefix. Serialize each package part immediately after registering its own
    # required default namespace. The OPC content-types reader used by the
    # Open XML SDK is stricter than Excel/openpyxl about prefixed `Types` roots.
    ET.register_namespace("", _MAIN_NS)
    ET.register_namespace("r", _DOC_REL_NS)
    replacements["xl/workbook.xml"] = ET.tostring(
        workbook, encoding="utf-8", xml_declaration=True
    )
    ET.register_namespace("", _REL_NS)
    replacements["xl/_rels/workbook.xml.rels"] = ET.tostring(
        relationships, encoding="utf-8", xml_declaration=True
    )
    ET.register_namespace("", _CONTENT_TYPES_NS)
    replacements["[Content_Types].xml"] = ET.tostring(
        content_types, encoding="utf-8", xml_declaration=True
    )
    return replacements, additions, assigned_parts


def _copy_archive(
    source: Path,
    destination: Path,
    replacements: Mapping[str, bytes],
    additions: Mapping[str, bytes],
) -> None:
    overlap = set(replacements) & set(additions)
    if overlap:
        raise LeagueWorkbookError("A workbook part cannot be replaced and added in one transaction.")
    try:
        with ZipFile(source, "r") as original, ZipFile(
            destination, "w", compression=ZIP_DEFLATED, allowZip64=True
        ) as updated:
            existing = set(original.namelist())
            missing = set(replacements) - existing
            if missing:
                raise LeagueWorkbookError(
                    "Workbook is missing expected XML part(s): " + ", ".join(sorted(missing))
                )
            if existing & set(additions):
                raise LeagueWorkbookError("A proposed workbook part already exists.")
            for info in original.infolist():
                updated.writestr(info, replacements.get(info.filename, original.read(info.filename)))
            for name, payload in additions.items():
                info = ZipInfo(name)
                info.compress_type = ZIP_DEFLATED
                updated.writestr(info, payload)
    except BadZipFile as exc:
        raise LeagueWorkbookError("The Excel workbook is not a valid OOXML archive.") from exc


def _verify_archive(
    source: Path,
    candidate: Path,
    *,
    replacements: Mapping[str, bytes],
    additions: Mapping[str, bytes],
) -> None:
    with ZipFile(source, "r") as original, ZipFile(candidate, "r") as updated:
        original_names = original.namelist()
        expected_names = original_names + list(additions)
        if updated.namelist() != expected_names:
            raise LeagueWorkbookError("Workbook package parts changed unexpectedly during staging.")
        for name in original_names:
            expected = replacements.get(name, original.read(name))
            if updated.read(name) != expected:
                raise LeagueWorkbookError(f"Workbook part '{name}' changed unexpectedly during staging.")
        for name, expected in additions.items():
            if updated.read(name) != expected:
                raise LeagueWorkbookError(f"New workbook part '{name}' did not stage exactly.")


def _verify_staged_rows(path: Path, mutation: LeagueWorkbookMutation) -> None:
    for sheet, rows in mutation.by_sheet().items():
        if not rows:
            continue
        data = pd.read_excel(path, sheet_name=sheet, dtype=object)
        headers = CONFIG_SHEET_HEADERS[sheet]
        if tuple(data.columns) != headers:
            raise LeagueWorkbookError(f"Staged {sheet} headers do not match the protected schema.")
        expected = [tuple(_normalize_config_row(sheet, row)) for row in rows]
        actual = [tuple("" if pd.isna(value) else value for value in values) for values in data.tail(len(rows)).itertuples(index=False, name=None)]
        for expected_row, actual_row in zip(expected, actual, strict=True):
            for expected_value, actual_value in zip(expected_row, actual_row, strict=True):
                if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                    if float(actual_value) != float(expected_value):
                        raise LeagueWorkbookError(f"Staged {sheet} numeric value did not match approval.")
                elif str(actual_value).strip() != str(expected_value).strip():
                    raise LeagueWorkbookError(f"Staged {sheet} text value did not match approval.")
    if mutation.calendar:
        calendar = pd.read_excel(path, sheet_name="Calendar", dtype=object)
        tail = calendar.tail(len(mutation.calendar))
        if len(tail) != len(mutation.calendar):
            raise LeagueWorkbookError("Staged Calendar row count did not match approval.")
        for expected, (_, actual) in zip(mutation.calendar, tail.iterrows(), strict=True):
            for column in ("League Name", "Round", "GP Name", "Circuit", "Status"):
                expected_value = expected.get(column, "Upcoming" if column == "Status" else "")
                if str(actual.get(column, "")).strip() != str(expected_value).strip():
                    raise LeagueWorkbookError(f"Staged Calendar {column} did not match approval.")
    if mutation.complete_league_ids:
        leagues = pd.read_excel(path, sheet_name="League Config", dtype=object)
        for league_id in mutation.complete_league_ids:
            selected = leagues[
                leagues["League ID"].fillna("").astype(str).str.strip().eq(str(league_id).strip())
            ]
            if len(selected) != 1 or str(selected.iloc[0]["Status"]).strip() != "Completed":
                raise LeagueWorkbookError(
                    f"Staged status for league {league_id!r} did not match the approved completion."
                )


def _commit_locked(
    workbook_path: Path,
    *,
    mutation: LeagueWorkbookMutation,
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None,
) -> LeagueWorkbookCommitResult:
    if not approved:
        raise race_book.ApprovalRequiredError(
            "League configuration requires explicit approval from the complete preview."
        )
    if mutation.is_empty():
        raise LeagueWorkbookError("The approved league configuration contains no changes.")
    current_sha = race_book.workbook_fingerprint(workbook_path)
    if current_sha != expected_sha256:
        raise race_book.StaleWorkbookError(
            "The workbook changed after this league preview was created. Reload and review again."
        )
    _assert_no_duplicate_keys(workbook_path, mutation)
    _assert_leagues_finished_before_completion(
        workbook_path,
        mutation.complete_league_ids,
    )
    _assert_snapshots_do_not_redefine_published_rounds(workbook_path, mutation)
    _assert_new_league_names_are_unique(workbook_path, mutation)
    _assert_snapshot_targets_are_active_and_scheduled(workbook_path, mutation)

    with ZipFile(workbook_path, "r") as archive:
        paths = race_book._sheet_paths(archive)
        replacements: dict[str, bytes] = {}
        additions: dict[str, bytes] = {}
        missing_sheets: dict[str, bytes] = {}
        rows_added: dict[str, int] = {}

        if mutation.complete_league_ids:
            league_part = paths.get("League Config")
            if not league_part:
                raise LeagueWorkbookError("League Config is missing the league selected for completion.")
            existing_leagues = pd.read_excel(workbook_path, sheet_name="League Config", dtype=object)
            if not {"League ID", "Status"}.issubset(existing_leagues.columns):
                raise LeagueWorkbookError("League Config does not have the protected identity/status schema.")
            league_xml = archive.read(league_part)
            for league_id in mutation.complete_league_ids:
                selected = existing_leagues[
                    existing_leagues["League ID"].fillna("").astype(str).str.strip().eq(str(league_id).strip())
                ]
                if len(selected) != 1:
                    raise LeagueWorkbookError(f"League {league_id!r} was not found uniquely for completion.")
                if str(selected.iloc[0]["Status"]).strip() != "Active":
                    raise LeagueWorkbookError(f"Only an Active league can be completed automatically: {league_id!r}.")
                excel_row = int(selected.index[0]) + 2
                league_xml = race_book._replace_row_cells(
                    league_xml,
                    excel_row,
                    {"E": "Completed"},
                    ("E",),
                )
            replacements[league_part] = league_xml

        for sheet, rows in mutation.by_sheet().items():
            if not rows:
                continue
            normalized = [_normalize_config_row(sheet, row) for row in rows]
            rows_added[sheet] = len(normalized)
            if sheet in paths:
                payload = replacements.get(paths[sheet], archive.read(paths[sheet]))
                updated, _, _ = _append_rows_to_worksheet(
                    payload, normalized, width=len(CONFIG_SHEET_HEADERS[sheet])
                )
                replacements[paths[sheet]] = updated
            else:
                missing_sheets[sheet] = _worksheet_xml(CONFIG_SHEET_HEADERS[sheet], normalized)

        package_replacements, package_additions, _ = _add_sheet_parts(archive, missing_sheets)
        replacements.update(package_replacements)
        additions.update(package_additions)

        if mutation.calendar:
            calendar_part = paths.get("Calendar")
            if not calendar_part:
                raise LeagueWorkbookError("Required Calendar worksheet is missing.")
            updated_calendar, _, _ = _append_calendar_rows(
                archive.read(calendar_part), mutation.calendar
            )
            replacements[calendar_part] = updated_calendar

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{workbook_path.stem}.league-setup-",
        suffix=".xlsx",
        dir=workbook_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        _copy_archive(workbook_path, temporary_path, replacements, additions)
        _verify_archive(
            workbook_path,
            temporary_path,
            replacements=replacements,
            additions=additions,
        )
        core.validate_workbook(temporary_path)
        _verify_staged_rows(temporary_path, mutation)
        import league_config as config

        # Reopen the staged authoritative configuration and re-run the pure
        # cross-sheet invariants at the final write boundary.
        config.validate_config_tables(config.load_config_tables(temporary_path))
        if race_book.workbook_fingerprint(workbook_path) != current_sha:
            raise race_book.StaleWorkbookError(
                "The workbook changed while the league update was staged. Reload and review again."
            )
        backup_root = (
            Path(backup_directory)
            if backup_directory
            else workbook_path.parent / ".codex-tmp" / "league-setup-backups"
        )
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_root / (
            f"{workbook_path.stem}.before-league-update-{timestamp}-{current_sha[:8]}.xlsx"
        )
        if backup_path.exists():
            backup_path = backup_root / (
                f"{workbook_path.stem}.before-league-update-{timestamp}-{current_sha[:8]}-"
                f"{uuid4().hex[:6]}.xlsx"
            )
        shutil.copy2(workbook_path, backup_path)
        if race_book.workbook_fingerprint(backup_path) != current_sha:
            raise race_book.StaleWorkbookError(
                "The recovery copy did not match the reviewed workbook; nothing was replaced."
            )
        shutil.copystat(workbook_path, temporary_path)
        if race_book.workbook_fingerprint(workbook_path) != current_sha:
            raise race_book.StaleWorkbookError(
                "The workbook changed after the recovery copy was verified. Nothing was replaced."
            )
        try:
            os.replace(temporary_path, workbook_path)
        except PermissionError as exc:
            raise LeagueWorkbookError(
                "Excel appears to have the workbook open. Close it and approve the preview again."
            ) from exc
        return LeagueWorkbookCommitResult(
            workbook_sha256=race_book.workbook_fingerprint(workbook_path),
            backup_path=backup_path,
            rows_added_by_sheet=dict(rows_added),
            calendar_rows_added=len(mutation.calendar),
            changed_parts=tuple(sorted(set(replacements) | set(additions))),
        )
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def commit_league_workbook_update(
    workbook_path: str | Path,
    *,
    mutation: LeagueWorkbookMutation,
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None = None,
) -> LeagueWorkbookCommitResult:
    """Commit one approved setup/roster configuration atomically.

    The mutation is append-only.  Existing result rows, prior configuration
    snapshots, Calendar rows, formulas and other package parts are
    preserved.  A new roster/team assignment is represented by another
    complete snapshot with a later ``Effective From Round``.
    """
    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise LeagueWorkbookError(f"Workbook was not found: {path}")
    with race_book._workbook_lock(path):
        return _commit_locked(
            path,
            mutation=mutation,
            expected_sha256=expected_sha256,
            approved=approved,
            backup_directory=backup_directory,
        )


def mutation_digest(mutation: LeagueWorkbookMutation, *, source_version: str) -> str:
    """Return a stable digest used to bind a preview to explicit approval."""
    digest = hashlib.sha256()
    digest.update(str(source_version).encode("utf-8"))
    for sheet, rows in mutation.by_sheet().items():
        digest.update(sheet.encode("utf-8"))
        for row in rows:
            digest.update(repr(_normalize_config_row(sheet, row)).encode("utf-8"))
    digest.update(b"Calendar")
    for row in mutation.calendar:
        digest.update(repr(_calendar_values(row)).encode("utf-8"))
    digest.update(repr(tuple(sorted(mutation.complete_league_ids))).encode("utf-8"))
    return digest.hexdigest()


def mutation_from_setup(
    setup: object,
    *,
    complete_league_ids: Iterable[str] = (),
) -> LeagueWorkbookMutation:
    """Convert a validated :class:`league_config.LeagueSetup` to writer rows."""
    import league_config as config

    if not isinstance(setup, config.LeagueSetup):
        raise LeagueWorkbookError("League setup has an invalid protected model.")
    tables = config.config_tables_from_setup(setup)

    def records(frame: pd.DataFrame) -> tuple[Mapping[str, object], ...]:
        clean = frame.astype(object).where(pd.notna(frame), None)
        return tuple(dict(row) for row in clean.to_dict("records"))

    calendar = tuple(
        {
            "League Name": setup.key.league_name,
            "Round": row.round_number,
            "Date": row.date,
            "GP Name": row.gp_name,
            "Circuit": row.circuit,
            "Status": row.status,
            "Time (Lisbon)": row.time_lisbon,
            "Game": setup.key.game,
            "Season": setup.key.season,
            "Has Sprint": row.has_sprint,
            "GP Lookup": row.gp_name,
            "Circuit Lookup": row.circuit,
            "League ID": setup.key.league_id,
        }
        for row in setup.calendar
    )
    normalized_complete = tuple(
        dict.fromkeys(
            _safe_text(value, label="Completed League ID", allow_blank=False)
            for value in complete_league_ids
        )
    )
    return LeagueWorkbookMutation(
        league_config=records(tables.league_config),
        roster_config=records(tables.roster_config),
        scoring_profiles=records(tables.scoring_profiles),
        scoring_points=records(tables.scoring_points),
        calendar=calendar,
        complete_league_ids=normalized_complete,
    )


def commit_league_setup(
    workbook_path: str | Path,
    *,
    setup: object,
    expected_sha256: str,
    approved: bool,
    complete_league_ids: Iterable[str] = (),
    backup_directory: str | Path | None = None,
) -> LeagueWorkbookCommitResult:
    """Validate and commit one complete configuration-backed league setup."""
    import league_config as config

    path = Path(workbook_path).resolve()
    existing = config.load_config_tables(path)
    completing = tuple(str(value).strip() for value in complete_league_ids if str(value).strip())
    validation_tables = existing
    if completing and not existing.league_config.empty:
        leagues = existing.league_config.copy()
        leagues.loc[
            leagues["League ID"].astype(str).isin(completing), "Status"
        ] = "Completed"
        validation_tables = config.ConfigTables(
            leagues,
            existing.roster_config.copy(),
            existing.scoring_profiles.copy(),
            existing.scoring_points.copy(),
        )
    if not isinstance(setup, config.LeagueSetup):
        raise LeagueWorkbookError("League setup has an invalid protected model.")
    config.validate_league_setup(setup, existing=validation_tables)
    return commit_league_workbook_update(
        path,
        mutation=mutation_from_setup(setup, complete_league_ids=completing),
        expected_sha256=expected_sha256,
        approved=approved,
        backup_directory=backup_directory,
    )


def mutation_from_roster_snapshot_update(
    existing: object,
    update: object,
) -> LeagueWorkbookMutation:
    """Convert a validated effective-round roster/scoring snapshot to rows."""
    import league_config as config

    if not isinstance(existing, config.ConfigTables) or not isinstance(
        update, config.RosterSnapshotUpdate
    ):
        raise LeagueWorkbookError("Roster snapshot update has an invalid protected model.")
    config.validate_roster_snapshot_update(existing, update)
    roster_rows = tuple(
        {
            "League ID": row.league_id,
            "Effective From Round": row.effective_from_round,
            "Driver Name": row.driver_name,
            "Team Name": row.team_name,
            "OCR Aliases": config.serialize_ocr_aliases(row.ocr_aliases),
        }
        for row in update.complete_roster
    )
    profile_rows = tuple(
        {
            "Profile ID": row.profile_id,
            "League ID": row.league_id,
            "Event Type": row.event_type.upper(),
            "Effective From Round": row.effective_from_round,
            "Fastest Lap Bonus": row.fastest_lap_bonus,
            "Fastest Lap Max Finish": row.fastest_lap_max_finish,
        }
        for row in update.scoring_profiles
    )
    point_rows = tuple(
        {
            "Profile ID": row.profile_id,
            "Position": row.position,
            "Points": row.points,
        }
        for row in update.scoring_points
    )
    return LeagueWorkbookMutation(
        roster_config=roster_rows,
        scoring_profiles=profile_rows,
        scoring_points=point_rows,
    )


def commit_roster_snapshot_update(
    workbook_path: str | Path,
    *,
    update: object,
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None = None,
) -> LeagueWorkbookCommitResult:
    import league_config as config

    path = Path(workbook_path).resolve()
    existing = config.load_config_tables(path)
    mutation = mutation_from_roster_snapshot_update(existing, update)
    return commit_league_workbook_update(
        path,
        mutation=mutation,
        expected_sha256=expected_sha256,
        approved=approved,
        backup_directory=backup_directory,
    )
