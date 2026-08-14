from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pandas as pd

import dashboard_core as core
import race_correction
import race_import
import race_workbook
import workbook_simplify as subject


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

EXPECTED_REMOVED_PARTS = {
    "xl/worksheets/pivot-legacy.xml",
    "xl/worksheets/_rels/pivot-legacy.xml.rels",
    "xl/pivotTables/pivotTable-legacy.xml",
    "xl/pivotTables/_rels/pivotTable-legacy.xml.rels",
    "xl/pivotCache/pivotCacheDefinition-legacy.xml",
    "xl/pivotCache/_rels/pivotCacheDefinition-legacy.xml.rels",
    "xl/pivotCache/pivotCacheRecords-legacy.xml",
}
EXPECTED_CHANGED_PARTS = {
    "[Content_Types].xml",
    "docProps/app.xml",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
}

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

LEGACY_ADDITIONS = {
    "xl/worksheets/pivot-legacy.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN_NS}" xmlns:r="{OFFICE_REL_NS}">'
        '<dimension ref="A1:B2"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Legacy cached report</t></is></c></row>'
        '</sheetData><pivotTableParts count="1"><pivotTablePart r:id="rId1"/>'
        '</pivotTableParts></worksheet>'
    ).encode("utf-8"),
    "xl/worksheets/_rels/pivot-legacy.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" '
        f'Type="{OFFICE_REL_NS}/pivotTable" '
        'Target="../pivotTables/pivotTable-legacy.xml"/>'
        '</Relationships>'
    ).encode("utf-8"),
    "xl/pivotTables/pivotTable-legacy.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<pivotTableDefinition xmlns="{MAIN_NS}" name="LegacyPivot" cacheId="0" '
        'dataCaption="Values"><location ref="A1:B2" firstHeaderRow="1" '
        'firstDataRow="1" firstDataCol="1"/><pivotFields count="0"/>'
        '<rowFields count="0"/><rowItems count="0"/><colFields count="0"/>'
        '<colItems count="0"/><dataFields count="0"/></pivotTableDefinition>'
    ).encode("utf-8"),
    "xl/pivotTables/_rels/pivotTable-legacy.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" '
        f'Type="{OFFICE_REL_NS}/pivotCacheDefinition" '
        'Target="../pivotCache/pivotCacheDefinition-legacy.xml"/>'
        '</Relationships>'
    ).encode("utf-8"),
    "xl/pivotCache/pivotCacheDefinition-legacy.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<pivotCacheDefinition xmlns="{MAIN_NS}" xmlns:r="{OFFICE_REL_NS}" '
        'r:id="rId1" recordCount="0"><cacheSource type="worksheet">'
        '<worksheetSource ref="A1:J1" sheet="Leagues"/></cacheSource>'
        '<cacheFields count="0"/></pivotCacheDefinition>'
    ).encode("utf-8"),
    "xl/pivotCache/_rels/pivotCacheDefinition-legacy.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" '
        f'Type="{OFFICE_REL_NS}/pivotCacheRecords" '
        'Target="pivotCacheRecords-legacy.xml"/>'
        '</Relationships>'
    ).encode("utf-8"),
    "xl/pivotCache/pivotCacheRecords-legacy.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<pivotCacheRecords xmlns="{MAIN_NS}" count="0"/>'
    ).encode("utf-8"),
}


def archive_payloads(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist()}


