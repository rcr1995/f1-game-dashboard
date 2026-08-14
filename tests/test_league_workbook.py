from __future__ import annotations

import shutil
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import pandas as pd

import league_workbook as subject
import race_workbook
import workbook_simplify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def _mutation(
    *,
    league_id: str = "league-test-2027",
    league_name: str = "Test League 2027",
    status: str = "Active",
    calendar_rounds: tuple[int, ...] = (1,),
) -> subject.LeagueWorkbookMutation:
    race_profile = f"{league_id}:R:1"
    sprint_profile = f"{league_id}:SR:1"
    return subject.LeagueWorkbookMutation(
        league_config=(
            {
                "League ID": league_id,
                "Game": "F1 27",
                "Season": "2027-T01",
                "League Name": league_name,
                "Status": status,
                "Cloned From League ID": "",
                "Created UTC": "2026-08-14T12:00:00Z",
                "Schema Version": 1,
            },
        ),
        roster_config=(
            {
                "League ID": league_id,
                "Effective From Round": 1,
                "Driver Name": "Driver One",
                "Team Name": "Team One",
                "OCR Aliases": "D One",
            },
            {
                "League ID": league_id,
                "Effective From Round": 1,
                "Driver Name": "Driver Two",
                "Team Name": "Team Two",
                "OCR Aliases": "",
            },
        ),
        scoring_profiles=(
            {
                "Profile ID": race_profile,
                "League ID": league_id,
                "Event Type": "R",
                "Effective From Round": 1,
                "Fastest Lap Bonus": 1,
                "Fastest Lap Max Finish": 2,
            },
            {
                "Profile ID": sprint_profile,
                "League ID": league_id,
                "Event Type": "SR",
                "Effective From Round": 1,
                "Fastest Lap Bonus": 0,
                "Fastest Lap Max Finish": "",
            },
        ),
        scoring_points=(
            {"Profile ID": race_profile, "Position": 1, "Points": 25},
            {"Profile ID": race_profile, "Position": 2, "Points": 18},
            {"Profile ID": sprint_profile, "Position": 1, "Points": 8},
            {"Profile ID": sprint_profile, "Position": 2, "Points": 7},
        ),
        calendar=tuple(
            {
                "League Name": league_name,
                "Round": round_number,
                "Date": f"2027-03-{13 + round_number:02d}",
                "GP Name": f"Grand Prix {round_number}",
                "Circuit": f"Circuit {round_number}",
                "Status": "Upcoming",
                "Time (Lisbon)": "06:00",
                "Game": "F1 27",
                "Season": "2027-T01",
                "Has Sprint": True,
                "League ID": league_id,
            }
            for round_number in calendar_rounds
        ),
    )


