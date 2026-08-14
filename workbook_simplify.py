"""Lossless, transaction-safe removal of the obsolete ``Pivot`` worksheet.

The dashboard computes standings directly from the ``Leagues`` result table;
the workbook's Pivot worksheet is only a cached Excel report.  A normal Excel
library round-trip would rewrite unrelated worksheets and may discard modern
comments, so this module performs the smallest possible OOXML package edit:

* remove the Pivot sheet and its workbook relationship;
* remove only Pivot-owned table/cache parts that become unreachable;
* update workbook metadata and content-type declarations; and
* copy every retained worksheet and unrelated package part byte-for-byte.

Both staging to a separate copy and an approved, recovery-backed atomic commit
are provided.  Re-running the migration on an already simplified workbook is
an idempotent no-op.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import tempfile
from typing import Iterable, Mapping
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import dashboard_core as core
import race_workbook


class WorkbookSimplificationError(race_workbook.WorkbookUpdateError):
    """Raised when the Pivot sheet cannot be removed without data loss."""


@dataclass(frozen=True)
class WorkbookSimplificationResult:
    """Verified result of staging or committing one simplification."""

    workbook_path: Path
    source_sha256: str
    workbook_sha256: str
    already_simplified: bool
    removed_parts: tuple[str, ...]
    changed_parts: tuple[str, ...]
    retained_sheets: tuple[str, ...]
    backup_path: Path | None = None


@dataclass(frozen=True)
class _Mutation:
    replacements: Mapping[str, bytes]
    deletions: frozenset[str]
    retained_sheets: tuple[str, ...]
    already_simplified: bool


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

_WORKBOOK_PART = "xl/workbook.xml"
_WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
_CONTENT_TYPES_PART = "[Content_Types].xml"
_APP_PROPERTIES_PART = "docProps/app.xml"
_PIVOT_SHEET_NAME = "Pivot"
_SHEET_REFERENCE = re.compile(r"(?:'Pivot'|Pivot)\s*!", re.IGNORECASE)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _relationship_part(owner_part: str) -> str:
    if not owner_part:
        return "_rels/.rels"
    path = PurePosixPath(owner_part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _resolve_target(owner_part: str, target: str) -> str:
    normalized_target = target.replace("\\", "/")
    if normalized_target.startswith("/"):
        resolved = posixpath.normpath(normalized_target.lstrip("/"))
    else:
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(owner_part), normalized_target)
        )
    if resolved in {"", "."} or resolved == ".." or resolved.startswith("../"):
        raise WorkbookSimplificationError("Workbook contains an unsafe package relationship target.")
    return resolved


def _relationships(
    archive: ZipFile,
    owner_part: str,
    *,
    replacements: Mapping[str, bytes] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    relationship_part = _relationship_part(owner_part)
    payload = (replacements or {}).get(relationship_part)
    if payload is None:
        if relationship_part not in archive.namelist():
            return ()
        payload = archive.read(relationship_part)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise WorkbookSimplificationError(
            f"Workbook relationship part '{relationship_part}' is not valid XML."
        ) from exc
    result: list[tuple[str, str, str]] = []
    for relationship in root.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relationship.attrib.get("TargetMode", "").casefold() == "external":
            continue
        relationship_id = relationship.attrib.get("Id", "")
        relationship_type = relationship.attrib.get("Type", "")
        target = relationship.attrib.get("Target", "")
        if not relationship_id or not relationship_type or not target:
            raise WorkbookSimplificationError(
                f"Workbook relationship part '{relationship_part}' is incomplete."
            )
        result.append((relationship_id, relationship_type, _resolve_target(owner_part, target)))
    return tuple(result)


def _attr(tag: bytes, name: str) -> str | None:
    match = re.search(
        rb"(?:^|\s)" + re.escape(name.encode("ascii")) + rb'="([^"]*)"',
        tag,
    )
    return html.unescape(match.group(1).decode("utf-8")) if match else None


def _replace_integer_attr(tag: bytes, name: str, value: int) -> bytes:
    pattern = re.compile(
        rb"((?:^|\s)" + re.escape(name.encode("ascii")) + rb'=")\d+("(?=\s|/?>))'
    )
    updated, count = pattern.subn(
        lambda match: match.group(1) + str(value).encode("ascii") + match.group(2),
        tag,
        count=1,
    )
    if count != 1:
        raise WorkbookSimplificationError(f"Could not update workbook attribute '{name}'.")
    return updated


def _remove_workbook_sheet(payload: bytes, *, relationship_id: str) -> bytes:
    pattern = re.compile(rb"<sheet\b[^>]*/>")
    removed = 0

    def replace(match: re.Match[bytes]) -> bytes:
        nonlocal removed
        tag = match.group(0)
        if (
            (_attr(tag, "name") or "").casefold() == _PIVOT_SHEET_NAME.casefold()
            and _attr(tag, "r:id") == relationship_id
        ):
            removed += 1
            return b""
        return tag

    updated = pattern.sub(replace, payload)
    if removed != 1:
        raise WorkbookSimplificationError("Could not remove exactly one Pivot worksheet declaration.")
    return updated


def _update_defined_names(payload: bytes, *, pivot_index: int) -> bytes:
    pattern = re.compile(rb"<definedName\b[^>]*>.*?</definedName>", re.DOTALL)

    def replace(match: re.Match[bytes]) -> bytes:
        element = match.group(0)
        start_end = element.find(b">") + 1
        start = element[:start_end]
        local_id = _attr(start, "localSheetId")
        if local_id is None:
            return element
        try:
            sheet_index = int(local_id)
        except ValueError as exc:
            raise WorkbookSimplificationError("Workbook contains an invalid local defined-name scope.") from exc
        if sheet_index == pivot_index:
            return b""
        if sheet_index > pivot_index:
            return _replace_integer_attr(start, "localSheetId", sheet_index - 1) + element[start_end:]
        return element

    return pattern.sub(replace, payload)


def _update_active_tab(payload: bytes, *, pivot_index: int, remaining_count: int) -> bytes:
    pattern = re.compile(rb"<workbookView\b[^>]*/>")
    changed = False

    def replace(match: re.Match[bytes]) -> bytes:
        nonlocal changed
        tag = match.group(0)
        active_tab = _attr(tag, "activeTab")
        if active_tab is None:
            return tag
        try:
            active_index = int(active_tab)
        except ValueError as exc:
            raise WorkbookSimplificationError("Workbook contains an invalid active worksheet index.") from exc
        if active_index > pivot_index:
            new_index = active_index - 1
        elif active_index == pivot_index:
            new_index = min(max(0, pivot_index - 1), max(0, remaining_count - 1))
        else:
            return tag
        changed = True
        return _replace_integer_attr(tag, "activeTab", new_index)

    updated = pattern.sub(replace, payload)
    # No change is expected when another sheet is active.
    del changed
    return updated


def _remove_pivot_cache_declarations(payload: bytes, relationship_ids: Iterable[str]) -> bytes:
    ids = frozenset(relationship_ids)
    if not ids:
        return payload
    pattern = re.compile(rb"<pivotCache\b[^>]*/>")
    removed: set[str] = set()

    def replace(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        relationship_id = _attr(tag, "r:id")
        if relationship_id in ids:
            removed.add(str(relationship_id))
            return b""
        return tag

    updated = pattern.sub(replace, payload)
    if removed != set(ids):
        raise WorkbookSimplificationError("Could not match every obsolete Pivot cache declaration.")
    updated = re.sub(rb"<pivotCaches\b[^>]*>\s*</pivotCaches>", b"", updated, count=1)
    return updated


def _remove_relationships(payload: bytes, relationship_ids: Iterable[str]) -> bytes:
    ids = frozenset(relationship_ids)
    pattern = re.compile(rb"<Relationship\b[^>]*/>")
    removed: set[str] = set()

    def replace(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        relationship_id = _attr(tag, "Id")
        if relationship_id in ids:
            removed.add(str(relationship_id))
            return b""
        return tag

    updated = pattern.sub(replace, payload)
    if removed != set(ids):
        raise WorkbookSimplificationError("Could not match every obsolete workbook relationship.")
    return updated


def _remove_content_type_overrides(payload: bytes, deleted_parts: Iterable[str]) -> bytes:
    deleted = {"/" + part.lstrip("/") for part in deleted_parts}
    pattern = re.compile(rb"<Override\b[^>]*/>")
    removed: set[str] = set()

    def replace(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        part_name = _attr(tag, "PartName")
        if part_name in deleted:
            removed.add(str(part_name))
            return b""
        return tag

    updated = pattern.sub(replace, payload)
    # Relationship parts normally use the default .rels content type and do
    # not have overrides, so only require that every declared deleted part was
    # removed—not that every deleted part owned an override.
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise WorkbookSimplificationError("Workbook content types are not valid XML.") from exc
    expected = {
        node.attrib.get("PartName", "")
        for node in root.findall(f"{{{_CONTENT_TYPES_NS}}}Override")
        if node.attrib.get("PartName", "") in deleted
    }
    if removed != expected:
        raise WorkbookSimplificationError("Could not remove obsolete Pivot content-type declarations.")
    return updated


def _update_app_properties(payload: bytes, *, pivot_index: int, remaining_count: int) -> bytes:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise WorkbookSimplificationError("Workbook application properties are not valid XML.") from exc

    heading_vector = root.find(f"{{{_APP_NS}}}HeadingPairs/{{{_VT_NS}}}vector")
    titles_vector = root.find(f"{{{_APP_NS}}}TitlesOfParts/{{{_VT_NS}}}vector")
    if heading_vector is None or titles_vector is None:
        raise WorkbookSimplificationError("Workbook application properties do not list worksheet titles.")

    headings = list(heading_vector)
    if len(headings) % 2:
        raise WorkbookSimplificationError("Workbook application worksheet metadata is malformed.")
    worksheet_offset = 0
    worksheet_count_element: ET.Element | None = None
    for index in range(0, len(headings), 2):
        label = next(iter(headings[index]), None)
        count_element = next(iter(headings[index + 1]), None)
        if label is None or count_element is None:
            raise WorkbookSimplificationError("Workbook application worksheet metadata is incomplete.")
        try:
            count = int(count_element.text or "")
        except ValueError as exc:
            raise WorkbookSimplificationError("Workbook application worksheet count is invalid.") from exc
        if (label.text or "").casefold() == "worksheets":
            worksheet_count_element = count_element
            break
        worksheet_offset += count
    if worksheet_count_element is None:
        raise WorkbookSimplificationError("Workbook application properties omit the worksheet count.")

    titles = list(titles_vector)
    target_index = worksheet_offset + pivot_index
    if target_index >= len(titles) or (titles[target_index].text or "").casefold() != _PIVOT_SHEET_NAME.casefold():
        raise WorkbookSimplificationError("Workbook application properties do not align with the Pivot sheet.")
    titles_vector.remove(titles[target_index])
    titles_vector.set("size", str(len(titles) - 1))
    worksheet_count_element.text = str(remaining_count)

    ET.register_namespace("", _APP_NS)
    ET.register_namespace("vt", _VT_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _descendants(archive: ZipFile, start_part: str) -> frozenset[str]:
    names = set(archive.namelist())
    seen: set[str] = set()
    stack = [start_part]
    while stack:
        part = stack.pop()
        if part in seen or part not in names:
            continue
        seen.add(part)
        relationship_part = _relationship_part(part)
        if relationship_part in names:
            seen.add(relationship_part)
        for _, _, target in _relationships(archive, part):
            if target in names and target not in seen:
                stack.append(target)
    return frozenset(seen)


def _reachable_parts(archive: ZipFile, replacements: Mapping[str, bytes]) -> frozenset[str]:
    names = set(archive.namelist())
    reachable: set[str] = set()
    owners = [""]
    processed: set[str] = set()
    while owners:
        owner = owners.pop()
        if owner in processed:
            continue
        processed.add(owner)
        relationship_part = _relationship_part(owner)
        if relationship_part in names:
            reachable.add(relationship_part)
        for _, _, target in _relationships(archive, owner, replacements=replacements):
            if target not in names:
                raise WorkbookSimplificationError(
                    f"Workbook relationship points to missing package part '{target}'."
                )
            if target not in reachable:
                reachable.add(target)
                owners.append(target)
    return frozenset(reachable)


def _remaining_pivot_cache_ids(
    archive: ZipFile,
    *,
    worksheet_parts: Iterable[str],
) -> frozenset[str]:
    cache_ids: set[str] = set()
    for worksheet_part in worksheet_parts:
        for _, relationship_type, target in _relationships(archive, worksheet_part):
            if not relationship_type.endswith("/pivotTable"):
                continue
            try:
                root = ET.fromstring(archive.read(target))
            except (KeyError, ET.ParseError) as exc:
                raise WorkbookSimplificationError("A retained Pivot table definition is invalid.") from exc
            cache_id = root.attrib.get("cacheId")
            if cache_id is None:
                raise WorkbookSimplificationError("A retained Pivot table omits its cache identifier.")
            cache_ids.add(cache_id)
    return frozenset(cache_ids)


def _assert_no_retained_reference(
    archive: ZipFile,
    *,
    pivot_part: str,
    candidate_parts: frozenset[str],
    workbook_root: ET.Element,
    pivot_index: int,
) -> None:
    for defined_name in workbook_root.findall(f".//{{{_MAIN_NS}}}definedName"):
        local_id = defined_name.attrib.get("localSheetId")
        if local_id is not None:
            try:
                if int(local_id) == pivot_index:
                    continue
            except ValueError as exc:
                raise WorkbookSimplificationError("Workbook contains an invalid local defined-name scope.") from exc
        if _SHEET_REFERENCE.search(defined_name.text or ""):
            raise WorkbookSimplificationError(
                "A retained workbook defined name still depends on the Pivot sheet."
            )

    for part in archive.namelist():
        if not part.endswith(".xml") or part in candidate_parts or part == pivot_part:
            continue
        try:
            root = ET.fromstring(archive.read(part))
        except ET.ParseError as exc:
            raise WorkbookSimplificationError(f"Workbook XML part '{part}' is invalid.") from exc
        for element in root.iter():
            if any(_SHEET_REFERENCE.search(value) for value in element.attrib.values()):
                raise WorkbookSimplificationError(
                    f"Retained workbook reference in '{part}' still depends on the Pivot sheet."
                )
            local = _local_name(element.tag).casefold()
            formula_element = (
                local in {"f", "formula", "formula1", "formula2"}
                or local.endswith("formula")
            )
            if formula_element and _SHEET_REFERENCE.search(element.text or ""):
                raise WorkbookSimplificationError(
                    f"Retained workbook formula in '{part}' still depends on the Pivot sheet."
                )


def _prepare_mutation(archive: ZipFile) -> _Mutation:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise WorkbookSimplificationError("Workbook contains duplicate OOXML package part names.")
    required = {_WORKBOOK_PART, _WORKBOOK_RELS_PART, _CONTENT_TYPES_PART}
    missing = required - set(names)
    if missing:
        raise WorkbookSimplificationError(
            "Workbook is missing required package part(s): " + ", ".join(sorted(missing))
        )
    try:
        workbook_root = ET.fromstring(archive.read(_WORKBOOK_PART))
    except ET.ParseError as exc:
        raise WorkbookSimplificationError("Workbook definition is not valid XML.") from exc

    sheets = workbook_root.findall(f".//{{{_MAIN_NS}}}sheet")
    sheet_names = tuple(sheet.attrib.get("name", "") for sheet in sheets)
    pivots = [
        (index, sheet)
        for index, sheet in enumerate(sheets)
        if sheet.attrib.get("name", "").casefold() == _PIVOT_SHEET_NAME.casefold()
    ]
    if not pivots:
        return _Mutation({}, frozenset(), sheet_names, True)
    if len(pivots) != 1:
        raise WorkbookSimplificationError("Workbook must contain at most one Pivot worksheet.")
    pivot_index, pivot_sheet = pivots[0]
    pivot_relationship_id = pivot_sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
    if not pivot_relationship_id:
        raise WorkbookSimplificationError("Pivot worksheet is missing its workbook relationship.")

    workbook_relationships = {
        relationship_id: (relationship_type, target)
        for relationship_id, relationship_type, target in _relationships(archive, _WORKBOOK_PART)
    }
    relationship = workbook_relationships.get(pivot_relationship_id)
    if relationship is None or not relationship[0].endswith("/worksheet"):
        raise WorkbookSimplificationError("Pivot worksheet relationship is missing or has the wrong type.")
    pivot_part = relationship[1]
    if pivot_part not in names:
        raise WorkbookSimplificationError("Pivot worksheet XML part is missing.")

    candidate_parts = _descendants(archive, pivot_part)
    _assert_no_retained_reference(
        archive,
        pivot_part=pivot_part,
        candidate_parts=candidate_parts,
        workbook_root=workbook_root,
        pivot_index=pivot_index,
    )

    retained_sheet_nodes = [sheet for index, sheet in enumerate(sheets) if index != pivot_index]
    retained_sheet_parts: list[str] = []
    for sheet in retained_sheet_nodes:
        relationship_id = sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
        retained_relationship = workbook_relationships.get(relationship_id)
        if retained_relationship is None or not retained_relationship[0].endswith("/worksheet"):
            raise WorkbookSimplificationError("A retained worksheet relationship is invalid.")
        retained_sheet_parts.append(retained_relationship[1])
    used_cache_ids = _remaining_pivot_cache_ids(
        archive,
        worksheet_parts=retained_sheet_parts,
    )

    cache_relationship_ids: list[str] = []
    for pivot_cache in workbook_root.findall(f".//{{{_MAIN_NS}}}pivotCache"):
        cache_id = pivot_cache.attrib.get("cacheId", "")
        relationship_id = pivot_cache.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
        cache_relationship = workbook_relationships.get(relationship_id)
        if (
            cache_id not in used_cache_ids
            and cache_relationship is not None
            and cache_relationship[1] in candidate_parts
        ):
            cache_relationship_ids.append(relationship_id)

    workbook_payload = archive.read(_WORKBOOK_PART)
    workbook_payload = _remove_workbook_sheet(
        workbook_payload,
        relationship_id=pivot_relationship_id,
    )
    workbook_payload = _update_defined_names(workbook_payload, pivot_index=pivot_index)
    workbook_payload = _update_active_tab(
        workbook_payload,
        pivot_index=pivot_index,
        remaining_count=len(retained_sheet_nodes),
    )
    workbook_payload = _remove_pivot_cache_declarations(
        workbook_payload,
        cache_relationship_ids,
    )
    workbook_rels_payload = _remove_relationships(
        archive.read(_WORKBOOK_RELS_PART),
        (pivot_relationship_id, *cache_relationship_ids),
    )
    preliminary_replacements = {
        _WORKBOOK_PART: workbook_payload,
        _WORKBOOK_RELS_PART: workbook_rels_payload,
    }

    reachable = _reachable_parts(archive, preliminary_replacements)
    deletions = frozenset(part for part in candidate_parts if part not in reachable)
    if pivot_part not in deletions:
        raise WorkbookSimplificationError("Pivot worksheet remained reachable after staging.")

    replacements: dict[str, bytes] = dict(preliminary_replacements)
    replacements[_CONTENT_TYPES_PART] = _remove_content_type_overrides(
        archive.read(_CONTENT_TYPES_PART),
        deletions,
    )
    if _APP_PROPERTIES_PART in names:
        replacements[_APP_PROPERTIES_PART] = _update_app_properties(
            archive.read(_APP_PROPERTIES_PART),
            pivot_index=pivot_index,
            remaining_count=len(retained_sheet_nodes),
        )
    replacements = {
        name: payload
        for name, payload in replacements.items()
        if payload != archive.read(name)
    }
    return _Mutation(
        replacements=replacements,
        deletions=deletions,
        retained_sheets=tuple(sheet.attrib.get("name", "") for sheet in retained_sheet_nodes),
        already_simplified=False,
    )


def _write_candidate(
    source: Path,
    destination: Path,
    mutation: _Mutation,
) -> None:
    try:
        with ZipFile(source, "r") as original, ZipFile(
            destination,
            "w",
            compression=ZIP_DEFLATED,
            allowZip64=True,
        ) as updated:
            for info in original.infolist():
                if info.filename in mutation.deletions:
                    continue
                updated.writestr(
                    info,
                    mutation.replacements.get(info.filename, original.read(info.filename)),
                )
    except BadZipFile as exc:
        raise WorkbookSimplificationError("The Excel workbook is not a valid OOXML archive.") from exc


def _verify_relationship_integrity(path: Path) -> None:
    try:
        with ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            for relationship_part in (
                name for name in names if name.endswith(".rels")
            ):
                if relationship_part == "_rels/.rels":
                    owner = ""
                else:
                    path_obj = PurePosixPath(relationship_part)
                    if path_obj.parent.name != "_rels" or not path_obj.name.endswith(".rels"):
                        raise WorkbookSimplificationError(
                            f"Workbook relationship part '{relationship_part}' has an invalid path."
                        )
                    owner = str(
                        path_obj.parent.parent / path_obj.name[: -len(".rels")]
                    )
                for _, _, target in _relationships(archive, owner):
                    if target not in names:
                        raise WorkbookSimplificationError(
                            f"Workbook relationship points to missing package part '{target}'."
                        )
    except BadZipFile as exc:
        raise WorkbookSimplificationError("The staged workbook is not a valid OOXML archive.") from exc


def _verify_candidate(source: Path, candidate: Path, mutation: _Mutation) -> None:
    try:
        with ZipFile(source, "r") as original, ZipFile(candidate, "r") as updated:
            expected_names = [
                name for name in original.namelist() if name not in mutation.deletions
            ]
            if updated.namelist() != expected_names:
                raise WorkbookSimplificationError(
                    "Workbook package parts changed unexpectedly during simplification."
                )
            for name in expected_names:
                expected = mutation.replacements.get(name, original.read(name))
                if updated.read(name) != expected:
                    raise WorkbookSimplificationError(
                        f"Workbook part '{name}' changed unexpectedly during simplification."
                    )
            for name in mutation.deletions:
                if name in updated.namelist():
                    raise WorkbookSimplificationError(
                        f"Obsolete Pivot part '{name}' was not removed."
                    )

            original_paths = race_workbook._sheet_paths(original)
            updated_paths = race_workbook._sheet_paths(updated)
            if tuple(updated_paths) != mutation.retained_sheets:
                raise WorkbookSimplificationError("Staged workbook worksheet order is incorrect.")
            for sheet_name in mutation.retained_sheets:
                original_part = original_paths[sheet_name]
                updated_part = updated_paths[sheet_name]
                if original_part != updated_part or original.read(original_part) != updated.read(updated_part):
                    raise WorkbookSimplificationError(
                        f"Retained worksheet '{sheet_name}' was altered during simplification."
                    )
    except BadZipFile as exc:
        raise WorkbookSimplificationError("The staged workbook is not a valid OOXML archive.") from exc

    _verify_relationship_integrity(candidate)
    core.validate_workbook(candidate)


def _stage_to_temporary(source: Path, temporary: Path) -> _Mutation:
    try:
        with ZipFile(source, "r") as archive:
            mutation = _prepare_mutation(archive)
    except BadZipFile as exc:
        raise WorkbookSimplificationError("The Excel workbook is not a valid OOXML archive.") from exc
    if mutation.already_simplified:
        shutil.copy2(source, temporary)
    else:
        _write_candidate(source, temporary, mutation)
    _verify_candidate(source, temporary, mutation)
    return mutation


def stage_simplified_workbook(
    workbook_path: str | Path,
    output_path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> WorkbookSimplificationResult:
    """Create and verify a simplified copy without modifying the source.

    ``output_path`` must not already exist.  This makes review/staging
    recoverable and prevents accidental overwrites of user files.
    """
    source = Path(workbook_path).resolve()
    output = Path(output_path).resolve()
    if not source.is_file():
        raise WorkbookSimplificationError(f"Workbook was not found: {source}")
    if source == output:
        raise WorkbookSimplificationError("The staged output must be separate from the source workbook.")
    if output.exists():
        raise WorkbookSimplificationError("The staged output already exists and was not overwritten.")
    source_sha = race_workbook.workbook_fingerprint(source)
    if expected_sha256 is not None and source_sha != expected_sha256:
        raise race_workbook.StaleWorkbookError(
            "The workbook changed after the simplification was reviewed."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.simplify-",
        suffix=".xlsx",
        dir=output.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        mutation = _stage_to_temporary(source, temporary)
        if race_workbook.workbook_fingerprint(source) != source_sha:
            raise race_workbook.StaleWorkbookError(
                "The workbook changed while the simplified copy was staged."
            )
        os.replace(temporary, output)
        return WorkbookSimplificationResult(
            workbook_path=output,
            source_sha256=source_sha,
            workbook_sha256=race_workbook.workbook_fingerprint(output),
            already_simplified=mutation.already_simplified,
            removed_parts=tuple(sorted(mutation.deletions)),
            changed_parts=tuple(sorted(mutation.replacements)),
            retained_sheets=mutation.retained_sheets,
        )
    finally:
        if temporary.exists():
            temporary.unlink()


def commit_workbook_simplification(
    workbook_path: str | Path,
    *,
    expected_sha256: str,
    approved: bool,
    backup_directory: str | Path | None = None,
) -> WorkbookSimplificationResult:
    """Back up and atomically replace a workbook after explicit approval."""
    if not approved:
        raise race_workbook.ApprovalRequiredError(
            "Workbook simplification requires explicit approval."
        )
    path = Path(workbook_path).resolve()
    if not path.is_file():
        raise WorkbookSimplificationError(f"Workbook was not found: {path}")

    with race_workbook._workbook_lock(path):
        source_sha = race_workbook.workbook_fingerprint(path)
        if source_sha != expected_sha256:
            raise race_workbook.StaleWorkbookError(
                "The workbook changed after the simplification was reviewed."
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}.simplify-",
            suffix=".xlsx",
            dir=path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            mutation = _stage_to_temporary(path, temporary)
            if mutation.already_simplified:
                return WorkbookSimplificationResult(
                    workbook_path=path,
                    source_sha256=source_sha,
                    workbook_sha256=source_sha,
                    already_simplified=True,
                    removed_parts=(),
                    changed_parts=(),
                    retained_sheets=mutation.retained_sheets,
                )
            if race_workbook.workbook_fingerprint(path) != source_sha:
                raise race_workbook.StaleWorkbookError(
                    "The workbook changed while simplification was staged."
                )
            backup_root = (
                Path(backup_directory).resolve()
                if backup_directory is not None
                else path.parent / ".codex-tmp" / "workbook-simplification-backups"
            )
            backup_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = backup_root / f"{path.stem}.before-simplify-{timestamp}-{source_sha[:8]}.xlsx"
            if backup.exists():
                backup = backup_root / (
                    f"{path.stem}.before-simplify-{timestamp}-{source_sha[:8]}-{uuid4().hex[:6]}.xlsx"
                )
            shutil.copy2(path, backup)
            if race_workbook.workbook_fingerprint(backup) != source_sha:
                raise race_workbook.StaleWorkbookError(
                    "The recovery copy did not match the reviewed workbook."
                )
            shutil.copystat(path, temporary)
            if race_workbook.workbook_fingerprint(path) != source_sha:
                raise race_workbook.StaleWorkbookError(
                    "The workbook changed after its recovery copy was verified."
                )
            try:
                os.replace(temporary, path)
            except PermissionError as exc:
                raise WorkbookSimplificationError(
                    "Excel appears to have the workbook open. Close it and try again."
                ) from exc
            return WorkbookSimplificationResult(
                workbook_path=path,
                source_sha256=source_sha,
                workbook_sha256=race_workbook.workbook_fingerprint(path),
                already_simplified=False,
                removed_parts=tuple(sorted(mutation.deletions)),
                changed_parts=tuple(sorted(mutation.replacements)),
                retained_sheets=mutation.retained_sheets,
                backup_path=backup,
            )
        finally:
            if temporary.exists():
                temporary.unlink()


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a verified Pivot-free copy of F1_Standings.xlsx."
    )
    parser.add_argument("source", help="Source .xlsx workbook (never modified)")
    parser.add_argument("output", help="New .xlsx output path (must not already exist)")
    parser.add_argument(
        "--expected-sha256",
        help="Optional reviewed SHA-256 guard for the source workbook",
    )
    arguments = parser.parse_args()
    result = stage_simplified_workbook(
        arguments.source,
        arguments.output,
        expected_sha256=arguments.expected_sha256,
    )
    print(
        json.dumps(
            {
                "output": str(result.workbook_path),
                "source_sha256": result.source_sha256,
                "workbook_sha256": result.workbook_sha256,
                "already_simplified": result.already_simplified,
                "retained_sheets": list(result.retained_sheets),
                "removed_parts": list(result.removed_parts),
                "changed_parts": list(result.changed_parts),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
