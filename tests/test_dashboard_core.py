from __future__ import annotations

import io
import unittest

import pandas as pd

import dashboard_core as core


class DashboardCoreTests(unittest.TestCase):
    def normalized_results(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                ["F1 25", "2026-T01", "League", 1, "R", "Bahrain GP", "Alice", "Red", 1, 25, "2026-T01", 2026, False],
                ["F1 25", "2026-T01", "League", 1, "SR", "Bahrain GP", "Alice", "Red", 2, 8, "2026-T01", 2026, False],
                ["F1 25", "2026-T01", "League", 1, "R", "Bahrain GP", "Bob", "Blue", 2, 18, "2026-T01", 2026, False],
                ["F1 25", "2026-T01", "League", 2, "R", "Monaco GP", "Alice", "Red", 2, 18, "2026-T01", 2026, False],
                ["F1 25", "2026-T01", "League", 2, "R", "Monaco GP", "Bob", "Blue", 1, 25, "2026-T01", 2026, False],
            ],
            columns=[
                "Game", "Season", "League Name", "Round", "Type", "GP Name", "Driver", "Team",
                "Finish Pos", "Points", "SeasonLabel", "SeasonNum", "IsSeasonFinal",
            ],
        )

    def workbook_bytes(self, leagues: pd.DataFrame, calendar: pd.DataFrame | None = None) -> io.BytesIO:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            leagues.to_excel(writer, sheet_name="Leagues", index=False)
            if calendar is not None:
                calendar.to_excel(writer, sheet_name="Calendar", index=False)
        buffer.seek(0)
        return buffer

    def test_standings_include_sprint_points_but_race_only_stats(self):
        standings = core.standings_table(self.normalized_results(), "Drivers")
        alice = standings.loc[standings["Driver"] == "Alice"].iloc[0]
        self.assertEqual(alice["Points"], 51)
        self.assertEqual(alice["Races"], 2)
        self.assertEqual(alice["Wins"], 1)
        self.assertEqual(alice["AvgFinish"], 1.5)

    def test_standings_tiebreak_uses_wins_then_podiums(self):
        data = self.normalized_results()
        data.loc[data["Driver"] == "Alice", "Points"] = [10, 0, 15]
        data.loc[data["Driver"] == "Bob", "Points"] = [12, 13]
        standings = core.standings_table(data, "Drivers")
        self.assertEqual(standings.iloc[0]["Driver"], "Alice")

    def test_effective_rows_prevent_double_counting_season_totals(self):
        data = self.normalized_results()
        final = data.iloc[[0]].copy()
        final["Round"] = 999
        final["GP Name"] = "Season Final"
        final["Points"] = 100
        final["IsSeasonFinal"] = True
        effective = core.effective_rows(pd.concat([data, final], ignore_index=True))
        self.assertFalse(effective["IsSeasonFinal"].any())
        self.assertEqual(len(effective), len(data))

    def test_titles_do_not_add_season_total_to_race_points(self):
        data = self.normalized_results()
        finals = pd.DataFrame(
            [
                ["F1 25", "2026-T01", "League", 999, "R", "Season Final", "Alice", "Red", 2, 43, "2026-T01", 2026, True],
                ["F1 25", "2026-T01", "League", 999, "R", "Season Final", "Bob", "Blue", 1, 44, "2026-T01", 2026, True],
            ],
            columns=data.columns,
        )
        _, champions = core.titles_count(pd.concat([data, finals], ignore_index=True), "Driver")
        self.assertEqual(champions.iloc[0]["Champion"], "Alice")
        self.assertEqual(champions.iloc[0]["Points"], 51)

    def test_workbook_validation_reports_missing_required_column(self):
        leagues = pd.DataFrame({"Game": ["F1 25"]})
        with self.assertRaisesRegex(core.WorkbookValidationError, "missing columns"):
            core.validate_workbook(self.workbook_bytes(leagues))

    def test_workbook_validation_warns_when_calendar_is_absent(self):
        leagues = pd.DataFrame(
            {
                "Game": ["F1 25"],
                "Season": ["2026-T01"],
                "League Name": ["League"],
                "Round": [1],
                "GP Name": ["Bahrain GP"],
                "Driver": ["Alice"],
                "Team": ["Red"],
                "Finish Pos": [1],
                "Points": [25],
            }
        )
        warnings = core.validate_workbook(self.workbook_bytes(leagues))
        self.assertEqual(len(warnings), 1)
        self.assertIn("Calendar", warnings[0])

    def test_loader_normalizes_season_final_and_event_type(self):
        leagues = pd.DataFrame(
            [["F1 25", "2026-T01", "League", "All", "X", "All", "Alice", "Red", 1, 100]],
            columns=["Game", "Season", "League Name", "Round", "Type", "GP Name", "Driver", "Team", "Finish Pos", "Points"],
        )
        loaded = core.load_standings_data(self.workbook_bytes(leagues))
        self.assertTrue(bool(loaded.iloc[0]["IsSeasonFinal"]))
        self.assertEqual(loaded.iloc[0]["GP Name"], "Season Final")
        self.assertEqual(loaded.iloc[0]["Type"], "R")

    def test_cumulative_points_progress_by_round(self):
        _, long = core.cumulative_points_wide(self.normalized_results(), "Driver", all_time=False)
        alice = long[long["Driver"] == "Alice"].sort_values("EventIdx")
        self.assertEqual(alice["CumPoints"].tolist(), [33, 51])


if __name__ == "__main__":
    unittest.main()