from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

import league_config
import league_workbook
import race_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_WORKBOOK = PROJECT_ROOT / "F1_Standings.xlsx"
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def configured_setup(
    *,
    league_id: str,
    status: str = "Active",
    has_sprint: bool = True,
) -> league_config.LeagueSetup:
    key = league_config.LeagueKey(
        league_id,
        "F1 27",
        "2027-T01",
        f"Configured {league_id}",
    )
    race_profile = f"{league_id}:R:1"
    sprint_profile = f"{league_id}:SR:1"
    return league_config.LeagueSetup(
        key=key,
        calendar=(
            league_config.CalendarRound(
                1,
                date(2027, 3, 14),
                "Australian GP",
                "Albert Park Circuit",
                status="Upcoming",
                time_lisbon=time(18, 0),
                has_sprint=has_sprint,
            ),
        ),
        roster=(
            league_config.RosterChange(
                league_id, 1, "Driver One", "Team Red", ("D One",)
            ),
            league_config.RosterChange(
                league_id, 1, "Driver Two", "Team Blue"
            ),
        ),
        scoring_profiles=(
            league_config.ScoringProfile(
                race_profile,
                league_id,
                "R",
                1,
                fastest_lap_bonus=1,
                fastest_lap_max_finish=2,
            ),
            league_config.ScoringProfile(
                sprint_profile,
                league_id,
                "SR",
                1,
            ),
        ),
        scoring_points=(
            league_config.ScoringPoint(race_profile, 1, 25),
            league_config.ScoringPoint(race_profile, 2, 18),
            league_config.ScoringPoint(sprint_profile, 1, 8),
            league_config.ScoringPoint(sprint_profile, 2, 7),
        ),
        status=status,
        created_utc=datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc),
    )


def reviewed_rows(*, event_type: str, wrong_driver: bool = False) -> list[dict[str, object]]:
    if event_type == "R":
        points = (25.0, 19.0)
        times = ("32:15.123", "+2.456")
        laps = ("1:31.500", "1:31.200")
    else:
        points = (8.0, 7.0)
        times = ("18:05.321", "+1.250")
        laps = ("1:32.100", "1:31.900")
    return [
        {
            "Position": 1,
            "Driver": "Unknown Driver" if wrong_driver else "Driver One",
            "Team": "Team Red",
            "Points": points[0],
            "Time": times[0],
            "Fastest Lap": laps[0],
        },
        {
            "Position": 2,
            "Driver": "Driver Two",
            "Team": "Team Blue",
            "Points": points[1],
            "Time": times[1],
            "Fastest Lap": laps[1],
        },
    ]