def build_legacy_pivot_fixture(path: Path) -> Path:
    """Add a deterministic, isolated Pivot graph to the tracked simplified file."""
    with ZipFile(SOURCE_WORKBOOK, "r") as source:
        workbook = source.read("xl/workbook.xml")
        game_purchase = re.search(
            rb'<sheet\b(?=[^>]*\bname="Game Purchase")[^>]*/>',
            workbook,
        )
        if game_purchase is None:
            raise AssertionError("Tracked workbook must contain Game Purchase")
        workbook = (
            workbook[: game_purchase.start()]
            + b'<sheet name="Pivot" sheetId="99" r:id="rId50"/>'
            + workbook[game_purchase.start() :]
        )
        pivot_caches = b'<pivotCaches><pivotCache cacheId="0" r:id="rId51"/></pivotCaches>'
        marker = b"<extLst>"
        if marker in workbook:
            workbook = workbook.replace(marker, pivot_caches + marker, 1)
        else:
            workbook = workbook.replace(b"</workbook>", pivot_caches + b"</workbook>", 1)

        workbook_rels = source.read("xl/_rels/workbook.xml.rels").replace(
            b"</Relationships>",
            (
                b'<Relationship Id="rId50" '
                + f'Type="{OFFICE_REL_NS}/worksheet" '.encode("ascii")
                + b'Target="worksheets/pivot-legacy.xml"/>'
                + b'<Relationship Id="rId51" '
                + f'Type="{OFFICE_REL_NS}/pivotCacheDefinition" '.encode("ascii")
                + b'Target="pivotCache/pivotCacheDefinition-legacy.xml"/>'
                + b"</Relationships>"
            ),
            1,
        )

        content_types = source.read("[Content_Types].xml").replace(
            b"</Types>",
            (
                b'<Override PartName="/xl/worksheets/pivot-legacy.xml" '
                b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                b'<Override PartName="/xl/pivotTables/pivotTable-legacy.xml" '
                b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml"/>'
                b'<Override PartName="/xl/pivotCache/pivotCacheDefinition-legacy.xml" '
                b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml"/>'
                b'<Override PartName="/xl/pivotCache/pivotCacheRecords-legacy.xml" '
                b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheRecords+xml"/>'
                b"</Types>"
            ),
            1,
        )

        app_root = ET.fromstring(source.read("docProps/app.xml"))
        heading_count = app_root.find(
            f"{{{APP_NS}}}HeadingPairs/{{{VT_NS}}}vector/{{{VT_NS}}}variant[2]/{{{VT_NS}}}i4"
        )
        titles = app_root.find(f"{{{APP_NS}}}TitlesOfParts/{{{VT_NS}}}vector")
        if heading_count is None or titles is None:
            raise AssertionError("Tracked workbook application metadata is incomplete")
        heading_count.text = "4"
        pivot_title = ET.Element(f"{{{VT_NS}}}lpstr")
        pivot_title.text = "Pivot"
        titles.insert(2, pivot_title)
        titles.set("size", "4")
        ET.register_namespace("", APP_NS)
        ET.register_namespace("vt", VT_NS)
        app_properties = ET.tostring(app_root, encoding="utf-8", xml_declaration=True)

        replacements = {
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": workbook_rels,
            "[Content_Types].xml": content_types,
            "docProps/app.xml": app_properties,
        }
        with ZipFile(path, "w", compression=ZIP_DEFLATED, allowZip64=True) as target:
            for info in source.infolist():
                target.writestr(info, replacements.get(info.filename, source.read(info.filename)))
            for name, payload in LEGACY_ADDITIONS.items():
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                target.writestr(info, payload)
    return path


def formula_snapshot(path: Path) -> tuple[tuple[str, bytes], ...]:
    formulas: list[tuple[str, bytes]] = []
    with ZipFile(path) as archive:
        sheet_paths = race_workbook._sheet_paths(archive)
        for sheet_name, part in sheet_paths.items():
            if sheet_name == "Pivot":
                continue
            root = ET.fromstring(archive.read(part))
            for formula in root.iter():
                if formula.tag.rsplit("}", 1)[-1] == "f":
                    formulas.append((sheet_name, ET.tostring(formula, encoding="utf-8")))
    return tuple(formulas)


def rewrite_part(path: Path, part_name: str, transform) -> None:
    temporary = path.with_suffix(".rewrite.xlsx")
    with ZipFile(path, "r") as source, ZipFile(
        temporary, "w", compression=ZIP_DEFLATED, allowZip64=True
    ) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            target.writestr(info, transform(payload) if info.filename == part_name else payload)
    temporary.replace(path)


