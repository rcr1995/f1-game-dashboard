from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timezone
from io import BytesIO
from pathlib import Path
import unittest

import pandas as pd

import league_config as config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def scoring_points(profile_id: str, values: list[float]) -> tuple[config.ScoringPoint, ...]:
    return tuple(
        config.ScoringPoint(profile_id, position, points)
        for position, points in enumerate(values, start=1)
    )


def basic_setup(
    *,
    league_id: str = "league-2027-t01",
    status: str = "Draft",
    with_sprint: bool = True,
) -> config.LeagueSetup:
    key = config.LeagueKey(league_id, "F1 27", "2027-T01", "New League")
    calendar = (
        config.CalendarRound(
            1,
            date(2027, 1, 10),
            "Australian GP",
            "Albert Park Circuit",
            time_lisbon=time(18, 0),
            has_sprint=False,
        ),
        config.CalendarRound(
            2,
            date(2027, 1, 17),
            "Chinese GP",
            "Shanghai International Circuit",
            time_lisbon=time(18, 0),
            has_sprint=with_sprint,
        ),
    )
    roster = (
        config.RosterChange(league_id, 1, "Alice", "Red", ("A. Lice",)),
        config.RosterChange(league_id, 1, "Bob", "Blue"),
    )
    race_id = f"{league_id}:R:1"
    profiles = [config.ScoringProfile(race_id, league_id, "R", 1, 1.0, 2)]
    points = list(scoring_points(race_id, [25, 18]))
    if with_sprint:
        sprint_id = f"{league_id}:SR:1"
        profiles.append(config.ScoringProfile(sprint_id, league_id, "SR", 1))
        points.extend(scoring_points(sprint_id, [8, 7]))
    return config.LeagueSetup(
        key,
        calendar,
        roster,
        tuple(profiles),
        tuple(points),
        status=status,
        created_utc=datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc),
    )


class LoaderAndFirstEventTests(unittest.TestCase):
    def test_legacy_workbook_without_config_sheets_loads_as_empty(self) -> None:
        tables = config.load_config_tables(PROJECT_ROOT / "F1_Standings.xlsx")

        self.assertTrue(tables.league_config.empty)
        self.assertTrue(tables.roster_config.empty)
        self.assertTrue(tables.scoring_profiles.empty)
        self.assertTrue(tables.scoring_points.empty)
        config.validate_config_tables(tables)

    def test_xlsx_blank_optional_cells_do_not_become_literal_nan(self) -> None:
        tables = config.config_tables_from_setup(basic_setup())
        tables.league_config.loc[0, "Cloned From League ID"] = pd.NA
        tables.roster_config.loc[:, "OCR Aliases"] = pd.NA
        # Direct DataFrame callers and an actual Excel round-trip must both
        # treat missing optional text as an empty value, never as "nan".
        config.validate_config_tables(tables)

        content = BytesIO()
        with pd.ExcelWriter(content, engine="openpyxl") as writer:
            tables.league_config.to_excel(
                writer, sheet_name=config.LEAGUE_CONFIG_SHEET, index=False
            )
            tables.roster_config.to_excel(
                writer, sheet_name=config.ROSTER_CONFIG_SHEET, index=False
            )
            tables.scoring_profiles.to_excel(
                writer, sheet_name=config.SCORING_PROFILES_SHEET, index=False
            )
            tables.scoring_points.to_excel(
                writer, sheet_name=config.SCORING_POINTS_SHEET, index=False
            )
        content.seek(0)

        loaded = config.load_config_tables(content)
        config.validate_config_tables(loaded)
        self.assertEqual(loaded.league_config.loc[0, "Cloned From League ID"], "")
        self.assertTrue(loaded.roster_config["OCR Aliases"].eq("").all())

    def test_first_event_uses_config_without_any_result_history(self) -> None:
        setup = basic_setup()
        config.validate_league_setup(setup)
        tables = config.config_tables_from_setup(setup)

        roster = config.resolve_roster_snapshot(tables, setup.key.league_id, 1)
        scoring = config.resolve_scoring_profile(
            tables, setup.key.league_id, "R", 1, len(roster)
        )

        self.assertEqual([(row.driver_name, row.team_name) for row in roster], [("Alice", "Red"), ("Bob", "Blue")])
        self.assertEqual(scoring.points, {1: 25.0, 2: 18.0})
        self.assertEqual(scoring.fastest_lap_bonus, 1.0)

    def test_setup_digest_is_order_independent_but_team_sensitive(self) -> None:
        setup = basic_setup()
        reordered = replace(
            setup,
            calendar=tuple(reversed(setup.calendar)),
            roster=tuple(reversed(setup.roster)),
            scoring_profiles=tuple(reversed(setup.scoring_profiles)),
            scoring_points=tuple(reversed(setup.scoring_points)),
        )
        self.assertEqual(
            config.league_setup_digest(setup), config.league_setup_digest(reordered)
        )

        changed_roster = tuple(
            replace(row, team_name="Green") if row.driver_name == "Alice" else row
            for row in setup.roster
        )
        self.assertNotEqual(
            config.league_setup_digest(setup),
            config.league_setup_digest(replace(setup, roster=changed_roster)),
        )

    def test_setup_rejects_truthy_text_as_sprint_flag(self) -> None:
        setup = basic_setup()
        invalid_calendar = (
            replace(setup.calendar[0], has_sprint="False"),  # type: ignore[arg-type]
            setup.calendar[1],
        )
        with self.assertRaises(config.LeagueConfigValidationError) as raised:
            config.validate_league_setup(
                replace(setup, calendar=invalid_calendar)
            )
        self.assertIn("Has Sprint must be a boolean", str(raised.exception))


