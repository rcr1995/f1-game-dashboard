from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd

import dashboard_core as core
import race_import as race
import race_workbook as workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"
MAIN_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class TimingValidationTests(unittest.TestCase):
    def test_approved_timing_values_are_normalized_without_inventing_totals(self):
        rows = workbook._validate_commit_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Team": "Red",
                    "Points": 25,
                    "Time": " 82:50.787 ",
                    "Fastest Lap": "1:35.122",
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Team": "Blue",
                    "Points": 18,
                    "Time": "+0.946",
                    "Fastest Lap": pd.NA,
                },
                {
                    "Position": 3,
                    "Driver": "Charlie",
                    "Team": "Green",
                    "Points": 15,
                    "Time": "+1 LAP",
                    "Fastest Lap": "dnf",
                },
            ],
            {1: 25, 2: 18, 3: 15},
        )

        self.assertEqual(rows[0]["Time"].text, "82:50.787")
        self.assertEqual(rows[0]["Fastest Lap"].text, "1:35.122")
        self.assertEqual(rows[1]["Time"].text, "+0.946")
        self.assertIsNone(rows[1]["Fastest Lap"])
        self.assertEqual(rows[2]["Time"].text, "+1 LAP")
        self.assertEqual(rows[2]["Fastest Lap"].text, "dnf")

    def test_unsafe_or_semantically_invalid_timing_values_are_rejected(self):
        base = {"Position": 1, "Driver": "Alice", "Team": "Red", "Points": 25}
        invalid_values = (
            ("Time", "=WEBSERVICE(\"https://example.invalid\")"),
            ("Time", "1:99.000"),
            ("Time", 0.0575),
            ("Fastest Lap", "+0.946"),
        )
        for key, value in invalid_values:
            with self.subTest(key=key, value=value), self.assertRaises(workbook.WorkbookUpdateError):
                workbook._validate_commit_rows([{**base, key: value}], {1: 25})

    def test_strict_mode_requires_both_fields_and_uses_importer_canonical_forms(self):
        rows = workbook._validate_commit_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Team": "Red",
                    "Points": 25,
                    "Time": " 082:50,787 ",
                    "Fastest Lap": "1:33,122",
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Team": "Blue",
                    "Points": 18,
                    "Time": "+01 LAPS",
                    "Fastest Lap": "N/A",
                },
            ],
            {1: 25, 2: 18},
            require_complete_timing=True,
        )

        self.assertEqual(rows[0]["Time"].text, "82:50.787")
        self.assertEqual(rows[0]["Fastest Lap"].text, "1:33.122")
        self.assertEqual(rows[1]["Time"].text, "+1 Lap")
        self.assertEqual(rows[1]["Fastest Lap"].text, "N/A")

        base = {"Position": 1, "Driver": "Alice", "Team": "Red", "Points": 25}
        with self.assertRaisesRegex(workbook.WorkbookUpdateError, "canonical Time"):
            workbook._validate_commit_rows(
                [{**base, "Fastest Lap": "1:33.122"}],
                {1: 25},
                require_complete_timing=True,
            )
        with self.assertRaisesRegex(workbook.WorkbookUpdateError, "canonical Fastest Lap"):
            workbook._validate_commit_rows(
                [{**base, "Time": "82:50.787", "Fastest Lap": "DNF"}],
                {1: 25},
                require_complete_timing=True,
            )


class TimingWorkbookRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REAL_WORKBOOK.is_file():
            raise AssertionError(f"Project workbook not found: {REAL_WORKBOOK}")
        standings = core.load_standings_data(REAL_WORKBOOK)
        calendar = core.load_calendar_data(REAL_WORKBOOK)
        _, context = core.latest_league_slice(standings)
        cls.game = str(context["Game"])
        cls.season = str(context["SeasonLabel"])
        cls.league = str(context["League Name"])
        cls.roster = race.derive_championship_roster(
            standings,
            game=cls.game,
            season=cls.season,
            league=cls.league,
        )
        candidates = calendar[
            calendar["League Name"].eq(cls.league)
            & calendar["Status"].str.casefold().eq("upcoming")
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
            if not workbook.event_already_exists(standings, candidate):
                cls.metadata = candidate
                break
        if cls.metadata is None:
            raise AssertionError("The test workbook needs one upcoming event that has not been imported.")
        cls.scoring = race.infer_scoring_profile(
            standings,
            game=cls.game,
            season=cls.season,
            league=cls.league,
            event_type="R",
            grid_size=len(cls.roster),
        )
        validation = race.validate_review_rows(
            [
                {"Position": position, "Driver": roster_entry.driver}
                for position, roster_entry in enumerate(cls.roster, start=1)
            ],
            cls.roster,
            cls.scoring,
        )
        if not validation.is_valid:
            raise AssertionError("Could not create approved test rows: " + "; ".join(validation.blockers))
        cls.rows = [dict(row) for row in validation.rows]

    def test_k_l_values_survive_a_safe_commit_to_a_workbook_copy(self):
        approved_rows = [dict(row) for row in self.rows]
        for row in approved_rows:
            row.update({"Time": "DNF", "Fastest Lap": "N/A"})
        approved_rows[0].update({"Time": "82:50.787", "Fastest Lap": "1:33.122"})
        approved_rows[1].update({"Time": "+0.946", "Fastest Lap": "1:34.632"})
        approved_rows[2]["Time"] = "+1:09.463"
        approved_rows[3]["Time"] = "+1 Lap"
        approved_rows[-1].update({"Time": "DNF", "Fastest Lap": "1:36.789"})

        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            copied = directory / REAL_WORKBOOK.name
            shutil.copy2(REAL_WORKBOOK, copied)
            before_parts: dict[str, bytes]
            with ZipFile(copied) as archive:
                before_parts = {name: archive.read(name) for name in archive.namelist()}

            result = workbook.commit_race_import(
                copied,
                metadata=self.metadata,
                rows=approved_rows,
                scoring_profile=self.scoring,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                require_complete_timing=True,
                backup_directory=directory / "backups",
            )

            with ZipFile(copied) as archive:
                sheet_paths = workbook._sheet_paths(archive)
                sheet_part = sheet_paths["Leagues"]
                calendar_part = sheet_paths["Calendar"]
                worksheet = ET.fromstring(archive.read(sheet_part))
                changed_parts = {
                    name for name in archive.namelist() if archive.read(name) != before_parts[name]
                }
            cells = {
                cell.attrib["r"]: cell
                for cell in worksheet.findall(".//m:sheetData/m:row/m:c", MAIN_NS)
            }
            def inline_text(reference: str) -> str:
                cell = cells[reference]
                self.assertEqual(cell.attrib.get("t"), "inlineStr")
                return "".join(node.text or "" for node in cell.findall(".//m:t", MAIN_NS))

            first_row = result.first_excel_row
            self.assertEqual(inline_text(f"K{first_row}"), "82:50.787")
            self.assertEqual(inline_text(f"L{first_row}"), "1:33.122")
            self.assertEqual(inline_text(f"K{first_row + 1}"), "+0.946")
            self.assertEqual(inline_text(f"K{first_row + 2}"), "+1:09.463")
            self.assertEqual(inline_text(f"K{first_row + 3}"), "+1 Lap")
            self.assertEqual(inline_text(f"K{result.last_excel_row}"), "DNF")
            self.assertEqual(inline_text(f"L{result.last_excel_row}"), "1:36.789")

            allowed_changes = {
                sheet_part,
                workbook._PIVOT_SOURCE_PART,
                calendar_part,
            }
            self.assertTrue(changed_parts.issubset(allowed_changes))


if __name__ == "__main__":
    unittest.main()
