"""Search and sorting follow venue identity without mutating gallery data."""
from copy import deepcopy
import unittest

from circuit_explorer import country_metadata, filter_circuits


def card(gp, venue="", key=None, races=0, unresolved=0, **extra):
    return {"key": key or gp, "gp_name": gp, "circuit_name": venue,
            "race_count": races, "unresolved_events": unresolved,
            **country_metadata(gp, venue), **extra}


class CircuitSearchTests(unittest.TestCase):
    def setUp(self):
        self.cards = [
            card("São Paulo GP", "Autódromo José Carlos Pace", races=3),
            card("United States GP", "Circuit of the Americas", races=4),
            card("Portuguese GP", "Algarve International Circuit", races=2),
            card("Japanese GP", "Suzuka International Racing Course", races=2),
            card("Spanish GP", "Madring", races=1),
            card("Barcelona-Catalunya GP", "Circuit de Barcelona-Catalunya", races=2),
        ]

    def find(self, query):
        return [row["gp_name"] for row in filter_circuits(self.cards, query)]

    def test_search_supports_accent_case_venue_aliases_and_both_country_languages(self):
        for query in ("SAO PAULO", "José Carlos", "Interlagos", "Brazil", "Brasil", "Brazilian"):
            self.assertEqual(self.find(query), ["São Paulo GP"])
        for query in ("COTA", "Austin", "USA", "Estados Unidos", "United States"):
            self.assertEqual(self.find(query), ["United States GP"])
        self.assertEqual(self.find("Portimao"), ["Portuguese GP"])
        self.assertEqual(self.find("Japao"), ["Japanese GP"])
        self.assertEqual(self.find("Portugal Algarve"), ["Portuguese GP"])
        self.assertEqual(self.find("Japan Brazil"), [])
        self.assertEqual(self.find("<script>"), [])

    def test_spanish_venues_are_distinct_and_unknown_venue_does_not_inherit_madrid(self):
        self.assertEqual(self.find("Madrid"), ["Spanish GP"])
        self.assertEqual(self.find("Catalunya"), ["Barcelona-Catalunya GP"])
        self.assertEqual(set(self.find("Spain")), {"Spanish GP", "Barcelona-Catalunya GP"})
        unrecorded = card("Spanish GP", key="unknown-spanish", venue_recorded=False)
        self.assertEqual(filter_circuits([unrecorded], "Madrid"), [])
        self.assertEqual(filter_circuits([unrecorded], "Spain"), [unrecorded])

    def test_country_metadata_follows_explicit_venue_and_does_not_guess_unknowns(self):
        self.assertEqual(country_metadata("Brazilian GP")["country_code"], "br")
        self.assertEqual(country_metadata("Anything", "Suzuka")["country_en"], "Japan")
        self.assertEqual(country_metadata("Spanish GP", "Barcelona")["country_pt"], "Espanha")
        self.assertEqual(country_metadata("Custom Course", "Custom Course"),
                         {"country_code": "", "country_en": "", "country_pt": ""})
        self.assertEqual(country_metadata("Japanese GP", "Custom Course")["country_code"], "")

    def test_name_country_and_race_sorts_are_stable_and_do_not_mutate(self):
        original = deepcopy(self.cards)
        by_name = filter_circuits(self.cards, sort="name")
        self.assertEqual([row["gp_name"] for row in by_name],
                         ["Barcelona-Catalunya GP", "Japanese GP", "Portuguese GP",
                          "São Paulo GP", "Spanish GP", "United States GP"])
        by_country = filter_circuits(self.cards, sort="country")
        self.assertEqual([row["country_en"] for row in by_country],
                         ["Brazil", "Japan", "Portugal", "Spain", "Spain", "United States"])
        by_races = filter_circuits(self.cards, sort="races")
        self.assertEqual([row["race_count"] for row in by_races], [4, 3, 2, 2, 2, 1])
        self.assertEqual(self.cards, original)
        self.assertIsNot(by_name, self.cards)
        self.assertEqual(filter_circuits(list(reversed(self.cards)), sort="races"), by_races)
        self.assertEqual(filter_circuits(self.cards, sort="invalid"), by_name)

    def test_sort_uses_portuguese_labels_and_unknown_countries_sort_last(self):
        rows = [card("French GP", "Circuit Paul Ricard"),
                card("Japanese GP", "Suzuka International Racing Course"),
                card("Custom GP", "Custom Circuit")]
        self.assertEqual([row["gp_name"] for row in filter_circuits(rows, sort="name", lang="pt")],
                         ["Custom GP", "French GP", "Japanese GP"])
        self.assertEqual([row["gp_name"] for row in filter_circuits(rows, sort="country", lang="pt")],
                         ["French GP", "Japanese GP", "Custom GP"])

    def test_races_sort_counts_unresolved_main_events_and_no_sprint_wins(self):
        rows = [card("Japanese GP", races=1), card("São Paulo GP", races=0, unresolved=2),
                card("Canadian GP", races=0)]  # A Sprint-only card has no main-race events.
        self.assertEqual([row["gp_name"] for row in filter_circuits(rows, sort="races")],
                         ["São Paulo GP", "Japanese GP", "Canadian GP"])
        self.assertEqual(filter_circuits([], "anything"), [])


if __name__ == "__main__":
    unittest.main()