class RosterSnapshotTests(unittest.TestCase):
    def test_complete_snapshot_handles_new_driver_team_and_team_change(self) -> None:
        setup = basic_setup()
        changed = replace(
            setup,
            roster=setup.roster
            + (
                config.RosterChange(setup.key.league_id, 2, "Alice", "Green"),
                config.RosterChange(setup.key.league_id, 2, "Charlie", "Yellow"),
            ),
        )
        config.validate_league_setup(changed)
        tables = config.config_tables_from_setup(changed)

        round_one = config.resolve_roster_snapshot(tables, setup.key.league_id, 1)
        round_two = config.resolve_roster_snapshot(tables, setup.key.league_id, 2)

        self.assertEqual(
            {(row.driver_name, row.team_name) for row in round_one},
            {("Alice", "Red"), ("Bob", "Blue")},
        )
        self.assertEqual(
            {(row.driver_name, row.team_name) for row in round_two},
            {("Alice", "Green"), ("Charlie", "Yellow")},
        )

    def test_partial_effective_snapshot_is_rejected(self) -> None:
        setup = basic_setup()
        partial = replace(
            setup,
            roster=setup.roster
            + (config.RosterChange(setup.key.league_id, 2, "Alice", "Green"),),
        )

        with self.assertRaises(config.LeagueConfigValidationError) as raised:
            config.validate_league_setup(partial)

        self.assertIn("must cover positions 1-1 exactly", str(raised.exception))

    def test_alias_collision_with_another_driver_is_rejected(self) -> None:
        setup = basic_setup()
        bad_roster = (
            config.RosterChange(setup.key.league_id, 1, "Alice", "Red", ("Bob",)),
            config.RosterChange(setup.key.league_id, 1, "Bob", "Blue"),
        )
        with self.assertRaises(config.LeagueConfigValidationError) as raised:
            config.validate_league_setup(replace(setup, roster=bad_roster))
        self.assertIn("matches another driver", str(raised.exception))

    def test_roster_snapshot_update_is_complete_future_and_digest_bound(self) -> None:
        setup = basic_setup(status="Active")
        tables = config.config_tables_from_setup(setup)
        update = config.RosterSnapshotUpdate(
            setup.key.league_id,
            2,
            (
                config.RosterChange(setup.key.league_id, 2, "Alice", "Green"),
                config.RosterChange(setup.key.league_id, 2, "Charlie", "Yellow"),
            ),
        )
        merged = config.config_tables_with_roster_snapshot(tables, update)

        resolved = config.resolve_roster_snapshot(merged, setup.key.league_id, 2)
        self.assertEqual(
            {(row.driver_name, row.team_name) for row in resolved},
            {("Alice", "Green"), ("Charlie", "Yellow")},
        )
        self.assertEqual(
            config.roster_snapshot_update_digest(tables, update),
            config.roster_snapshot_update_digest(
                tables, replace(update, complete_roster=tuple(reversed(update.complete_roster)))
            ),
        )

        with self.assertRaises(config.LeagueConfigValidationError):
            config.validate_roster_snapshot_update(
                tables, replace(update, effective_from_round=1)
            )

    def test_grid_growth_requires_same_round_scoring_coverage(self) -> None:
        setup = basic_setup(status="Active")
        tables = config.config_tables_from_setup(setup)
        expanded = (
            config.RosterChange(setup.key.league_id, 2, "Alice", "Red"),
            config.RosterChange(setup.key.league_id, 2, "Bob", "Blue"),
            config.RosterChange(setup.key.league_id, 2, "Charlie", "Yellow"),
        )
        without_scoring = config.RosterSnapshotUpdate(
            setup.key.league_id, 2, expanded
        )
        with self.assertRaises(config.LeagueConfigValidationError) as raised:
            config.validate_roster_snapshot_update(tables, without_scoring)
        self.assertIn("positions 1-3", str(raised.exception))

        race_profile = config.ScoringProfile(
            "expanded:R:2", setup.key.league_id, "R", 2, 1, 3
        )
        sprint_profile = config.ScoringProfile(
            "expanded:SR:2", setup.key.league_id, "SR", 2
        )
        with_scoring = config.RosterSnapshotUpdate(
            setup.key.league_id,
            2,
            expanded,
            (race_profile, sprint_profile),
            scoring_points("expanded:R:2", [25, 18, 15])
            + scoring_points("expanded:SR:2", [8, 7, 6]),
        )
        merged = config.config_tables_with_roster_snapshot(tables, with_scoring)
        self.assertEqual(
            config.resolve_scoring_profile(
                merged, setup.key.league_id, "R", 2, 3
            ).points,
            {1: 25.0, 2: 18.0, 3: 15.0},
        )

    def test_completed_or_draft_league_rejects_future_snapshots(self) -> None:
        for status in ("Completed", "Draft"):
            with self.subTest(status=status):
                setup = basic_setup(status=status)
                tables = config.config_tables_from_setup(setup)
                update = config.RosterSnapshotUpdate(
                    setup.key.league_id,
                    2,
                    (
                        config.RosterChange(
                            setup.key.league_id, 2, "Alice", "Green"
                        ),
                        config.RosterChange(
                            setup.key.league_id, 2, "Bob", "Blue"
                        ),
                    ),
                )
                with self.assertRaises(config.LeagueConfigValidationError) as raised:
                    config.validate_roster_snapshot_update(tables, update)
                self.assertIn("only to an Active league", str(raised.exception))


