"""Venue aliases, complete race provenance and honest missing dates."""
from datetime import date
import json
import unittest

import pandas as pd

from circuit_history import circuit_history


def result(**overrides):
    return {**{"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League",
               "Round": 1, "Type": "R", "GP Name": "São Paulo GP", "Driver": "Alice",
               "Finish Pos": 1, "IsSeasonFinal": False}, **overrides}


def event(**overrides):
    return {**{"League Name": "League", "Round": 1, "GP Name": "São Paulo GP",
               "Circuit": "Autódromo José Carlos Pace (Interlagos)", "Date": pd.Timestamp("2026-11-08")}, **overrides}


class CircuitHistoryTests(unittest.TestCase):
    def build(self, rows, calendar=()):
        return circuit_history(pd.DataFrame(rows), pd.DataFrame(calendar))

    def test_brazil_aliases_share_one_history_and_race_only_counts(self):
        rows = [result(Driver="Fatacuida"),
                result(SeasonLabel="2026-T01", **{"League Name": "Older", "GP Name": "Brazilian GP", "Driver": "Polingua"}),
                result(SeasonLabel="2023-T01", Game="F1 23", **{"League Name": "ARF", "GP Name": "Brazil GP", "Driver": "Polingua"}),
                result(Type="SR", Driver="Sprint Winner"),
                result(Type="Q", Driver="Qualifier"),
                result(IsSeasonFinal=True, Driver="Season Champion")]
        cards = self.build(rows, [event()])
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["gp_name"], "São Paulo GP")
        self.assertEqual(card["race_count"], 3)
        self.assertEqual(card["leaders"], [{"driver": "Polingua", "wins": 2}, {"driver": "Fatacuida", "wins": 1}])
        self.assertEqual([row["driver"] for row in card["winners"]], ["Fatacuida", "Polingua", "Polingua"])
        self.assertEqual(card["winners"][0]["date"], "2026-11-08")
        self.assertIsNone(card["winners"][1]["date"])
        self.assertEqual(card["winners"][2]["league"], "ARF")
        self.assertEqual(card["winners"][2]["game"], "F1 23")

    def test_legacy_calendar_never_borrows_date_from_reused_league_name(self):
        rows = [result(), result(SeasonLabel="2025-T01", Driver="Bob")]
        card = self.build(rows, [event()])[0]
        self.assertTrue(all(row["date"] is None for row in card["winners"]))
        card = self.build(rows, [event(Game="F1 25", Season="2026-T02")])[0]
        self.assertEqual([row["date"] for row in card["winners"]], ["2026-11-08", None])

    def test_league_filter_isolates_game_season_and_league_and_recounts_wins(self):
        selected = {"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League"}
        rows = [result(Driver="Alice"), result(Round=2, Driver="Bob"),
                result(SeasonLabel="2026-T01", Driver="Old Winner"),
                result(Game="F1 24", Driver="Other Game"),
                result(Driver="Other League", **{"League Name": "Other"}),
                result(SeasonLabel="2026-T01", **{"GP Name": "Canadian GP"}),
                result(Type="SR", Driver="Sprint Winner")]
        original = pd.DataFrame(rows)
        cards = circuit_history(original, pd.DataFrame([event()]), meta=selected)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["race_count"], 2)
        self.assertEqual({row["driver"] for row in cards[0]["winners"]}, {"Alice", "Bob"})
        self.assertEqual(cards[0]["leaders"], [{"driver": "Alice", "wins": 1}, {"driver": "Bob", "wins": 1}])
        self.assertEqual(original.to_dict("records"), rows)
        self.assertEqual(circuit_history(original, meta={**selected, "League Name": "Unknown"}), [])

    def test_filter_does_not_make_an_ambiguous_legacy_calendar_date_look_unique(self):
        rows = pd.DataFrame([result(), result(SeasonLabel="2025-T01", Driver="Bob")])
        current = {"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League"}
        card = circuit_history(rows, pd.DataFrame([event()]), meta=current)[0]
        self.assertIsNone(card["winners"][0]["date"])
        card = circuit_history(rows, pd.DataFrame([event(Game="F1 25", Season="2026-T02")]), meta=current)[0]
        self.assertEqual(card["winners"][0]["date"], "2026-11-08")

    def test_filter_preserves_exact_catalog_identity_for_case_and_spacing_variants(self):
        selected = {"Game": "F1 25", "SeasonLabel": "2026-T02", "League Name": "League"}
        rows = pd.DataFrame([result(Driver="Selected Winner"),
                             result(Driver="Different Case", **{"League Name": "LEAGUE"}),
                             result(Driver="Different Game", Game="f1 25"),
                             result(Driver="Different Season", SeasonLabel="2026-t02"),
                             result(Driver="Different Spaces", **{"League Name": " League "})])
        card = circuit_history(rows, meta=selected)[0]
        self.assertEqual(card['leaders'], [{'driver': 'Selected Winner', 'wins': 1}])

    def test_league_id_disambiguates_calendar_and_rejects_other_league_id(self):
        rows = [result(**{"League ID": "current"}), result(SeasonLabel="2025-T01", Driver="Bob", **{"League ID": "old"})]
        card = self.build(rows, [event(**{"League ID": "current"})])[0]
        self.assertEqual([row["date"] for row in card["winners"]], ["2026-11-08", None])
        card = self.build(rows, [event(**{"League ID": "unrelated"})])[0]
        self.assertTrue(all(row["date"] is None for row in card["winners"]))

    def test_direct_result_date_is_used_without_calendar_and_invalid_dates_stay_missing(self):
        card = self.build([result(Date=date(2026, 11, 8))])[0]
        self.assertEqual(card["winners"][0]["date"], "2026-11-08")
        for missing in (None, pd.NaT, "", "not a date", 46334):
            with self.subTest(missing=missing):
                self.assertIsNone(self.build([result(Date=missing)])[0]["winners"][0]["date"])

    def test_ambiguous_calendar_or_wrong_gp_does_not_supply_a_date(self):
        for calendar in ([event(), event(Date=pd.Timestamp("2026-11-09"))],
                         [event(**{"GP Name": "Canadian GP", "Circuit": "Circuit Gilles-Villeneuve"})]):
            with self.subTest(calendar=calendar):
                self.assertIsNone(self.build([result()], calendar)[0]["winners"][0]["date"])

    def test_ambiguous_numeric_or_incomplete_date_text_is_not_guessed(self):
        for value in ("03/04/2026", "11/08/2026", "November 2026", "2026"):
            with self.subTest(value=value):
                self.assertIsNone(self.build([result(Date=value)])[0]["winners"][0]["date"])
        for value in ("2026-11-08", "8 November 2026", "Nov 8, 2026"):
            with self.subTest(value=value):
                self.assertEqual(self.build([result(Date=value)])[0]["winners"][0]["date"], "2026-11-08")
        card = self.build([result(Date="03/04/2026")], [event()])[0]
        self.assertEqual(card["winners"][0]["date"], "2026-11-08")

    def test_explicit_madrid_and_barcelona_are_separate_and_unknown_spanish_is_not_guessed(self):
        cards = self.build([
            result(**{"GP Name": "Spanish GP", "Circuit": "Madring"}),
            result(Round=2, Driver="Bob", **{"GP Name": "Spanish GP", "Circuit": "Circuit de Barcelona-Catalunya"}),
            result(Round=3, Driver="Charlie", **{"GP Name": "Spanish GP"}),
        ])
        self.assertEqual(len(cards), 3)
        mapped = {card["key"]: card for card in cards}
        self.assertEqual(mapped["madring"]["winners"][0]["driver"], "Alice")
        self.assertEqual(mapped["circuitdebarcelonacatalunya"]["winners"][0]["driver"], "Bob")
        self.assertEqual(mapped["unrecordedspanishgp"]["circuit_name"], "")
        self.assertFalse(mapped["unrecordedspanishgp"]["venue_recorded"])

    def test_calendar_explicit_venue_can_resolve_generic_spanish_gp(self):
        cards = self.build([result(**{"GP Name": "Spanish GP"})],
                           [event(**{"GP Name": "Spanish GP", "Circuit": "Circuit de Barcelona-Catalunya"})])
        self.assertEqual(cards[0]["gp_name"], "Barcelona-Catalunya GP")
        self.assertEqual(cards[0]["winners"][0]["date"], "2026-11-08")

    def test_duplicate_alias_row_counts_once_but_conflicting_winners_are_not_invented(self):
        a = result()
        card = self.build([a, {**a, "GP Name": "Brazilian GP"}])[0]
        self.assertEqual(card["race_count"], 1)
        card = self.build([a, result(Driver="Bob")])[0]
        self.assertEqual(card["winners"], [])
        self.assertEqual(card["unresolved_events"], 1)

    def test_missing_winner_and_sprint_only_circuits_remain_in_layout_catalog(self):
        cards = self.build([result(**{"Finish Pos": 2}), result(Type="SR", **{"GP Name": "Canadian GP"})])
        self.assertEqual(len(cards), 2)
        self.assertTrue(all(card["winners"] == [] for card in cards))
        self.assertTrue(all(card["race_count"] == 0 for card in cards))

    def test_summary_only_and_invalid_inputs_do_not_create_a_gp_history(self):
        self.assertEqual(self.build([result(IsSeasonFinal=True)]), [])
        self.assertEqual(circuit_history(pd.DataFrame()), [])
        self.assertEqual(circuit_history(None), [])
        self.assertEqual(circuit_history(pd.DataFrame([{"GP Name": "São Paulo GP"}])), [])

    def test_result_order_cannot_change_history_and_models_are_json_safe(self):
        rows = [result(Driver="Alice"), result(Round=2, Driver="Bob", **{"GP Name": "Brazilian GP"}),
                result(Round=2, Driver="Bob", **{"GP Name": "São Paulo GP"})]
        calendar = [event(), event(Round=2, Date=pd.Timestamp("2026-11-15"))]
        expected = self.build(rows, calendar)
        self.assertEqual(self.build(list(reversed(rows)), list(reversed(calendar))), expected)
        json.dumps(expected, allow_nan=False)

    def test_unknown_circuit_preserves_explicit_name_in_either_row_order(self):
        inferred = result(**{"GP Name": "Custom Course"})
        explicit = result(**{"GP Name": "Custom Course", "Circuit": "Custom Course"})
        forward = self.build([inferred, explicit])
        self.assertEqual(forward, self.build([explicit, inferred]))
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward[0]["circuit_name"], "Custom Course")
        self.assertTrue(forward[0]["venue_recorded"])
        self.assertEqual(forward[0]["race_count"], 1)

    def test_known_venue_metadata_promotes_unknown_gp_label_in_either_order(self):
        venue_as_gp = result(**{"GP Name": "Autódromo José Carlos Pace"})
        canonical_gp = result(**{"GP Name": "São Paulo GP"})
        forward = self.build([venue_as_gp, canonical_gp], [event()])
        self.assertEqual(forward, self.build([canonical_gp, venue_as_gp], [event()]))
        self.assertEqual(len(forward), 1)
        card = forward[0]
        self.assertEqual(card["gp_name"], "São Paulo GP")
        self.assertEqual(card["circuit_name"], "Autódromo José Carlos Pace")
        self.assertTrue(card["venue_recorded"])
        self.assertEqual(card["race_count"], 1)
        self.assertEqual(card["winners"][0]["date"], "2026-11-08")


if __name__ == "__main__":
    unittest.main()
