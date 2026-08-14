from __future__ import annotations

import re
import shutil
from datetime import date, datetime, time, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd

import dashboard_core as core
import league_config
import league_workbook
import race_correction as correction
import race_import as race
import race_import_ui as import_ui
import race_workbook as workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"


def archive_payloads(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {item.filename: archive.read(item.filename) for item in archive.infolist()}


def column_cell_snapshots(worksheet_xml: bytes, columns: set[str]) -> dict[str, bytes]:
    root = ET.fromstring(worksheet_xml)
    namespace = root.tag[1:].partition("}")[0]
    snapshots: dict[str, bytes] = {}
    for cell in root.iter(f"{{{namespace}}}c"):
        reference = cell.attrib.get("r", "")
        match = re.match(r"([A-Z]+)", reference)
        if match and match.group(1) in columns:
            snapshots[reference] = ET.tostring(cell, encoding="utf-8")
    return snapshots


def event_rows(data: pd.DataFrame, metadata: workbook.RaceMetadata) -> pd.DataFrame:
    return (
        data.loc[workbook._event_mask(data, metadata)]
        .sort_values("Finish Pos")
        .reset_index(drop=True)
    )


class RealWorkbookCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REAL_WORKBOOK.is_file():
            raise AssertionError(f"Project workbook not found: {REAL_WORKBOOK}")
        cls.standings = core.load_standings_data(REAL_WORKBOOK)
        cls.metadata = workbook.RaceMetadata(
            game="F1 25: 2026 Season pack",
            season="2026-T02",
            league="Teikirise",
            round_number=3,
            event_type="R",
            gp_name="Belgian GP",
        )
        cls.sprint_metadata = workbook.RaceMetadata(
            game=cls.metadata.game,
            season=cls.metadata.season,
            league=cls.metadata.league,
            round_number=2,
            event_type="SR",
            gp_name="British GP",
        )
        if len(event_rows(cls.standings, cls.metadata)) != 22:
            raise AssertionError("The real workbook must contain the Round 3 Race fixture.")
        if len(event_rows(cls.standings, cls.sprint_metadata)) != 22:
            raise AssertionError("The real workbook must contain the Round 2 Sprint fixture.")
        cls.roster = race.derive_championship_roster(
            cls.standings,
            game=cls.metadata.game,
            season=cls.metadata.season,
            league=cls.metadata.league,
        )
        cls.scoring = race.infer_scoring_profile(
            cls.standings,
            game=cls.metadata.game,
            season=cls.metadata.season,
            league=cls.metadata.league,
            event_type="R",
            grid_size=len(cls.roster),
        )
        cls.sprint_scoring = race.infer_scoring_profile(
            cls.standings,
            game=cls.metadata.game,
            season=cls.metadata.season,
            league=cls.metadata.league,
            event_type="SR",
            grid_size=len(cls.roster),
        )
        target_roster = {
            (str(row.Driver).strip(), str(row.Team).strip())
            for row in event_rows(cls.standings, cls.metadata).itertuples(index=False)
        }
        if target_roster != {(entry.driver, entry.team) for entry in cls.roster}:
            raise AssertionError("The correction fixture must match the authoritative roster.")

    def copy_workbook(self, directory: Path) -> Path:
        copied = directory / REAL_WORKBOOK.name
        shutil.copy2(REAL_WORKBOOK, copied)
        return copied

    def replacement_rows(self, scoring: dict[int, float] | None = None) -> list[dict]:
        profile = self.scoring if scoring is None else scoring
        rows: list[dict] = []
        for position, entry in enumerate(reversed(self.roster), start=1):
            rows.append(
                {
                    "Position": position,
                    "Driver": entry.driver,
                    "Team": entry.team,
                    "Points": profile[position],
                    "Time": "90:00.000" if position == 1 else f"+{position}.000",
                    "Fastest Lap": f"1:{20 + position:02d}.000",
                }
            )
        return rows

    def test_snapshot_is_complete_stable_and_binds_calendar_state(self):
        first = correction.load_event_snapshot(REAL_WORKBOOK, self.metadata)
        second = correction.load_event_snapshot(REAL_WORKBOOK, self.metadata)

        self.assertEqual(first, second)
        self.assertEqual(len(first.rows), len(self.roster))
        self.assertEqual([row.position for row in first.rows], list(range(1, 23)))
        self.assertRegex(first.digest, r"^[0-9a-f]{64}$")
        self.assertEqual(first.calendar_status, "Done")

    def test_replace_is_in_place_and_preserves_later_rows_helpers_and_package(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_workbook(directory)
            original_bytes = copied.read_bytes()
            before_parts = archive_payloads(copied)
            with ZipFile(copied) as archive:
                sheet_paths = workbook._sheet_paths(archive)
            leagues_part = sheet_paths["Leagues"]
            helper_cells = column_cell_snapshots(before_parts[leagues_part], {"O", "P"})
            later_metadata = workbook.RaceMetadata(
                game=self.metadata.game,
                season=self.metadata.season,
                league=self.metadata.league,
                round_number=4,
                event_type="R",
                gp_name="Hungarian GP",
            )
            later_before = event_rows(core.load_standings_data(copied), later_metadata)
            snapshot = correction.load_event_snapshot(copied, self.metadata)

            result = correction.commit_event_correction(
                copied,
                metadata=self.metadata,
                action=correction.CorrectionAction.REPLACE,
                rows=self.replacement_rows(),
                authoritative_roster=self.roster,
                authoritative_scoring=self.scoring,
                expected_event_digest=snapshot.digest,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "backups",
            )

            self.assertEqual(result.rows_replaced, len(self.roster))
            self.assertEqual(result.rows_removed, 0)
            self.assertFalse(result.calendar_updated)
            self.assertEqual(result.affected_excel_rows, tuple(row.excel_row for row in snapshot.rows))
            self.assertEqual(result.backup_path.read_bytes(), original_bytes)
            self.assertEqual(result.workbook_sha256, workbook.workbook_fingerprint(copied))

            after_snapshot = correction.load_event_snapshot(copied, self.metadata)
            self.assertEqual(
                [row.driver for row in after_snapshot.rows],
                [entry.driver for entry in reversed(self.roster)],
            )
            self.assertEqual(after_snapshot.rows[0].time, "90:00.000")
            self.assertEqual(after_snapshot.rows[-1].fastest_lap, "1:42.000")
            pd.testing.assert_frame_equal(
                event_rows(core.load_standings_data(copied), later_metadata),
                later_before,
            )

            after_parts = archive_payloads(copied)
            self.assertEqual(list(after_parts), list(before_parts))
            changed_parts = {
                name for name in before_parts if before_parts[name] != after_parts[name]
            }
            self.assertEqual(changed_parts, {leagues_part})
            self.assertEqual(
                column_cell_snapshots(after_parts[leagues_part], {"O", "P"}),
                helper_cells,
            )
            self.assertEqual(
                after_parts[workbook._PIVOT_SOURCE_PART],
                before_parts[workbook._PIVOT_SOURCE_PART],
            )

    def test_race_undo_clears_only_event_cells_and_reopens_calendar(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_workbook(directory)
            before_parts = archive_payloads(copied)
            with ZipFile(copied) as archive:
                sheet_paths = workbook._sheet_paths(archive)
            leagues_part = sheet_paths["Leagues"]
            calendar_part = sheet_paths["Calendar"]
            helper_cells = column_cell_snapshots(before_parts[leagues_part], {"O", "P"})
            later_metadata = workbook.RaceMetadata(
                game=self.metadata.game,
                season=self.metadata.season,
                league=self.metadata.league,
                round_number=4,
                event_type="R",
                gp_name="Hungarian GP",
            )
            later_before = event_rows(core.load_standings_data(copied), later_metadata)
            snapshot = correction.load_event_snapshot(copied, self.metadata)

            result = correction.commit_event_correction(
                copied,
                metadata=self.metadata,
                action="undo",
                expected_event_digest=snapshot.digest,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "backups",
            )

            self.assertEqual(result.rows_removed, len(self.roster))
            self.assertEqual(result.rows_replaced, 0)
            self.assertTrue(result.calendar_updated)
            after = core.load_standings_data(copied)
            self.assertFalse(workbook.event_already_exists(after, self.metadata))
            pd.testing.assert_frame_equal(event_rows(after, later_metadata), later_before)
            calendar = pd.read_excel(copied, sheet_name="Calendar")
            calendar_mask = (
                calendar["League Name"].fillna("").astype(str).str.strip().eq(self.metadata.league)
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(self.metadata.round_number)
                & calendar["GP Name"].fillna("").astype(str).str.strip().eq(self.metadata.gp_name)
            )
            self.assertEqual(calendar.loc[calendar_mask, "Status"].tolist(), ["Upcoming"])

            after_parts = archive_payloads(copied)
            changed_parts = {
                name for name in before_parts if before_parts[name] != after_parts[name]
            }
            self.assertEqual(changed_parts, {leagues_part, calendar_part})
            self.assertEqual(
                column_cell_snapshots(after_parts[leagues_part], {"O", "P"}),
                helper_cells,
            )
            self.assertEqual(
                after_parts[workbook._PIVOT_SOURCE_PART],
                before_parts[workbook._PIVOT_SOURCE_PART],
            )

    def test_sprint_undo_never_changes_main_race_calendar_status(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_workbook(directory)
            before_parts = archive_payloads(copied)
            snapshot = correction.load_event_snapshot(copied, self.sprint_metadata)
            self.assertEqual(snapshot.calendar_status, "Done")

            result = correction.commit_event_correction(
                copied,
                metadata=self.sprint_metadata,
                action=correction.CorrectionAction.UNDO,
                expected_event_digest=snapshot.digest,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "backups",
            )

            self.assertFalse(result.calendar_updated)
            after_parts = archive_payloads(copied)
            with ZipFile(copied) as archive:
                leagues_part = workbook._sheet_paths(archive)["Leagues"]
            changed_parts = {
                name for name in before_parts if before_parts[name] != after_parts[name]
            }
            self.assertEqual(changed_parts, {leagues_part})
            calendar = pd.read_excel(copied, sheet_name="Calendar")
            calendar_mask = (
                calendar["League Name"].fillna("").astype(str).str.strip().eq(self.sprint_metadata.league)
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(self.sprint_metadata.round_number)
                & calendar["GP Name"].fillna("").astype(str).str.strip().eq(self.sprint_metadata.gp_name)
            )
            self.assertEqual(calendar.loc[calendar_mask, "Status"].tolist(), ["Done"])

    def test_active_configured_sprint_undo_becomes_exact_reimport_candidate(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_workbook(directory)
            league_id = "correction-active-sprint"
            race_profile = f"{league_id}:R:1"
            sprint_profile = f"{league_id}:SR:1"
            setup = league_config.LeagueSetup(
                key=league_config.LeagueKey(
                    league_id,
                    "F1 27",
                    "2027-T01",
                    "Correction Active Sprint 2027",
                ),
                calendar=(
                    league_config.CalendarRound(
                        1,
                        date(2027, 7, 18),
                        "Configured Sprint GP",
                        "Configured Circuit",
                        time_lisbon=time(15, 0),
                        has_sprint=True,
                    ),
                ),
                roster=(
                    league_config.RosterChange(
                        league_id, 1, "Driver One", "Team One"
                    ),
                ),
                scoring_profiles=(
                    league_config.ScoringProfile(
                        race_profile, league_id, "R", 1
                    ),
                    league_config.ScoringProfile(
                        sprint_profile, league_id, "SR", 1
                    ),
                ),
                scoring_points=(
                    league_config.ScoringPoint(race_profile, 1, 25),
                    league_config.ScoringPoint(sprint_profile, 1, 8),
                ),
                status="Active",
                created_utc=datetime(2027, 1, 1, tzinfo=timezone.utc),
            )
            league_workbook.commit_league_setup(
                copied,
                setup=setup,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "setup-backups",
            )
            rows = [
                {
                    "Position": 1,
                    "Driver": "Driver One",
                    "Team": "Team One",
                    "Time": "30:00.000",
                    "Fastest Lap": "1:20.000",
                }
            ]
            sprint_metadata = workbook.RaceMetadata(
                setup.key.game,
                setup.key.season,
                setup.key.league_name,
                1,
                "SR",
                "Configured Sprint GP",
                league_id,
            )
            race_metadata = workbook.RaceMetadata(
                setup.key.game,
                setup.key.season,
                setup.key.league_name,
                1,
                "R",
                "Configured Sprint GP",
                league_id,
            )
            workbook.commit_race_import(
                copied,
                metadata=sprint_metadata,
                rows=rows,
                scoring_profile={1: 8},
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                require_complete_timing=True,
                backup_directory=directory / "race-backups",
            )
            workbook.commit_race_import(
                copied,
                metadata=race_metadata,
                rows=rows,
                scoring_profile={1: 25},
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                require_complete_timing=True,
                backup_directory=directory / "race-backups",
            )
            snapshot = correction.load_event_snapshot(copied, sprint_metadata)
            undo = correction.commit_event_correction(
                copied,
                metadata=sprint_metadata,
                action="undo",
                expected_event_digest=snapshot.digest,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "correction-backups",
            )
            self.assertFalse(undo.calendar_updated)

            standings = core.load_standings_data(copied)
            calendar = core.load_calendar_data(copied)
            tables = league_config.load_config_tables(copied)
            defaults = import_ui.infer_admin_defaults(standings, calendar, tables)
            self.assertTrue(defaults.confident)
            self.assertEqual(
                defaults.championship,
                (setup.key.game, setup.key.season, setup.key.league_name),
            )
            self.assertEqual(defaults.event.round_number, 1)
            self.assertEqual(defaults.event.gp_name, "Configured Sprint GP")
            self.assertEqual(defaults.event.event_type, "SR")

            reimported = workbook.commit_race_import(
                copied,
                metadata=sprint_metadata,
                rows=rows,
                scoring_profile={1: 8},
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                require_complete_timing=True,
                backup_directory=directory / "race-backups",
            )
            self.assertEqual(reimported.rows_added, 1)
            self.assertTrue(
                workbook.event_already_exists(
                    core.load_standings_data(copied), sprint_metadata
                )
            )

    def test_approval_sha_digest_and_authoritative_roster_guards_are_fail_closed(self):
        cases = ("approval", "sha", "digest", "roster", "timing")
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
                directory = Path(temporary_directory)
                copied = self.copy_workbook(directory)
                original = copied.read_bytes()
                snapshot = correction.load_event_snapshot(copied, self.metadata)
                rows = self.replacement_rows()
                approved = True
                expected_sha = workbook.workbook_fingerprint(copied)
                expected_digest = snapshot.digest
                expected_error: type[Exception] = correction.EventCorrectionError
                if case == "approval":
                    approved = False
                    expected_error = workbook.ApprovalRequiredError
                elif case == "sha":
                    expected_sha = "0" * 64
                    expected_error = workbook.StaleWorkbookError
                elif case == "digest":
                    expected_digest = "0" * 64
                    expected_error = workbook.StaleWorkbookError
                elif case == "roster":
                    rows[0]["Driver"] = "Invented Driver"
                elif case == "timing":
                    rows[0]["Fastest Lap"] = ""
                    expected_error = workbook.WorkbookUpdateError

                with self.assertRaises(expected_error):
                    correction.commit_event_correction(
                        copied,
                        metadata=self.metadata,
                        action="replace",
                        rows=rows,
                        authoritative_roster=self.roster,
                        authoritative_scoring=self.scoring,
                        expected_event_digest=expected_digest,
                        expected_sha256=expected_sha,
                        approved=approved,
                        backup_directory=directory / "backups",
                    )

                self.assertEqual(copied.read_bytes(), original)
                self.assertFalse((directory / "backups").exists())

    def test_completed_configured_league_allows_replace_but_blocks_undo(self):
        with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            copied = self.copy_workbook(directory)
            current_id = "correction-completed-current"
            successor_id = "correction-completed-successor"

            def setup(
                league_id: str,
                *,
                league_name: str,
                season: str,
                cloned_from: str = "",
            ) -> league_config.LeagueSetup:
                profile_id = f"{league_id}:R:1"
                return league_config.LeagueSetup(
                    key=league_config.LeagueKey(
                        league_id, "F1 27", season, league_name
                    ),
                    calendar=(
                        league_config.CalendarRound(
                            1,
                            date(2027, 3, 14 if not cloned_from else 21),
                            "Configured GP" if not cloned_from else "Next GP",
                            "Configured Circuit",
                            time_lisbon=time(18, 0),
                            has_sprint=False,
                        ),
                    ),
                    roster=(
                        league_config.RosterChange(
                            league_id, 1, "Driver One", "Team Red"
                        ),
                        league_config.RosterChange(
                            league_id, 1, "Driver Two", "Team Blue"
                        ),
                    ),
                    scoring_profiles=(
                        league_config.ScoringProfile(
                            profile_id, league_id, "R", 1
                        ),
                    ),
                    scoring_points=(
                        league_config.ScoringPoint(profile_id, 1, 25),
                        league_config.ScoringPoint(profile_id, 2, 18),
                    ),
                    status="Active",
                    cloned_from_league_id=cloned_from,
                    created_utc=datetime(2027, 1, 1, tzinfo=timezone.utc),
                )

            current = setup(
                current_id,
                league_name="Correction Current 2027",
                season="2027-T01",
            )
            league_workbook.commit_league_setup(
                copied,
                setup=current,
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "setup-backups",
            )
            metadata = workbook.RaceMetadata(
                current.key.game,
                current.key.season,
                current.key.league_name,
                1,
                "R",
                "Configured GP",
                current_id,
            )
            rows = [
                {
                    "Position": 1,
                    "Driver": "Driver One",
                    "Team": "Team Red",
                    "Points": 25,
                    "Time": "30:00.000",
                    "Fastest Lap": "1:20.000",
                },
                {
                    "Position": 2,
                    "Driver": "Driver Two",
                    "Team": "Team Blue",
                    "Points": 18,
                    "Time": "+2.000",
                    "Fastest Lap": "1:21.000",
                },
            ]
            workbook.commit_race_import(
                copied,
                metadata=metadata,
                rows=rows,
                scoring_profile={1: 25, 2: 18},
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                require_complete_timing=True,
                backup_directory=directory / "race-backups",
            )
            successor = setup(
                successor_id,
                league_name="Correction Successor 2027",
                season="2027-T02",
                cloned_from=current_id,
            )
            league_workbook.commit_league_setup(
                copied,
                setup=successor,
                complete_league_ids=(current_id,),
                expected_sha256=workbook.workbook_fingerprint(copied),
                approved=True,
                backup_directory=directory / "setup-backups",
            )
            snapshot = correction.load_event_snapshot(copied, metadata)
            reviewed_sha = workbook.workbook_fingerprint(copied)

            with self.assertRaisesRegex(
                correction.EventCorrectionError, "cannot undo"
            ):
                correction.commit_event_correction(
                    copied,
                    metadata=metadata,
                    action="undo",
                    expected_event_digest=snapshot.digest,
                    expected_sha256=reviewed_sha,
                    approved=True,
                    backup_directory=directory / "correction-backups",
                )
            self.assertEqual(workbook.workbook_fingerprint(copied), reviewed_sha)

            replacement = [dict(row) for row in rows]
            replacement[0]["Time"] = "29:59.000"
            result = correction.commit_event_correction(
                copied,
                metadata=metadata,
                action="replace",
                rows=replacement,
                expected_event_digest=snapshot.digest,
                expected_sha256=reviewed_sha,
                approved=True,
                backup_directory=directory / "correction-backups",
            )
            self.assertEqual(result.rows_replaced, 2)


if __name__ == "__main__":
    unittest.main()