class ResolutionAndCloneTests(unittest.TestCase):
    def test_legacy_fallback_adapters_are_used_only_when_config_is_absent(self) -> None:
        tables = config.empty_config_tables()
        roster = config.resolve_roster_snapshot(
            tables,
            "legacy",
            3,
            lambda _: [
                {"Driver": "Alice", "Team": "Red"},
                {"Driver": "Bob", "Team": "Blue"},
            ],
        )
        scoring = config.resolve_scoring_profile(
            tables,
            "legacy",
            "R",
            3,
            2,
            lambda _event_type, _round, _size: {1: 25, 2: 18},
        )
        self.assertEqual(len(roster), 2)
        self.assertEqual(scoring.points, {1: 25.0, 2: 18.0})
        self.assertEqual(scoring.profile_id, "legacy")

    def test_clone_configured_league_copies_latest_roster_and_scoring(self) -> None:
        source = replace(basic_setup(league_id="source", status="Completed"), key=config.LeagueKey("source", "F1 26", "2026-T02", "Source"))
        changed_source = replace(
            source,
            roster=source.roster
            + (
                config.RosterChange("source", 2, "Alice", "Emerald"),
                config.RosterChange("source", 2, "Charlie", "Gold"),
            ),
        )
        source_tables = config.config_tables_from_setup(changed_source)
        new_key = config.LeagueKey("target", "F1 27", "2027-T01", "Target")
        cloned = config.clone_configured_league(
            source_tables,
            source_league_id="source",
            new_key=new_key,
            calendar=basic_setup(league_id="target").calendar,
        )

        self.assertEqual(cloned.cloned_from_league_id, "source")
        self.assertEqual(
            {(row.driver_name, row.team_name, row.effective_from_round) for row in cloned.roster},
            {("Alice", "Emerald", 1), ("Charlie", "Gold", 1)},
        )
        self.assertEqual({profile.event_type for profile in cloned.scoring_profiles}, {"R", "SR"})
        self.assertTrue(all(profile.league_id == "target" for profile in cloned.scoring_profiles))

    def test_clone_legacy_uses_latest_complete_race_and_supports_first_event(self) -> None:
        standings = pd.DataFrame(
            [
                ["F1 26", "2026-T01", "Old", 1, "R", "A GP", "Alice", "Red", 1, 25],
                ["F1 26", "2026-T01", "Old", 1, "R", "A GP", "Bob", "Blue", 2, 18],
                ["F1 26", "2026-T01", "Old", 2, "R", "B GP", "Alice", "Green", 2, 18],
                ["F1 26", "2026-T01", "Old", 2, "R", "B GP", "Charlie", "Yellow", 1, 25],
            ],
            columns=[
                "Game", "Season", "League Name", "Round", "Type", "GP Name",
                "Driver", "Team", "Finish Pos", "Points",
            ],
        )
        key = config.LeagueKey("new", "F1 27", "2027-T01", "New")
        calendar = (
            config.CalendarRound(1, date(2027, 2, 1), "C GP", "Circuit C"),
        )
        cloned = config.clone_legacy_league(
            standings,
            source_game="F1 26",
            source_season="2026-T01",
            source_league="Old",
            new_key=key,
            calendar=calendar,
        )

        self.assertEqual(
            {(row.driver_name, row.team_name) for row in cloned.roster},
            {("Alice", "Green"), ("Charlie", "Yellow")},
        )
        tables = config.config_tables_from_setup(cloned)
        self.assertEqual(len(config.resolve_roster_snapshot(tables, "new", 1)), 2)
        self.assertEqual(
            config.resolve_scoring_profile(tables, "new", "R", 1, 2).points,
            {1: 25.0, 2: 18.0},
        )


class FastestLapBonusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = config.ResolvedScoringProfile(
            "race",
            "league",
            "R",
            1,
            ((1, 25.0), (2, 18.0), (3, 15.0)),
            1.0,
            2,
        )

    def test_unique_fastest_eligible_driver_receives_bonus(self) -> None:
        award = config.derive_fastest_lap_bonus(
            [
                {"Position": 1, "Driver": "Alice", "Fastest Lap": "1:33.500"},
                {"Position": 2, "Driver": "Bob", "Fastest Lap": "1:33.200"},
                {"Position": 3, "Driver": "Charlie", "Fastest Lap": "1:32.000"},
            ],
            self.profile,
        )
        self.assertEqual(award, config.FastestLapAward("Bob", 2, "1:33.200", 1.0))

    def test_tie_and_missing_eligible_lap_block_assignment(self) -> None:
        tied = [
            {"Position": 1, "Driver": "Alice", "Fastest Lap": "1:33.200"},
            {"Position": 2, "Driver": "Bob", "Fastest Lap": "1:33.200"},
        ]
        with self.assertRaises(config.LeagueConfigResolutionError) as tie_error:
            config.derive_fastest_lap_bonus(tied, self.profile)
        self.assertIn("tied", str(tie_error.exception))

        missing = [
            {"Position": 1, "Driver": "Alice", "Fastest Lap": ""},
            {"Position": 2, "Driver": "Bob", "Fastest Lap": "1:33.200"},
        ]
        with self.assertRaises(config.LeagueConfigResolutionError) as missing_error:
            config.derive_fastest_lap_bonus(missing, self.profile)
        self.assertIn("missing", str(missing_error.exception))

    def test_zero_bonus_does_not_require_lap_data(self) -> None:
        no_bonus = replace(self.profile, fastest_lap_bonus=0)
        self.assertEqual(
            config.derive_fastest_lap_bonus([], no_bonus),
            config.FastestLapAward(None, None, None, 0.0),
        )


if __name__ == "__main__":
    unittest.main()
