from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd

import dashboard_core as core
import race_import as race
import race_workbook as workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"


def extracted(
    position: int | None,
    driver: str | None,
    source: str,
    *,
    confidence: float = 0.9,
    raw_text: str | None = None,
    suggestion: str | None = None,
    issues: list[str] | None = None,
) -> race.ExtractedResult:
    return race.ExtractedResult(
        position=position,
        raw_text=raw_text or f"{position} {driver or suggestion or 'unknown'}",
        driver=driver,
        suggested_driver=suggestion,
        confidence=confidence,
        sources=[source],
        match_method="exact" if driver else "unresolved",
        issues=list(issues or []),
    )


def scoring_history() -> pd.DataFrame:
    rows: list[list[object]] = []
    scales = {
        "R": {1: 25, 2: 18, 3: 15},
        "SR": {1: 8, 2: 7, 3: 6},
    }
    for event_type, points_by_position in scales.items():
        for round_number in (1, 2):
            for position, points in points_by_position.items():
                rows.append(
                    [
                        "F1 25",
                        "2026-T01",
                        "League",
                        round_number,
                        event_type,
                        f"Round {round_number}",
                        f"Driver {position}",
                        f"Team {position}",
                        position,
                        points,
                        "2026-T01",
                        False,
                    ]
                )
    return pd.DataFrame(
        rows,
        columns=[
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
            "SeasonLabel",
            "IsSeasonFinal",
        ],
    )


def worksheet_parts(path: Path) -> dict[str, str]:
    """Resolve worksheet names independently from the production helper."""
    spreadsheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(path) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        relationship_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    targets = {
        item.attrib["Id"]: item.attrib["Target"].replace("\\", "/")
        for item in relationship_xml.findall(f"{{{package_rel_ns}}}Relationship")
    }
    result: dict[str, str] = {}
    for sheet in workbook_xml.findall(f".//{{{spreadsheet_ns}}}sheet"):
        target = targets[sheet.attrib[f"{{{office_rel_ns}}}id"]]
        if target.startswith("/"):
            part = target.lstrip("/")
        elif target.startswith("xl/"):
            part = target
        else:
            part = posixpath.normpath(posixpath.join("xl", target))
        result[sheet.attrib["name"]] = part
    return result