class WorkbookSimplificationTests(unittest.TestCase):
    def test_tracked_workbook_is_already_simplified_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            output = Path(raw) / "tracked-copy.xlsx"
            source_sha = race_workbook.workbook_fingerprint(SOURCE_WORKBOOK)
            before = archive_payloads(SOURCE_WORKBOOK)

            result = subject.stage_simplified_workbook(
                SOURCE_WORKBOOK,
                output,
                expected_sha256=source_sha,
            )

            self.assertEqual(race_workbook.workbook_fingerprint(SOURCE_WORKBOOK), source_sha)
            self.assertTrue(result.already_simplified)
            self.assertEqual(result.removed_parts, ())
            self.assertEqual(result.changed_parts, ())
            self.assertEqual(result.retained_sheets, ("Leagues", "Calendar", "Game Purchase"))
            self.assertEqual(output.read_bytes(), SOURCE_WORKBOOK.read_bytes())
            self.assertEqual(archive_payloads(output), before)
            self.assertFalse(any("pivot" in name.casefold() for name in before))
            with ZipFile(output) as archive:
                self.assertNotIn("Pivot", race_workbook._sheet_paths(archive))

    def test_staged_copy_removes_only_pivot_graph_and_preserves_all_retained_sheets(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            legacy = build_legacy_pivot_fixture(root / "legacy.xlsx")
            output = root / "F1_Standings.simplified.xlsx"
            source_sha = race_workbook.workbook_fingerprint(legacy)
            before = archive_payloads(legacy)
            before_standings = core.load_standings_data(SOURCE_WORKBOOK)
            before_formulas = formula_snapshot(legacy)

            result = subject.stage_simplified_workbook(
                legacy,
                output,
                expected_sha256=source_sha,
            )

            self.assertEqual(race_workbook.workbook_fingerprint(legacy), source_sha)
            self.assertFalse(result.already_simplified)
            self.assertEqual(set(result.removed_parts), EXPECTED_REMOVED_PARTS)
            self.assertEqual(set(result.changed_parts), EXPECTED_CHANGED_PARTS)
            self.assertEqual(
                result.retained_sheets,
                ("Leagues", "Calendar", "Game Purchase"),
            )
            after = archive_payloads(output)
            self.assertEqual(set(before) - set(after), EXPECTED_REMOVED_PARTS)
            self.assertEqual(
                {
                    name
                    for name in set(before) & set(after)
                    if before[name] != after[name]
                },
                EXPECTED_CHANGED_PARTS,
            )
            for part_name in (
                "xl/worksheets/sheet1.xml",
                "xl/worksheets/sheet2.xml",
                "xl/worksheets/sheet4.xml",
                "xl/calcChain.xml",
                "xl/sharedStrings.xml",
                "xl/styles.xml",
            ):
                self.assertEqual(after[part_name], before[part_name], part_name)
            self.assertNotIn(b"Pivot", after["docProps/app.xml"])
            self.assertNotIn(b"pivotCache", after["xl/workbook.xml"])
            self.assertEqual(formula_snapshot(output), before_formulas)
            pd.testing.assert_frame_equal(
                core.load_standings_data(output),
                before_standings,
                check_dtype=False,
            )
            for sheet_name in ("Calendar", "Game Purchase"):
                pd.testing.assert_frame_equal(
                    pd.read_excel(output, sheet_name=sheet_name),
                    pd.read_excel(SOURCE_WORKBOOK, sheet_name=sheet_name),
                    check_dtype=False,
                )

    def test_migration_is_deterministic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            first = root / "first.xlsx"
            second = root / "second.xlsx"
            third = root / "third.xlsx"
            legacy = build_legacy_pivot_fixture(root / "legacy.xlsx")

            first_result = subject.stage_simplified_workbook(legacy, first)
            second_result = subject.stage_simplified_workbook(legacy, second)
            third_result = subject.stage_simplified_workbook(first, third)

            self.assertEqual(first_result.workbook_sha256, second_result.workbook_sha256)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertTrue(third_result.already_simplified)
            self.assertEqual(third_result.removed_parts, ())
            self.assertEqual(first.read_bytes(), third.read_bytes())

    def test_refuses_to_remove_pivot_when_a_retained_formula_depends_on_it(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            source = root / "dependent.xlsx"
            output = root / "should-not-exist.xlsx"
            build_legacy_pivot_fixture(source)
            with ZipFile(source) as archive:
                leagues_part = race_workbook._sheet_paths(archive)["Leagues"]

            def add_dependency(payload: bytes) -> bytes:
                marker = b"</worksheet>"
                self.assertIn(marker, payload)
                return payload.replace(
                    marker,
                    b"<extLst><ext><f>Pivot!A1</f></ext></extLst>" + marker,
                    1,
                )

            rewrite_part(source, leagues_part, add_dependency)
            reviewed_sha = race_workbook.workbook_fingerprint(source)

            with self.assertRaisesRegex(
                subject.WorkbookSimplificationError,
                "still depends on the Pivot sheet",
            ):
                subject.stage_simplified_workbook(source, output)
            self.assertFalse(output.exists())
            self.assertEqual(race_workbook.workbook_fingerprint(source), reviewed_sha)

    def test_refuses_pivot_reference_in_retained_data_validation_formula(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            source = root / "validation-dependent.xlsx"
            output = root / "should-not-exist.xlsx"
            build_legacy_pivot_fixture(source)
            with ZipFile(source) as archive:
                leagues_part = race_workbook._sheet_paths(archive)["Leagues"]

            def add_dependency(payload: bytes) -> bytes:
                marker = b"</worksheet>"
                return payload.replace(
                    marker,
                    (
                        b'<dataValidations count="1"><dataValidation type="list" sqref="Z1">'
                        b"<formula1>'Pivot'!$A$1:$A$2</formula1>"
                        b"</dataValidation></dataValidations>" + marker
                    ),
                    1,
                )

            rewrite_part(source, leagues_part, add_dependency)
            with self.assertRaisesRegex(
                subject.WorkbookSimplificationError,
                "still depends on the Pivot sheet",
            ):
                subject.stage_simplified_workbook(source, output)
            self.assertFalse(output.exists())

    def test_refuses_internal_hyperlink_to_pivot_sheet(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            source = root / "hyperlink-dependent.xlsx"
            output = root / "should-not-exist.xlsx"
            build_legacy_pivot_fixture(source)
            with ZipFile(source) as archive:
                leagues_part = race_workbook._sheet_paths(archive)["Leagues"]

            def add_dependency(payload: bytes) -> bytes:
                marker = b"</worksheet>"
                return payload.replace(
                    marker,
                    b'<hyperlinks><hyperlink ref="Z1" location="&apos;Pivot&apos;!A1"/></hyperlinks>'
                    + marker,
                    1,
                )

            rewrite_part(source, leagues_part, add_dependency)
            with self.assertRaisesRegex(
                subject.WorkbookSimplificationError,
                "still depends on the Pivot sheet",
            ):
                subject.stage_simplified_workbook(source, output)
            self.assertFalse(output.exists())

    def test_commit_requires_approval_stale_guard_and_creates_exact_recovery_copy(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = root / SOURCE_WORKBOOK.name
            build_legacy_pivot_fixture(target)
            original = target.read_bytes()
            reviewed_sha = race_workbook.workbook_fingerprint(target)

            with self.assertRaises(race_workbook.ApprovalRequiredError):
                subject.commit_workbook_simplification(
                    target,
                    expected_sha256=reviewed_sha,
                    approved=False,
                )
            with self.assertRaises(race_workbook.StaleWorkbookError):
                subject.commit_workbook_simplification(
                    target,
                    expected_sha256="0" * 64,
                    approved=True,
                )
            self.assertEqual(target.read_bytes(), original)

            result = subject.commit_workbook_simplification(
                target,
                expected_sha256=reviewed_sha,
                approved=True,
                backup_directory=root / "backups",
            )

            self.assertFalse(result.already_simplified)
            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertEqual(result.backup_path.read_bytes(), original)
            self.assertEqual(result.workbook_sha256, race_workbook.workbook_fingerprint(target))
            second = subject.commit_workbook_simplification(
                target,
                expected_sha256=result.workbook_sha256,
                approved=True,
                backup_directory=root / "backups",
            )
            self.assertTrue(second.already_simplified)
            self.assertIsNone(second.backup_path)
            self.assertEqual(second.workbook_sha256, result.workbook_sha256)

    def test_staging_never_overwrites_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            output = Path(raw) / "existing.xlsx"
            output.write_bytes(b"keep me")
            with self.assertRaisesRegex(
                subject.WorkbookSimplificationError,
                "already exists",
            ):
                subject.stage_simplified_workbook(SOURCE_WORKBOOK, output)
            self.assertEqual(output.read_bytes(), b"keep me")

    def test_event_correction_accepts_simplified_workbook(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = root / "F1_Standings.simplified.xlsx"
            subject.stage_simplified_workbook(SOURCE_WORKBOOK, target)
            metadata = race_workbook.RaceMetadata(
                game="F1 25: 2026 Season pack",
                season="2026-T02",
                league="Teikirise",
                round_number=3,
                event_type="R",
                gp_name="Belgian GP",
            )
            standings = core.load_standings_data(target)
            roster = race_import.derive_championship_roster(
                standings,
                game=metadata.game,
                season=metadata.season,
                league=metadata.league,
            )
            scoring = race_import.infer_scoring_profile(
                standings,
                game=metadata.game,
                season=metadata.season,
                league=metadata.league,
                event_type="R",
                grid_size=len(roster),
            )
            rows = [
                {
                    "Position": position,
                    "Driver": entry.driver,
                    "Team": entry.team,
                    "Points": scoring[position],
                    "Time": "90:00.000" if position == 1 else f"+{position}.000",
                    "Fastest Lap": f"1:{20 + position:02d}.000",
                }
                for position, entry in enumerate(reversed(roster), start=1)
            ]
            snapshot = race_correction.load_event_snapshot(target, metadata)

            result = race_correction.commit_event_correction(
                target,
                metadata=metadata,
                action="replace",
                rows=rows,
                authoritative_roster=roster,
                authoritative_scoring=scoring,
                expected_event_digest=snapshot.digest,
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )

            self.assertEqual(result.rows_replaced, len(roster))
            with ZipFile(target) as archive:
                self.assertNotIn("Pivot", race_workbook._sheet_paths(archive))

    def test_stage_only_cli_reports_hashes_and_keeps_non_overwrite_guard(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            legacy = build_legacy_pivot_fixture(root / "legacy.xlsx")
            output = root / "cli-output.xlsx"
            stdout = io.StringIO()
            with mock.patch(
                "sys.argv",
                ["workbook_simplify", str(legacy), str(output)],
            ), redirect_stdout(stdout):
                self.assertEqual(subject._main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["output"], str(output.resolve()))
            self.assertEqual(report["retained_sheets"], ["Leagues", "Calendar", "Game Purchase"])
            self.assertEqual(report["workbook_sha256"], race_workbook.workbook_fingerprint(output))

            with mock.patch(
                "sys.argv",
                ["workbook_simplify", str(legacy), str(output)],
            ), self.assertRaisesRegex(
                subject.WorkbookSimplificationError,
                "already exists",
            ):
                subject._main()


if __name__ == "__main__":
    unittest.main()