class LeagueWorkbookTransactionTests(unittest.TestCase):
    def _copy(self, directory: Path) -> Path:
        target = directory / "F1_Standings.xlsx"
        shutil.copy2(SOURCE_WORKBOOK, target)
        return target

    def test_adds_configuration_sheets_and_calendar_without_touching_other_parts(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            before_sha = race_workbook.workbook_fingerprint(target)
            with ZipFile(target, "r") as archive:
                before_parts = {name: archive.read(name) for name in archive.namelist()}

            result = subject.commit_league_workbook_update(
                target,
                mutation=_mutation(),
                expected_sha256=before_sha,
                approved=True,
                backup_directory=root / "backups",
            )

            self.assertNotEqual(result.workbook_sha256, before_sha)
            self.assertTrue(result.backup_path.is_file())
            self.assertEqual(race_workbook.workbook_fingerprint(result.backup_path), before_sha)
            with pd.ExcelFile(target) as workbook:
                for sheet in subject.CONFIG_SHEET_HEADERS:
                    self.assertIn(sheet, workbook.sheet_names)
            leagues = pd.read_excel(target, sheet_name="League Config")
            self.assertEqual(leagues.iloc[-1]["League ID"], "league-test-2027")
            roster = pd.read_excel(target, sheet_name="Roster Config")
            self.assertEqual(set(roster["Driver Name"]), {"Driver One", "Driver Two"})
            calendar = pd.read_excel(target, sheet_name="Calendar")
            new_row = calendar.iloc[-1]
            self.assertEqual(new_row["League Name"], "Test League 2027")
            self.assertEqual(int(new_row["Round"]), 1)
            self.assertEqual(new_row["Status"], "Upcoming")
            self.assertEqual(new_row["League ID"], "league-test-2027")

            with ZipFile(target, "r") as archive:
                after_parts = {name: archive.read(name) for name in archive.namelist()}
            self.assertIn(
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"',
                after_parts["[Content_Types].xml"],
            )
            self.assertNotIn(b"<ns0:Types", after_parts["[Content_Types].xml"])
            self.assertIn(
                b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"',
                after_parts["xl/workbook.xml"],
            )
            self.assertIn(
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"',
                after_parts["xl/_rels/workbook.xml.rels"],
            )
            roster_part = next(
                payload
                for name, payload in after_parts.items()
                if name.startswith("xl/worksheets/sheet")
                and b"OCR Aliases" in payload
            )
            self.assertIn(b'width="18"', roster_part)
            changed_existing = {
                name for name, payload in before_parts.items() if after_parts.get(name) != payload
            }
            self.assertEqual(
                changed_existing,
                {
                    "[Content_Types].xml",
                    "xl/workbook.xml",
                    "xl/_rels/workbook.xml.rels",
                    "xl/worksheets/sheet2.xml",
                },
            )
            self.assertEqual(before_parts["xl/worksheets/sheet1.xml"], after_parts["xl/worksheets/sheet1.xml"])

    def test_setup_accepts_simplified_workbook_without_pivot_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            legacy = self._copy(root)
            target = root / "F1_Standings.simplified.xlsx"
            workbook_simplify.stage_simplified_workbook(legacy, target)

            result = subject.commit_league_workbook_update(
                target,
                mutation=_mutation(),
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )

            self.assertTrue(result.workbook_sha256)
            with ZipFile(target) as archive:
                self.assertNotIn("Pivot", race_workbook._sheet_paths(archive))
                self.assertFalse(
                    any(
                        part.startswith(("xl/pivotCache/", "xl/pivotTables/"))
                        for part in archive.namelist()
                    )
                )
            with pd.ExcelFile(target) as workbook_file:
                self.assertIn("League Config", workbook_file.sheet_names)

    def test_second_snapshot_appends_without_recreating_or_rewriting_prior_rows(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            subject.commit_league_workbook_update(
                target,
                mutation=_mutation(calendar_rounds=(1, 5)),
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )
            before = pd.read_excel(target, sheet_name="Roster Config")
            mutation = subject.LeagueWorkbookMutation(
                roster_config=(
                    {
                        "League ID": "league-test-2027",
                        "Effective From Round": 5,
                        "Driver Name": "Driver One",
                        "Team Name": "New Team",
                        "OCR Aliases": "D One",
                    },
                    {
                        "League ID": "league-test-2027",
                        "Effective From Round": 5,
                        "Driver Name": "Driver Three",
                        "Team Name": "Team Three",
                        "OCR Aliases": "",
                    },
                )
            )
            subject.commit_league_workbook_update(
                target,
                mutation=mutation,
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )
            after = pd.read_excel(target, sheet_name="Roster Config")
            pd.testing.assert_frame_equal(after.iloc[: len(before)].reset_index(drop=True), before)
            later = after[pd.to_numeric(after["Effective From Round"]) == 5]
            self.assertEqual(set(later["Driver Name"]), {"Driver One", "Driver Three"})

    def test_requires_approval_and_current_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            target = self._copy(Path(raw))
            with self.assertRaises(race_workbook.ApprovalRequiredError):
                subject.commit_league_workbook_update(
                    target,
                    mutation=_mutation(),
                    expected_sha256=race_workbook.workbook_fingerprint(target),
                    approved=False,
                )
            with self.assertRaises(race_workbook.StaleWorkbookError):
                subject.commit_league_workbook_update(
                    target,
                    mutation=_mutation(),
                    expected_sha256="0" * 64,
                    approved=True,
                )

    def test_duplicate_config_is_blocked_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            subject.commit_league_workbook_update(
                target,
                mutation=_mutation(),
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )
            reviewed_sha = race_workbook.workbook_fingerprint(target)
            with self.assertRaises(subject.LeagueWorkbookError):
                subject.commit_league_workbook_update(
                    target,
                    mutation=_mutation(),
                    expected_sha256=reviewed_sha,
                    approved=True,
                    backup_directory=root / "backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)

    def test_snapshot_update_requires_active_status_and_exact_calendar_round(self) -> None:
        for status, expected_text in (
            ("Completed", "only to an Active league"),
            ("Active", "must match exactly one managed Calendar row"),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory(
                dir=TEST_TEMP_ROOT
            ) as raw:
                root = Path(raw)
                target = self._copy(root)
                subject.commit_league_workbook_update(
                    target,
                    mutation=_mutation(status=status),
                    expected_sha256=race_workbook.workbook_fingerprint(target),
                    approved=True,
                    backup_directory=root / "backups",
                )
                reviewed_sha = race_workbook.workbook_fingerprint(target)
                update = subject.LeagueWorkbookMutation(
                    roster_config=(
                        {
                            "League ID": "league-test-2027",
                            "Effective From Round": 5,
                            "Driver Name": "Driver One",
                            "Team Name": "Team One",
                            "OCR Aliases": "",
                        },
                        {
                            "League ID": "league-test-2027",
                            "Effective From Round": 5,
                            "Driver Name": "Driver Two",
                            "Team Name": "Team Two",
                            "OCR Aliases": "",
                        },
                    )
                )
                with self.assertRaisesRegex(subject.LeagueWorkbookError, expected_text):
                    subject.commit_league_workbook_update(
                        target,
                        mutation=update,
                        expected_sha256=reviewed_sha,
                        approved=True,
                        backup_directory=root / "backups",
                    )
                self.assertEqual(
                    race_workbook.workbook_fingerprint(target), reviewed_sha
                )

    def test_global_league_name_uniqueness_uses_canonical_identity(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            subject.commit_league_workbook_update(
                target,
                mutation=_mutation(),
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )
            reviewed_sha = race_workbook.workbook_fingerprint(target)
            punctuation_variant = _mutation(
                league_id="league-variant-2028",
                league_name="Tést---League 2027",
            )
            with self.assertRaisesRegex(
                subject.LeagueWorkbookError, "never been used"
            ):
                subject.commit_league_workbook_update(
                    target,
                    mutation=punctuation_variant,
                    expected_sha256=reviewed_sha,
                    approved=True,
                    backup_directory=root / "backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)

    def test_calendar_sprint_flag_parses_false_text_and_rejects_unknown_text(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            accepted = _mutation()
            accepted.calendar[0]["Has Sprint"] = "False"
            subject.commit_league_workbook_update(
                target,
                mutation=accepted,
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "backups",
            )
            calendar = pd.read_excel(target, sheet_name="Calendar")
            self.assertFalse(bool(calendar.iloc[-1]["Has Sprint"]))

        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target = self._copy(root)
            invalid = _mutation()
            invalid.calendar[0]["Has Sprint"] = "sometimes"
            reviewed_sha = race_workbook.workbook_fingerprint(target)
            with self.assertRaisesRegex(
                subject.LeagueWorkbookError, "invalid boolean"
            ):
                subject.commit_league_workbook_update(
                    target,
                    mutation=invalid,
                    expected_sha256=reviewed_sha,
                    approved=True,
                    backup_directory=root / "backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)


if __name__ == "__main__":
    unittest.main()