def archive_payloads(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {item.filename: archive.read(item.filename) for item in archive.infolist()}


def column_cell_snapshots(worksheet_xml: bytes, columns: set[str]) -> dict[str, bytes]:
    """Capture full cell XML so values, formulas, types, and styles are checked."""
    root = ET.fromstring(worksheet_xml)
    namespace = root.tag[1:].partition("}")[0]
    snapshots: dict[str, bytes] = {}
    for cell in root.iter(f"{{{namespace}}}c"):
        reference = cell.attrib.get("r", "")
        match = re.match(r"([A-Z]+)", reference)
        if match and match.group(1) in columns:
            snapshots[reference] = ET.tostring(cell, encoding="utf-8")
    return snapshots


class ControlledDriverMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = [
            race.DriverEntry("TomasRodri21", "McLaren"),
            race.DriverEntry("Polingua", "Red Bull"),
            race.DriverEntry("Fatacuida", "Mercedes"),
        ]

    def test_exact_roster_name_is_accepted(self):
        match = race.match_driver("Polingua", self.roster)

        self.assertEqual(match.canonical, "Polingua")
        self.assertEqual(match.suggestion, "Polingua")
        self.assertEqual(match.method, "exact")
        self.assertFalse(match.needs_review)

    def test_normalized_case_accents_and_punctuation_are_accepted(self):
        roster = [race.DriverEntry("Nico Hülkenberg", "Audi")]

        match = race.match_driver("P15 NÍCO-HULKENBERG Audi", roster)

        self.assertEqual(match.canonical, "Nico Hülkenberg")
        self.assertEqual(match.method, "exact")
        self.assertFalse(match.needs_review)

    def test_controlled_alias_is_accepted_only_when_target_is_on_roster(self):
        match = race.match_driver("P2 poli ngua Red Bull", self.roster)
        outside_roster = race.match_driver(
            "poli ngua", [race.DriverEntry("Alice", "Team A")]
        )

        self.assertEqual(match.canonical, "Polingua")
        self.assertEqual(match.method, "alias")
        self.assertFalse(match.needs_review)
        self.assertIsNone(outside_roster.canonical)
        self.assertIsNone(outside_roster.suggestion)
        self.assertTrue(outside_roster.needs_review)

    def test_fuzzy_match_is_only_a_review_suggestion(self):
        match = race.match_driver("Polingla", self.roster)

        self.assertIsNone(match.canonical)
        self.assertEqual(match.suggestion, "Polingua")
        self.assertEqual(match.method, "fuzzy")
        self.assertTrue(match.needs_review)
        self.assertGreaterEqual(match.score, 0.84)

    def test_low_confidence_exact_match_is_not_silently_accepted(self):
        match = race.match_driver("Fatacuida", self.roster, ocr_confidence=0.4)

        self.assertIsNone(match.canonical)
        self.assertEqual(match.suggestion, "Fatacuida")
        self.assertEqual(match.method, "exact")
        self.assertTrue(match.needs_review)
        self.assertIn("Low OCR confidence", match.reason)


class ScreenshotMergeTests(unittest.TestCase):
    def test_column_header_tokens_are_ignored_during_row_extraction(self):
        roster = [
            race.DriverEntry("TomasRodri21", "McLaren"),
            race.DriverEntry("Polingua", "Red Bull"),
            race.DriverEntry("Fatacuida", "Mercedes"),
        ]
        tokens = [
            race.OcrToken("POS", 0.99, 10, 10, 45, 30, "Screenshot 1"),
            race.OcrToken("DRIVER", 0.99, 100, 10, 180, 30, "Screenshot 1"),
            race.OcrToken("TEAM", 0.99, 250, 10, 310, 30, "Screenshot 1"),
        ]

        rows = race.extract_results_from_tokens(tokens, roster, source="Screenshot 1")

        self.assertEqual(rows, [])

    def test_two_screenshot_overlap_is_deduplicated_and_sources_are_combined(self):
        first = extracted(
            5,
            "Polingua",
            "Screenshot 1",
            confidence=0.82,
            raw_text="5 Polingua",
            issues=["first note"],
        )
        second = extracted(
            5,
            "Polingua",
            "Screenshot 2",
            confidence=0.97,
            raw_text="P5 Polingua Red Bull",
            issues=["second note"],
        )

        merged = race.merge_screenshot_results([[first], [second]])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].sources, ["Screenshot 1", "Screenshot 2"])
        self.assertEqual(merged[0].confidence, 0.97)
        self.assertEqual(merged[0].raw_text, "P5 Polingua Red Bull")
        self.assertEqual(merged[0].issues, ["first note", "second note"])

    def test_same_driver_at_two_positions_flags_position_conflict_on_both_rows(self):
        merged = race.merge_screenshot_results(
            [
                [extracted(2, "Polingua", "Screenshot 1")],
                [extracted(3, "Polingua", "Screenshot 2")],
            ]
        )

        self.assertEqual(len(merged), 2)
        for row in merged:
            self.assertIn("Conflicting positions were read for this driver.", row.issues)

    def test_same_position_with_two_drivers_flags_driver_conflict_on_both_rows(self):
        merged = race.merge_screenshot_results(
            [
                [extracted(2, "Polingua", "Screenshot 1")],
                [extracted(2, "Fatacuida", "Screenshot 2")],
            ]
        )

        self.assertEqual(len(merged), 2)
        for row in merged:
            self.assertIn("Conflicting drivers were read for this position.", row.issues)


class ScoringAndReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = [
            race.DriverEntry("Alice", "Red"),
            race.DriverEntry("Bob", "Blue"),
            race.DriverEntry("Charlie", "Green"),
        ]
        self.scoring = {1: 25.0, 2: 18.0, 3: 15.0}

    def test_race_and_sprint_scoring_are_verified_separately(self):
        standings = scoring_history()

        race_profile = race.infer_scoring_profile(
            standings,
            game="F1 25",
            season="2026-T01",
            league="League",
            event_type="R",
            grid_size=3,
        )
        sprint_profile = race.infer_scoring_profile(
            standings,
            game="F1 25",
            season="2026-T01",
            league="League",
            event_type="SR",
            grid_size=3,
        )

        self.assertEqual(race_profile, {1: 25.0, 2: 18.0, 3: 15.0})
        self.assertEqual(sprint_profile, {1: 8.0, 2: 7.0, 3: 6.0})
        self.assertEqual(race.scoring_profile_from_project_rules("R", 12)[11], 0.0)
        self.assertEqual(race.scoring_profile_from_project_rules("SR", 10)[9], 0.0)

    def test_first_sprint_uses_verified_project_scale_after_standard_race_history(self):
        standings = scoring_history()
        standings = standings[~standings["Type"].eq("SR")].copy()

        sprint_profile = race.infer_scoring_profile(
            standings,
            game="F1 25",
            season="2026-T01",
            league="League",
            event_type="SR",
            grid_size=3,
        )

        self.assertEqual(sprint_profile, {1: 8.0, 2: 7.0, 3: 6.0})

    def test_first_sprint_fallback_rejects_nonstandard_race_scoring(self):
        standings = scoring_history()
        standings = standings[~standings["Type"].eq("SR")].copy()
        standings.loc[standings["Finish Pos"].eq(1), "Points"] = 24

        with self.assertRaisesRegex(
            race.ScoringProfileError,
            "Race scoring does not match the verified project rules",
        ):
            race.infer_scoring_profile(
                standings,
                game="F1 25",
                season="2026-T01",
                league="League",
                event_type="SR",
                grid_size=3,
            )

    def test_partial_sprint_history_does_not_use_first_sprint_fallback(self):
        standings = scoring_history()
        standings = standings[
            standings["Type"].eq("R")
            | (standings["Type"].eq("SR") & standings["Finish Pos"].eq(1))
        ].copy()

        with self.assertRaisesRegex(
            race.ScoringProfileError,
            "does not contain enough results",
        ):
            race.infer_scoring_profile(
                standings,
                game="F1 25",
                season="2026-T01",
                league="League",
                event_type="SR",
                grid_size=3,
            )

    def test_scoring_verification_rejects_inconsistent_points_for_a_position(self):
        standings = scoring_history()
        mask = (
            standings["Type"].eq("R")
            & standings["Round"].eq(2)
            & standings["Finish Pos"].eq(2)
        )
        standings.loc[mask, "Points"] = 17

        with self.assertRaisesRegex(race.ScoringProfileError, r"position\(s\): 2"):
            race.infer_scoring_profile(
                standings,
                game="F1 25",
                season="2026-T01",
                league="League",
                event_type="R",
                grid_size=3,
            )

    def test_review_derives_team_and_points_from_confirmed_positions(self):
        validation = race.validate_review_rows(
            [
                {"Position": 1, "Driver": "Alice", "Points": 0},
                {"Position": 2, "Driver": "Bob", "Points": 999},
                {"Position": 3, "Driver": "Charlie", "Points": -1},
            ],
            self.roster,
            self.scoring,
        )

        self.assertTrue(validation.is_valid)
        self.assertEqual(
            validation.rows,
            [
                {"Position": 1, "Driver": "Alice", "Team": "Red", "Points": 25.0},
                {"Position": 2, "Driver": "Bob", "Team": "Blue", "Points": 18.0},
                {"Position": 3, "Driver": "Charlie", "Team": "Green", "Points": 15.0},
            ],
        )

    def test_review_blocks_duplicate_and_missing_positions_and_drivers(self):
        validation = race.validate_review_rows(
            [
                {"Position": 1, "Driver": "Alice"},
                {"Position": 1, "Driver": "Alice"},
                {"Position": 3, "Driver": "Bob"},
            ],
            self.roster,
            self.scoring,
        )
        blockers = "\n".join(validation.blockers)

        self.assertFalse(validation.is_valid)
        self.assertIn("Duplicate finishing position(s): 1.", blockers)
        self.assertIn("Duplicate driver(s): Alice.", blockers)
        self.assertIn("Missing finishing position(s): 2.", blockers)
        self.assertIn("Missing roster driver(s): Charlie.", blockers)


class RealWorkbookTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REAL_WORKBOOK.is_file():
            raise AssertionError(f"Project workbook not found: {REAL_WORKBOOK}")

        cls.standings = core.load_standings_data(REAL_WORKBOOK)
        cls.calendar = core.load_calendar_data(REAL_WORKBOOK)
        _, context = core.latest_league_slice(cls.standings)
        cls.game = str(context["Game"])
        cls.season = str(context["SeasonLabel"])
        cls.league = str(context["League Name"])
        cls.roster = race.derive_championship_roster(
            cls.standings,
            game=cls.game,
            season=cls.season,
            league=cls.league,
        )

        candidates = cls.calendar[
            cls.calendar["League Name"].eq(cls.league)
            & cls.calendar["Status"].str.casefold().eq("upcoming")
        ].sort_values(["Round", "Date"], na_position="last")
        cls.metadata = None
        for _, calendar_row in candidates.iterrows():
            candidate = workbook.RaceMetadata(
                game=cls.game,
                season=cls.season,
                league=cls.league,
                round_number=int(calendar_row["Round"]),
                event_type="R",
                gp_name=str(calendar_row["GP Name"]),
            )
            if not workbook.event_already_exists(cls.standings, candidate):
                cls.metadata = candidate
                break
        if cls.metadata is None:
            raise AssertionError(
                "The real workbook needs an upcoming, not-yet-imported calendar event for transaction tests."
            )

        cls.scoring = race.infer_scoring_profile(
            cls.standings,
            game=cls.game,
            season=cls.season,
            league=cls.league,
            event_type="R",
            grid_size=len(cls.roster),
        )
        validation = race.validate_review_rows(
            [
                {"Position": position, "Driver": entry.driver}
                for position, entry in enumerate(cls.roster, start=1)
            ],
            cls.roster,
            cls.scoring,
        )
        if not validation.is_valid:
            raise AssertionError("Could not build a valid approved result: " + "; ".join(validation.blockers))
        cls.approved_rows = validation.rows

    def copy_real_workbook(self, directory: Path) -> Path:
        copied = directory / REAL_WORKBOOK.name
        shutil.copy2(REAL_WORKBOOK, copied)
        return copied

    def test_no_workbook_mutation_occurs_without_explicit_approval(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            original_bytes = copied.read_bytes()
            backup_directory = directory / "backups"

            with self.assertRaises(workbook.ApprovalRequiredError):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=self.approved_rows,
                    scoring_profile=self.scoring,
                    expected_sha256=workbook.workbook_fingerprint(copied),
                    approved=False,
                    backup_directory=backup_directory,
                )

            self.assertEqual(copied.read_bytes(), original_bytes)
            self.assertFalse(backup_directory.exists())

    def test_stale_workbook_hash_blocks_update_without_mutation(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            original_bytes = copied.read_bytes()
            backup_directory = directory / "backups"

            with self.assertRaises(workbook.StaleWorkbookError):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=self.approved_rows,
                    scoring_profile=self.scoring,
                    expected_sha256="0" * 64,
                    approved=True,
                    backup_directory=backup_directory,
                )

            self.assertEqual(copied.read_bytes(), original_bytes)
            self.assertFalse(backup_directory.exists())

    def test_mid_transaction_external_change_blocks_replace(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            expected_sha = workbook.workbook_fingerprint(copied)
            external_bytes = copied.read_bytes() + b"external-save"
            original_verify = workbook._verify_untouched_parts

            def mutate_after_staging(source, candidate, changed_parts):
                original_verify(source, candidate, changed_parts)
                copied.write_bytes(external_bytes)

            with (
                mock.patch.object(workbook, "_verify_untouched_parts", side_effect=mutate_after_staging),
                self.assertRaises(workbook.StaleWorkbookError),
            ):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=self.approved_rows,
                    scoring_profile=self.scoring,
                    expected_sha256=expected_sha,
                    approved=True,
                    backup_directory=directory / "backups",
                )

            self.assertEqual(copied.read_bytes(), external_bytes)
            self.assertFalse((directory / "backups").exists())

    def test_external_change_after_recovery_copy_blocks_replace(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            expected_sha = workbook.workbook_fingerprint(copied)
            external_bytes = copied.read_bytes() + b"late-external-save"
            original_copystat = workbook.shutil.copystat

            def mutate_after_candidate_metadata(source, destination, *args, **kwargs):
                original_copystat(source, destination, *args, **kwargs)
                if ".race-import-" in Path(destination).name:
                    copied.write_bytes(external_bytes)

            with (
                mock.patch.object(workbook.shutil, "copystat", side_effect=mutate_after_candidate_metadata),
                self.assertRaises(workbook.StaleWorkbookError),
            ):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=self.approved_rows,
                    scoring_profile=self.scoring,
                    expected_sha256=expected_sha,
                    approved=True,
                    backup_directory=directory / "backups",
                )

            self.assertEqual(copied.read_bytes(), external_bytes)
            backups = list((directory / "backups").iterdir())
            self.assertEqual(1, len(backups))
            self.assertEqual(expected_sha, workbook.workbook_fingerprint(backups[0]))

    def test_writer_rechecks_controlled_roster_without_mutation(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            original_bytes = copied.read_bytes()
            tampered_rows = [dict(row) for row in self.approved_rows]
            tampered_rows[0]["Driver"] = "Unknown OCR Guess"
            tampered_rows[0]["Team"] = "Unknown Team"
            backup_directory = directory / "backups"

            with self.assertRaises(workbook.WorkbookUpdateError):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=tampered_rows,
                    scoring_profile=self.scoring,
                    expected_sha256=workbook.workbook_fingerprint(copied),
                    approved=True,
                    backup_directory=backup_directory,
                )

            self.assertEqual(copied.read_bytes(), original_bytes)
            self.assertFalse(backup_directory.exists())

    def test_writer_rejects_invented_sprint_metadata_without_mutation(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            original_bytes = copied.read_bytes()
            invented = workbook.RaceMetadata(
                game=self.metadata.game,
                season=self.metadata.season,
                league=self.metadata.league,
                round_number=self.metadata.round_number,
                event_type="SR",
                gp_name="Invented Grand Prix",
            )

            with self.assertRaisesRegex(workbook.WorkbookUpdateError, "Calendar row"):
                workbook.commit_race_import(
                    copied,
                    metadata=invented,
                    rows=(),
                    scoring_profile={},
                    expected_sha256=workbook.workbook_fingerprint(copied),
                    approved=True,
                    backup_directory=directory / "backups",
                )

            self.assertEqual(copied.read_bytes(), original_bytes)
            self.assertFalse((directory / "backups").exists())

    def test_successful_append_preserves_package_helpers_and_blocks_repeat_import(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            backup_directory = directory / "backups"
            original_workbook_bytes = copied.read_bytes()
            before_standings = core.load_standings_data(copied)
            before_parts = archive_payloads(copied)
            sheet_parts = worksheet_parts(copied)
            leagues_part = sheet_parts["Leagues"]
            calendar_part = sheet_parts["Calendar"]
            helper_cells_before = column_cell_snapshots(
                before_parts[leagues_part], {"O", "P"}
            )
            self.assertTrue(helper_cells_before, "The real workbook must exercise O:P helper preservation.")

            result = workbook.commit_race_import(
                copied,
                metadata=self.metadata,
                rows=self.approved_rows,
                scoring_profile=self.scoring,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=backup_directory,
            )

            self.assertEqual(result.rows_added, len(self.roster))
            self.assertEqual(result.last_excel_row - result.first_excel_row + 1, len(self.roster))
            self.assertTrue(result.calendar_updated)
            self.assertEqual(result.workbook_sha256, workbook.workbook_fingerprint(copied))
            self.assertTrue(result.backup_path.is_file())
            self.assertEqual(result.backup_path.read_bytes(), original_workbook_bytes)

            after_parts = archive_payloads(copied)
            self.assertEqual(list(after_parts), list(before_parts))
            differing_parts = {
                name for name in before_parts if before_parts[name] != after_parts[name]
            }
            self.assertEqual(differing_parts, {leagues_part, calendar_part})
            self.assertEqual(
                column_cell_snapshots(after_parts[leagues_part], {"O", "P"}),
                helper_cells_before,
            )

            after_standings = core.load_standings_data(copied)
            self.assertEqual(len(after_standings), len(before_standings) + len(self.roster))
            event_mask = (
                after_standings["Game"].eq(self.metadata.game)
                & after_standings["SeasonLabel"].eq(self.metadata.season)
                & after_standings["League Name"].eq(self.metadata.league)
                & after_standings["Round"].eq(self.metadata.round_number)
                & after_standings["Type"].eq(self.metadata.event_type)
                & after_standings["GP Name"].eq(self.metadata.gp_name)
            )
            actual = (
                after_standings.loc[event_mask, ["Finish Pos", "Driver", "Team", "Points"]]
                .rename(columns={"Finish Pos": "Position"})
                .sort_values("Position")
                .reset_index(drop=True)
            )
            expected = pd.DataFrame(self.approved_rows).sort_values("Position").reset_index(drop=True)
            pd.testing.assert_frame_equal(
                actual,
                expected[["Position", "Driver", "Team", "Points"]],
                check_dtype=False,
            )

            calendar = pd.read_excel(copied, sheet_name="Calendar")
            calendar_mask = (
                calendar["League Name"].fillna("").astype(str).str.strip().eq(self.metadata.league)
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(self.metadata.round_number)
                & calendar["GP Name"].fillna("").astype(str).str.strip().eq(self.metadata.gp_name)
            )
            self.assertEqual(calendar.loc[calendar_mask, "Status"].tolist(), ["Done"])

            committed_bytes = copied.read_bytes()
            existing_backups = set(backup_directory.iterdir())
            with self.assertRaises(workbook.DuplicateEventError):
                workbook.commit_race_import(
                    copied,
                    metadata=self.metadata,
                    rows=self.approved_rows,
                    scoring_profile=self.scoring,
                    expected_sha256=result.workbook_sha256,
                    approved=True,
                    backup_directory=backup_directory,
                )
            self.assertEqual(copied.read_bytes(), committed_bytes)
            self.assertEqual(set(backup_directory.iterdir()), existing_backups)

    def test_successful_sprint_append_does_not_complete_main_race_calendar_entry(self):
        sprint_metadata = workbook.RaceMetadata(
            game=self.metadata.game,
            season=self.metadata.season,
            league=self.metadata.league,
            round_number=self.metadata.round_number,
            event_type="SR",
            gp_name=self.metadata.gp_name,
        )
        sprint_scoring = race.scoring_profile_from_project_rules("SR", len(self.roster))
        sprint_validation = race.validate_review_rows(
            [
                {"Position": position, "Driver": entry.driver}
                for position, entry in enumerate(self.roster, start=1)
            ],
            self.roster,
            sprint_scoring,
        )
        self.assertTrue(sprint_validation.is_valid)

        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            before_calendar = pd.read_excel(copied, sheet_name="Calendar")
            calendar_mask = (
                before_calendar["League Name"].fillna("").astype(str).str.strip().eq(sprint_metadata.league)
                & pd.to_numeric(before_calendar["Round"], errors="coerce").eq(sprint_metadata.round_number)
                & before_calendar["GP Name"].fillna("").astype(str).str.strip().eq(sprint_metadata.gp_name)
            )
            self.assertEqual(int(calendar_mask.sum()), 1)
            original_status = before_calendar.loc[calendar_mask, "Status"].iloc[0]
            before_count = len(core.load_standings_data(copied))

            result = workbook.commit_race_import(
                copied,
                metadata=sprint_metadata,
                rows=sprint_validation.rows,
                scoring_profile=sprint_scoring,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "backups",
            )

            self.assertEqual(result.rows_added, len(self.roster))
            self.assertFalse(result.calendar_updated)
            after_standings = core.load_standings_data(copied)
            self.assertEqual(len(after_standings), before_count + len(self.roster))
            self.assertTrue(workbook.event_already_exists(after_standings, sprint_metadata))
            after_calendar = pd.read_excel(copied, sheet_name="Calendar")
            self.assertEqual(
                after_calendar.loc[calendar_mask, "Status"].iloc[0],
                original_status,
            )

    def test_pivot_source_extends_when_append_crosses_existing_range(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_real_workbook(directory)
            before_parts = archive_payloads(copied)
            definition = before_parts[workbook._PIVOT_SOURCE_PART]
            reduced_definition = re.sub(
                rb'(<worksheetSource\b[^>]*\bref="[A-Z]+\d+:[A-Z]+)\d+("[^>]*\bsheet="Leagues"[^>]*/>)',
                rb'\g<1>1750\g<2>',
                definition,
                count=1,
            )
            with ZipFile(copied, "w") as target:
                for name, payload in before_parts.items():
                    target.writestr(name, reduced_definition if name == workbook._PIVOT_SOURCE_PART else payload)

            result = workbook.commit_race_import(
                copied,
                metadata=self.metadata,
                rows=self.approved_rows,
                scoring_profile=self.scoring,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "backups",
            )

            with ZipFile(copied) as archive:
                updated_definition = archive.read(workbook._PIVOT_SOURCE_PART)
            self.assertIn(
                f'A1:J{result.last_excel_row}'.encode("ascii"),
                updated_definition,
            )


if __name__ == "__main__":
    unittest.main()
