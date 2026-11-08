"""The three human drivers' circuit comparisons use published session evidence."""
from datetime import time, timedelta
import json
import unittest

import pandas as pd

from circuit_history import circuit_history


def row(**overrides):
    return {**{"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League",
               "Round": 1, "Type": "R", "GP Name": "São Paulo GP",
               "Driver": "TomasRodri21", "Finish Pos": 1,
               "Fastest Lap": "1:12.500", "IsSeasonFinal": False}, **overrides}


class CircuitHeadToHeadTests(unittest.TestCase):
    def build(self, rows, meta=None):
        return circuit_history(pd.DataFrame(rows), meta=meta)

    def humans(self, rows, meta=None):
        return {item["driver"]: item for item in self.build(rows, meta)[0]["head_to_head"]}

    def test_races_count_once_per_driver_and_sprints_only_supply_lap_records(self):
        rows = [row(), row(Driver="TomasRodri", **{"GP Name": "Brazilian GP"}),
                row(Driver="Polingua", **{"Finish Pos": 2, "Fastest Lap": "1:12.300"}),
                row(Driver="Fatacuida", **{"Finish Pos": 3, "Fastest Lap": "1:12.400"}),
                row(Type="SR", **{"Fastest Lap": "1:11.000"}),
                row(Round=2, **{"Finish Pos": 4, "Fastest Lap": "1:12.100"}),
                row(Round=2, Driver="Fatacuida", **{"Finish Pos": 1, "Fastest Lap": "1:12.000"})]
        humans = self.humans(rows)
        self.assertEqual((humans["TomasRodri21"]["starts"], humans["TomasRodri21"]["wins"],
                          humans["TomasRodri21"]["podiums"]), (2, 1, 1))
        self.assertEqual((humans["TomasRodri21"]["best_lap"], humans["TomasRodri21"]["best_lap_type"]),
                         ("1:11.000", "SR"))
        self.assertEqual((humans["Fatacuida"]["starts"], humans["Fatacuida"]["wins"],
                          humans["Fatacuida"]["podiums"]), (2, 1, 2))
        self.assertEqual(humans["Polingua"]["starts"], 1)
        self.assertEqual([item["driver"] for item in self.build(rows)[0]["head_to_head"]],
                         ["TomasRodri21", "Polingua", "Fatacuida"])

    def test_selected_scope_filters_all_metrics_and_best_lap_provenance(self):
        selected = {"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League"}
        rows = [row(), row(SeasonLabel="2026-T01", **{"Fastest Lap": "1:09.000"}),
                row(Game="F1 24", **{"Fastest Lap": "1:08.000"}),
                row(**{"League Name": "Other", "Fastest Lap": "1:07.000"})]
        current = self.humans(rows, selected)["TomasRodri21"]
        self.assertEqual(current["starts"], 1)
        self.assertEqual(current["wins"], 1)
        self.assertEqual(current["best_lap"], "1:12.500")
        self.assertEqual(current["best_lap_season"], "2026-T02")
        self.assertEqual(current["best_lap_league"], "League")
        self.assertEqual(current["best_lap_game"], "F1 25")
        self.assertEqual(self.humans(rows)["TomasRodri21"]["best_lap"], "1:07.000")

    def test_summaries_qualifying_and_human_like_ai_names_are_excluded(self):
        rows = [row(Driver="Alice"), row(Driver="TomasRodri21 AI", **{"Finish Pos": 2}),
                row(Type="Q", **{"Fastest Lap": "0:59.000"}),
                row(IsSeasonFinal=True, **{"Fastest Lap": "0:58.000"})]
        for human in self.humans(rows).values():
            self.assertFalse(human["has_results"])
            self.assertEqual((human["starts"], human["wins"], human["podiums"]), (0, 0, 0))
            self.assertIsNone(human["best_lap"])

    def test_conflicting_duplicate_classifications_do_not_invent_wins_or_best_laps(self):
        rows = [row(), row(Driver="TomasRodri", **{"Finish Pos": 2})]
        human = self.humans(rows)["TomasRodri21"]
        self.assertEqual((human["starts"], human["wins"], human["podiums"]), (1, 0, 0))
        self.assertIsNone(human["best_lap"])
        self.assertEqual(human["unresolved_results"], 1)
        self.assertEqual(self.build(rows)[0]["winners"], [])
        self.assertEqual(self.build(rows)[0]["unresolved_events"], 1)

    def test_conflicting_finishing_rank_between_drivers_is_not_two_wins(self):
        rows = [row(), row(Driver="Polingua")]
        humans = self.humans(rows)
        self.assertEqual(humans["TomasRodri21"]["wins"], 0)
        self.assertEqual(humans["Polingua"]["wins"], 0)
        self.assertEqual(humans["TomasRodri21"]["unresolved_results"], 1)
        self.assertEqual(self.build(rows)[0]["winners"], [])

    def test_disputed_first_place_owner_cannot_promote_another_first_place_claim(self):
        rows = [row(), row(Driver="TomasRodri", **{"Finish Pos": 2}),
                row(Driver="Polingua")]
        card = self.build(rows)[0]
        self.assertEqual(card["winners"], [])
        self.assertEqual(card["race_count"], 0)
        self.assertEqual(card["unresolved_events"], 1)
        humans = {human["driver"]: human for human in card["head_to_head"]}
        self.assertEqual(humans["TomasRodri21"]["wins"], 0)
        self.assertEqual(humans["Polingua"]["wins"], 0)
        self.assertEqual(humans["Polingua"]["unresolved_results"], 1)
        self.assertEqual(card, self.build(list(reversed(rows)))[0])

    def test_conflicting_duplicate_laps_preserve_classification_but_not_an_invented_pb(self):
        human = self.humans([row(), row(**{"Fastest Lap": "1:10.000"})])["TomasRodri21"]
        self.assertEqual((human["starts"], human["wins"]), (1, 1))
        self.assertIsNone(human["best_lap"])
        self.assertEqual(human["unresolved_results"], 1)

    def test_lap_formats_use_existing_parser_and_never_fall_back_to_race_time(self):
        for lap in (time(0, 1, 12, 500000), timedelta(seconds=72.5), 72.5 / 86400,
                    "00:01:12.500", "1:12,500"):
            with self.subTest(lap=lap):
                self.assertEqual(self.humans([row(**{"Fastest Lap": lap})])["TomasRodri21"]["best_lap"],
                                 "1:12.500")
        for lap in (None, "", "DNF", "1:99.999", True):
            with self.subTest(lap=lap):
                human = self.humans([row(**{"Fastest Lap": lap, "Time": "1:00.000"})])["TomasRodri21"]
                self.assertTrue(human["has_results"])
                self.assertIsNone(human["best_lap"])

    def test_sprint_only_driver_has_no_main_race_wins_or_appearances(self):
        card = self.build([row(Type="SR", Driver="Fatacuida")])[0]
        human = next(item for item in card["head_to_head"] if item["driver"] == "Fatacuida")
        self.assertTrue(human["has_results"])
        self.assertEqual((human["starts"], human["wins"], human["podiums"]), (0, 0, 0))
        self.assertEqual(human["best_lap_type"], "SR")
        self.assertEqual(card["race_count"], 0)

    def test_explicit_venues_stay_separate_and_reordering_cannot_change_comparison(self):
        rows = [row(**{"GP Name": "Spanish GP", "Circuit": "Madring"}),
                row(Round=2, **{"GP Name": "Spanish GP", "Circuit": "Barcelona", "Fastest Lap": "1:17.000"}),
                row(SeasonLabel="2025-T01", **{"GP Name": "Spanish GP", "Circuit": "Barcelona",
                                            "Fastest Lap": "1:17.000"})]
        cards = self.build(rows)
        self.assertEqual(cards, self.build(list(reversed(rows))))
        self.assertEqual(len(cards), 2)
        by_key = {card["key"]: card for card in cards}
        self.assertEqual(by_key["madring"]["head_to_head"][0]["starts"], 1)
        self.assertEqual(by_key["circuitdebarcelonacatalunya"]["head_to_head"][0]["starts"], 2)
        self.assertEqual(by_key["circuitdebarcelonacatalunya"]["head_to_head"][0]["best_lap_season"], "2025-T01")
        json.dumps(cards, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