class ConfiguredFirstEventWriterTests(unittest.TestCase):
    def _configured_workbook(
        self, root: Path, *, league_id: str
    ) -> tuple[Path, league_config.LeagueSetup]:
        target = root / "F1_Standings.xlsx"
        shutil.copy2(SOURCE_WORKBOOK, target)
        setup = configured_setup(league_id=league_id)
        league_workbook.commit_league_setup(
            target,
            setup=setup,
            expected_sha256=race_workbook.workbook_fingerprint(target),
            approved=True,
            backup_directory=root / "setup-backups",
        )
        return target, setup

    @staticmethod
    def _metadata(
        setup: league_config.LeagueSetup, event_type: str
    ) -> race_workbook.RaceMetadata:
        return race_workbook.RaceMetadata(
            setup.key.game,
            setup.key.season,
            setup.key.league_name,
            1,
            event_type,
            "Australian GP",
            setup.key.league_id,
        )

    def test_first_configured_race_blocks_tampering_then_writes_bonus_and_timing(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target, setup = self._configured_workbook(
                root, league_id="configured-first-race"
            )
            metadata = self._metadata(setup, "R")
            reviewed_sha = race_workbook.workbook_fingerprint(target)

            with self.assertRaises(race_workbook.WorkbookUpdateError):
                race_workbook.commit_race_import(
                    target,
                    metadata=metadata,
                    rows=reviewed_rows(event_type="R", wrong_driver=True),
                    scoring_profile={1: 25, 2: 18},
                    expected_sha256=reviewed_sha,
                    approved=True,
                    require_complete_timing=True,
                    backup_directory=root / "race-backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)

            incorrect_points = reviewed_rows(event_type="R")
            incorrect_points[1]["Points"] = 18.0  # Omits the configured fastest-lap bonus.
            with self.assertRaises(race_workbook.WorkbookUpdateError):
                race_workbook.commit_race_import(
                    target,
                    metadata=metadata,
                    rows=incorrect_points,
                    scoring_profile={1: 25, 2: 18},
                    expected_sha256=reviewed_sha,
                    approved=True,
                    require_complete_timing=True,
                    backup_directory=root / "race-backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)

            result = race_workbook.commit_race_import(
                target,
                metadata=metadata,
                rows=reviewed_rows(event_type="R"),
                scoring_profile={1: 25, 2: 18},
                expected_sha256=reviewed_sha,
                approved=True,
                require_complete_timing=True,
                backup_directory=root / "race-backups",
            )
            self.assertTrue(result.calendar_updated)
            self.assertEqual(result.rows_added, 2)

            leagues = pd.read_excel(target, sheet_name="Leagues")
            imported = leagues[
                leagues["Game"].astype(str).eq(setup.key.game)
                & leagues["Season"].astype(str).eq(setup.key.season)
                & leagues["League Name"].astype(str).eq(setup.key.league_name)
                & leagues["Type"].astype(str).eq("R")
                & pd.to_numeric(leagues["Round"], errors="coerce").eq(1)
            ].sort_values("Finish Pos")
            self.assertEqual(
                list(imported[["Driver", "Team"]].itertuples(index=False, name=None)),
                [("Driver One", "Team Red"), ("Driver Two", "Team Blue")],
            )
            self.assertEqual(imported["Points"].astype(float).tolist(), [25.0, 19.0])
            self.assertEqual(imported["Time"].tolist(), ["32:15.123", "+2.456"])
            self.assertEqual(imported["Fastest Lap"].tolist(), ["1:31.500", "1:31.200"])

            calendar = pd.read_excel(target, sheet_name="Calendar")
            event = calendar[
                calendar["League ID"].fillna("").astype(str).eq(setup.key.league_id)
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(1)
            ]
            self.assertEqual(len(event), 1)
            self.assertEqual(event.iloc[0]["Status"], "Done")

    def test_first_configured_sprint_is_separate_and_leaves_calendar_upcoming(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target, setup = self._configured_workbook(
                root, league_id="configured-first-sprint"
            )
            metadata = self._metadata(setup, "SR")
            result = race_workbook.commit_race_import(
                target,
                metadata=metadata,
                rows=reviewed_rows(event_type="SR"),
                scoring_profile={1: 8, 2: 7},
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                require_complete_timing=True,
                backup_directory=root / "sprint-backups",
            )

            self.assertFalse(result.calendar_updated)
            leagues = pd.read_excel(target, sheet_name="Leagues")
            imported = leagues[
                leagues["Game"].astype(str).eq(setup.key.game)
                & leagues["Season"].astype(str).eq(setup.key.season)
                & leagues["League Name"].astype(str).eq(setup.key.league_name)
                & leagues["Type"].astype(str).eq("SR")
                & pd.to_numeric(leagues["Round"], errors="coerce").eq(1)
            ].sort_values("Finish Pos")
            self.assertEqual(len(imported), 2)
            self.assertEqual(imported["Points"].astype(float).tolist(), [8.0, 7.0])

            calendar = pd.read_excel(target, sheet_name="Calendar")
            event = calendar[
                calendar["League ID"].fillna("").astype(str).eq(setup.key.league_id)
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(1)
            ]
            self.assertEqual(len(event), 1)
            self.assertEqual(event.iloc[0]["Status"], "Upcoming")

    def test_draft_and_completed_configured_leagues_reject_normal_imports(self) -> None:
        for status in ("Draft", "Completed"):
            with self.subTest(status=status), tempfile.TemporaryDirectory(
                dir=TEST_TEMP_ROOT
            ) as raw:
                root = Path(raw)
                target = root / f"{status}.xlsx"
                shutil.copy2(SOURCE_WORKBOOK, target)
                setup = configured_setup(
                    league_id=f"configured-{status.casefold()}", status=status
                )
                league_workbook.commit_league_setup(
                    target,
                    setup=setup,
                    expected_sha256=race_workbook.workbook_fingerprint(target),
                    approved=True,
                    backup_directory=root / f"{status}-setup-backups",
                )
                reviewed_sha = race_workbook.workbook_fingerprint(target)
                with self.assertRaisesRegex(
                    race_workbook.WorkbookUpdateError, "cannot accept new results"
                ):
                    race_workbook.commit_race_import(
                        target,
                        metadata=self._metadata(setup, "R"),
                        rows=reviewed_rows(event_type="R"),
                        scoring_profile={1: 25, 2: 18},
                        expected_sha256=reviewed_sha,
                        approved=True,
                        require_complete_timing=True,
                        backup_directory=root / f"{status}-race-backups",
                    )
                self.assertEqual(
                    race_workbook.workbook_fingerprint(target), reviewed_sha
                )

    def test_successor_activates_only_after_prior_calendar_is_finished(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as raw:
            root = Path(raw)
            target, current = self._configured_workbook(
                root, league_id="configured-current"
            )
            successor = replace(
                configured_setup(league_id="configured-successor"),
                cloned_from_league_id=current.key.league_id,
            )
            reviewed_sha = race_workbook.workbook_fingerprint(target)
            with self.assertRaises(league_workbook.LeagueWorkbookError):
                league_workbook.commit_league_setup(
                    target,
                    setup=successor,
                    complete_league_ids=(current.key.league_id,),
                    expected_sha256=reviewed_sha,
                    approved=True,
                    backup_directory=root / "setup-backups",
                )
            self.assertEqual(race_workbook.workbook_fingerprint(target), reviewed_sha)

            race_workbook.commit_race_import(
                target,
                metadata=self._metadata(current, "R"),
                rows=reviewed_rows(event_type="R"),
                scoring_profile={1: 25, 2: 18},
                expected_sha256=reviewed_sha,
                approved=True,
                require_complete_timing=True,
                backup_directory=root / "race-backups",
            )
            race_only_sha = race_workbook.workbook_fingerprint(target)
            with self.assertRaisesRegex(
                league_workbook.LeagueWorkbookError, "complete exact Sprint"
            ):
                league_workbook.commit_league_setup(
                    target,
                    setup=successor,
                    complete_league_ids=(current.key.league_id,),
                    expected_sha256=race_only_sha,
                    approved=True,
                    backup_directory=root / "setup-backups",
                )
            self.assertEqual(
                race_workbook.workbook_fingerprint(target), race_only_sha
            )
            race_workbook.commit_race_import(
                target,
                metadata=self._metadata(current, "SR"),
                rows=reviewed_rows(event_type="SR"),
                scoring_profile={1: 8, 2: 7},
                expected_sha256=race_only_sha,
                approved=True,
                require_complete_timing=True,
                backup_directory=root / "sprint-backups",
            )
            league_workbook.commit_league_setup(
                target,
                setup=successor,
                complete_league_ids=(current.key.league_id,),
                expected_sha256=race_workbook.workbook_fingerprint(target),
                approved=True,
                backup_directory=root / "setup-backups",
            )
            leagues = pd.read_excel(target, sheet_name="League Config")
            statuses = dict(
                leagues[["League ID", "Status"]].itertuples(index=False, name=None)
            )
            self.assertEqual(statuses[current.key.league_id], "Completed")
            self.assertEqual(statuses[successor.key.league_id], "Active")


if __name__ == "__main__":
    unittest.main()
