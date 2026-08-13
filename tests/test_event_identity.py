from __future__ import annotations

import unittest

import pandas as pd

import race_workbook as workbook


class EventIdentityTests(unittest.TestCase):
    def test_same_championship_round_and_type_is_duplicate_even_if_gp_name_differs(self):
        data = pd.DataFrame(
            [
                {
                    "Game": "F1 26",
                    "SeasonLabel": "2026-T01",
                    "League Name": "Family",
                    "Round": 4,
                    "Type": "R",
                    "GP Name": "Belgian GP",
                }
            ]
        )
        invented = workbook.RaceMetadata(
            game="F1 26",
            season="2026-T01",
            league="Family",
            round_number=4,
            event_type="R",
            gp_name="Invented GP",
        )
        self.assertTrue(workbook.event_already_exists(data, invented))

    def test_race_and_sprint_in_same_round_remain_distinct(self):
        data = pd.DataFrame(
            [
                {
                    "Game": "F1 26",
                    "SeasonLabel": "2026-T01",
                    "League Name": "Family",
                    "Round": 4,
                    "Type": "R",
                    "GP Name": "Belgian GP",
                }
            ]
        )
        sprint = workbook.RaceMetadata("F1 26", "2026-T01", "Family", 4, "SR", "Belgian GP")
        self.assertFalse(workbook.event_already_exists(data, sprint))

    def test_calendar_identity_requires_one_matching_championship(self):
        unique = pd.DataFrame(
            [{"Game": "F1 26", "SeasonLabel": "2026-T01", "League Name": "Family"}]
        )
        metadata = workbook.RaceMetadata("F1 26", "2026-T01", "Family", 4, "R", "Belgian GP")
        self.assertTrue(workbook._calendar_identity_is_unambiguous(unique, metadata))

        reused = pd.concat(
            [
                unique,
                pd.DataFrame(
                    [{"Game": "F1 25", "SeasonLabel": "2025-T01", "League Name": "Family"}]
                ),
            ],
            ignore_index=True,
        )
        self.assertFalse(workbook._calendar_identity_is_unambiguous(reused, metadata))


if __name__ == "__main__":
    unittest.main()
