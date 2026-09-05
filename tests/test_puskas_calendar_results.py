import unittest

import pandas as pd

import puskas_html


class CalendarRaceStandingsTests(unittest.TestCase):
    def setUp(self):
        self.meta = {
            "Game": "F1 26",
            "SeasonLabel": "2026-T02",
            "League Name": "Puskas League",
        }

    def _row(self, **overrides):
        row = {
            "Game": "F1 26",
            "SeasonLabel": "2026-T02",
            "League Name": "Puskas League",
            "Round": 5,
            "Type": "R",
            "GP Name": "Australian GP",
            "Driver": "Alice",
            "Team": "Ferrari",
            "Finish Pos": 1,
            "Points": 25,
            "Time": "1:20:01.123",
            "Fastest Lap": "1:20.456",
            "IsSeasonFinal": False,
        }
        row.update(overrides)
        return row

    def test_selects_only_main_race_from_exact_dashboard_identity(self):
        results = pd.DataFrame(
            [
                self._row(),
                self._row(Type="SR", Driver="Sprint Driver", **{"Finish Pos": 2}),
                self._row(SeasonLabel="2026-T01", Driver="Old Season"),
                self._row(**{"League Name": "Other League", "Driver": "Other League"}),
                self._row(Game="F1 25", Driver="Other Game"),
                self._row(Round=4, Driver="Other Round"),
                self._row(**{"GP Name": "British GP", "Driver": "Other GP"}),
                self._row(IsSeasonFinal=True, Driver="Season Total"),
            ]
        )

        selected = puskas_html._calendar_race_standings(
            results, 5.0, "Australian GP", self.meta
        )

        self.assertEqual(selected["Driver"].tolist(), ["Alice"])
        self.assertEqual(selected["Type"].tolist(), ["R"])

    def test_fails_closed_for_duplicate_driver_or_finishing_position(self):
        duplicate_driver = pd.DataFrame(
            [self._row(), self._row(Team="McLaren", **{"Finish Pos": 2})]
        )
        duplicate_position = pd.DataFrame(
            [self._row(), self._row(Driver="Bob", **{"Finish Pos": 1})]
        )

        self.assertTrue(
            puskas_html._calendar_race_standings(
                duplicate_driver, 5, "Australian GP", self.meta
            ).empty
        )
        self.assertTrue(
            puskas_html._calendar_race_standings(
                duplicate_position, 5, "Australian GP", self.meta
            ).empty
        )

    def test_fails_closed_for_missing_non_integer_or_non_positive_position(self):
        for invalid_position in (None, "not-a-rank", 0, -1, 1.5):
            with self.subTest(position=invalid_position):
                rows = pd.DataFrame([self._row(**{"Finish Pos": invalid_position})])
                self.assertTrue(
                    puskas_html._calendar_race_standings(
                        rows, 5, "Australian GP", self.meta
                    ).empty
                )

    def test_managed_calendar_uses_exact_championship_identity(self):
        calendar = pd.DataFrame(
            [
                {
                    "League ID": "old-id",
                    "Game": "F1 25",
                    "Season": "2025-T02",
                    "League Name": "Puskas League",
                    "Round": 1,
                    "GP Name": "Old GP",
                },
                {
                    "League ID": "current-id",
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Puskas League",
                    "Round": 5,
                    "GP Name": "Australian GP",
                },
            ]
        )

        selected = puskas_html.get_calendar_for_league(calendar, self.meta)

        self.assertEqual(selected["League ID"].tolist(), ["current-id"])

    def test_calendar_prefers_explicit_league_id_and_fails_closed_on_ambiguity(self):
        calendar = pd.DataFrame(
            [
                {
                    "League ID": "one",
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Puskas League",
                },
                {
                    "League ID": "two",
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Puskas League",
                },
            ]
        )

        explicit = puskas_html.get_calendar_for_league(
            calendar, {**self.meta, "League ID": "two"}
        )
        ambiguous = puskas_html.get_calendar_for_league(calendar, self.meta)

        self.assertEqual(explicit["League ID"].tolist(), ["two"])
        self.assertTrue(ambiguous.empty)

    def test_managed_calendar_rejects_mixed_blank_and_nonblank_league_ids(self):
        calendar = pd.DataFrame(
            [
                {
                    "League ID": "current-id",
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Puskas League",
                    "Round": 1,
                },
                {
                    "League ID": "",
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Puskas League",
                    "Round": 2,
                },
            ]
        )

        selected = puskas_html.get_calendar_for_league(calendar, self.meta)

        self.assertTrue(selected.empty)

    def test_legacy_calendar_requires_exact_league_name(self):
        calendar = pd.DataFrame(
            [
                {"League Name": "Puskas League", "Round": 5},
                {"League Name": "2026-T02", "Round": 99},
            ]
        )

        selected = puskas_html.get_calendar_for_league(calendar, self.meta)
        fuzzy = puskas_html.get_calendar_for_league(
            calendar, {**self.meta, "League Name": "Different 2026-T02 League"}
        )

        self.assertEqual(selected["Round"].tolist(), [5])
        self.assertTrue(fuzzy.empty)

    def test_legacy_reused_league_name_with_duplicate_rounds_fails_closed(self):
        calendar = pd.DataFrame(
            [
                {"League Name": "Puskas League", "Round": 1, "GP Name": "Old GP"},
                {
                    "League Name": "Puskas League",
                    "Round": 1,
                    "GP Name": "Current GP",
                },
            ]
        )

        selected = puskas_html.get_calendar_for_league(calendar, self.meta)

        self.assertTrue(selected.empty)

    def test_popup_escapes_workbook_values_and_localizes_heading(self):
        rows = pd.DataFrame(
            [
                self._row(
                    Driver='<script>alert("driver")</script>',
                    Time='<img src=x onerror="alert(1)">',
                    **{"Fastest Lap": "1:20.456&"},
                )
            ]
        )

        rendered = puskas_html._calendar_standings_popup(
            rows,
            gp_name='<svg onload="alert(2)"> GP',
            popup_id="calendar-race-standings-0",
            lang="pt",
        )

        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("<svg onload", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", rendered)
        self.assertIn("&lt;svg onload=&quot;alert(2)&quot;&gt;", rendered)
        self.assertIn("Classificação da corrida", rendered)
        self.assertIn('role="group"', rendered)
        self.assertIn('role="region" tabindex="0"', rendered)
        self.assertIn('aria-label="Ver classificação da corrida de', rendered)

    def test_popup_keeps_all_twenty_two_classified_drivers_in_position_order(self):
        rows = pd.DataFrame(
            [
                self._row(
                    Driver=f"Driver {position:02d}",
                    **{
                        "Finish Pos": position,
                        "Points": max(26 - position, 0),
                        "Time": "1:20:01.123" if position == 1 else f"+{position}.000",
                    },
                )
                for position in reversed(range(1, 23))
            ]
        )

        selected = puskas_html._calendar_race_standings(
            rows, 5, "Australian GP", self.meta
        )
        rendered = puskas_html._calendar_standings_popup(
            selected,
            gp_name="Australian GP",
            popup_id="calendar-race-standings-0",
            lang="en",
        )

        self.assertEqual(len(selected), 22)
        self.assertEqual(selected["Finish Pos"].tolist(), list(range(1, 23)))
        self.assertEqual(rendered.count('class="p-cal-popup-row">'), 22)
        self.assertIn("max-height: 18rem", "\n".join(
            value
            for value in puskas_html.render_puskas_dashboard.__code__.co_consts
            if isinstance(value, str)
        ))

    def test_calendar_trigger_is_a_native_accessible_disclosure_with_dismissal(self):
        source = puskas_html.render_puskas_dashboard.__code__.co_consts
        joined_source = "\n".join(value for value in source if isinstance(value, str))

        self.assertIn('<details class="p-cal-event">', joined_source)
        self.assertIn('<summary class="p-cal-track p-cal-track-trigger"', joined_source)
        self.assertIn("event.key === 'Escape'", joined_source)
        self.assertIn("event.target.closest('.p-cal-event')", joined_source)
        self.assertIn("item.addEventListener('toggle'", joined_source)


if __name__ == "__main__":
    unittest.main()
