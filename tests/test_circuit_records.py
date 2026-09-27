"""Records must follow the venue without confusing game and real-world timing."""
from pathlib import Path
from datetime import time, timedelta
import unittest

import pandas as pd

import dashboard_core as core
from circuit_records import CIRCUIT_RECORDS, get_circuit_record, league_lap_records, circuit_key
from puskas_html import _next_race_circuit_details, render_puskas_dashboard, circuit_lap_records_html


class CircuitRecordTests(unittest.TestCase):
    def test_explicit_venue_disambiguates_spanish_grands_prix(self):
        barcelona = get_circuit_record("Spanish GP", "Circuit de Barcelona-Catalunya")
        madrid = get_circuit_record("Spanish GP", "Madring")
        self.assertEqual(barcelona.circuit, "Circuit de Barcelona-Catalunya")
        self.assertEqual(madrid.circuit, "Madring")
        self.assertNotEqual(barcelona.lap_time, madrid.lap_time)
        self.assertIsNone(get_circuit_record("Spanish GP", "Jarama"))

    def test_circuit_aliases_and_blank_calendar_venue(self):
        self.assertEqual(get_circuit_record("Mexico GP"), get_circuit_record("", "Autodromo Hermanos Rodriguez"))
        self.assertEqual(get_circuit_record("Canadian GP"), get_circuit_record("", "Circuit Gilles Villeneuve"))
        for missing in (None, pd.NA, float("nan"), ""):
            name, record = _next_race_circuit_details("Azerbaijan GP", missing, "en")
            self.assertIn("Baku City Circuit", name)
            self.assertIn("1:43.009", record)

    def test_unknown_and_no_upcoming_event_never_invent_a_record(self):
        name, record = _next_race_circuit_details("Azerbaijan GP", '<New & Circuit>', "en")
        self.assertIn("&lt;New &amp; Circuit&gt;", name)
        self.assertIn("Verified record unavailable", record)
        self.assertNotIn("Charles Leclerc", record)
        self.assertNotIn("href=", record)
        self.assertEqual(_next_race_circuit_details("TBD", "", "en"), ("", ""))

    def test_each_record_has_complete_sourced_timing(self):
        for record in CIRCUIT_RECORDS.values():
            with self.subTest(circuit=record.circuit):
                self.assertRegex(record.lap_time, r"^\d:[0-5]\d\.\d{3}$")
                self.assertTrue(record.driver)
                self.assertLessEqual(record.year, 2026)
                self.assertTrue(record.source.startswith("https://www.formula1.com/en/racing/"))

    def test_actual_dashboard_card_changes_with_next_venue_in_both_languages(self):
        workbook = Path(__file__).resolve().parents[1] / "F1_Standings.xlsx"
        base = core.load_standings_data(workbook)
        latest, meta = core.latest_league_slice(base)
        races = latest[~latest["IsSeasonFinal"]]
        standings = core.standings_table(races, entity="Drivers")
        calendar = core.load_calendar_data(workbook).iloc[:1].copy()
        calendar["League Name"] = meta["League Name"]
        for gp, circuit, driver in (
            ("Azerbaijan GP", "Baku City Circuit", "Charles Leclerc"),
            ("Japanese GP", "Suzuka International Racing Course", "Kimi Antonelli"),
        ):
            calendar["GP Name"], calendar["Circuit"], calendar["Status"] = gp, circuit, "Upcoming"
            for lang, label in (("en", "REAL-WORLD F1 RACE LAP RECORD"), ("pt", "RECORDE REAL DE VOLTA EM CORRIDA F1")):
                with self.subTest(gp=gp, lang=lang):
                    output = render_puskas_dashboard(races, calendar, standings, meta, base, lang)
                    card = output.split('class="p-card p-next-race"', 1)[1].split('<!--', 1)[0]
                    self.assertIn(circuit, card)
                    self.assertIn(driver, card)
                    self.assertIn(label, card)
                    self.assertNotIn(get_circuit_record(gp).source, card)
                    self.assertEqual(card.count('class="p-lap-record-line"'), 2)


class LeagueLapRecordTests(unittest.TestCase):
    def results(self, rows):
        return pd.DataFrame([dict({"GP Name": "Austrian GP", "Driver": "TomasRodri21",
                                   "Fastest Lap": "1:10.097", "Season": "2026-T01",
                                   "Type": "R", "IsSeasonFinal": False}, **row) for row in rows])

    def test_fastest_human_across_seasons_and_sprints_not_race_winner_or_ai(self):
        results = self.results([
            {},
            {"Driver": "Fatacuida", "Fastest Lap": time(0, 1, 10, 677000)},
            {"Driver": "Polingua", "Fastest Lap": time(0, 1, 8, 159000), "Season": "2025-T01", "Type": "SR"},
            {"Driver": "Max Verstappen", "Fastest Lap": "1:00.000"},
            {"Driver": "TomasRodri21 AI", "Fastest Lap": "1:00.000"},
            {"IsSeasonFinal": True, "Fastest Lap": "0:55.000"},
            {"Type": "Q", "Fastest Lap": "0:50.000"},
        ])
        record = league_lap_records(results)[circuit_key("Austrian GP")]
        self.assertEqual((record.lap_time, record.driver, record.season), ("1:08.159", "Polingua", "2025-T01"))

    def test_missing_and_invalid_laps_are_not_inferred_from_race_time(self):
        results = self.results([{"Fastest Lap": value, "Time": "1:00.000"} for value in
                                [None, pd.NA, float("nan"), "", "-", "DNF", "1:70.123", "-1:20.000", "0:00.000", True, 90]])
        self.assertEqual(league_lap_records(results), {})
        self.assertEqual(league_lap_records(results.drop(columns="Fastest Lap")), {})
        self.assertEqual(league_lap_records(None), {})

    def test_workbook_time_formats_are_compared_numerically(self):
        for value in (time(0, 1, 8, 159000), "1:08.159", "00:01:08.159", "1:08,159",
                      timedelta(seconds=68.159), 68.159 / 86400):
            with self.subTest(value=value):
                records = league_lap_records(self.results([{"Fastest Lap": value}, {"Fastest Lap": "0:59.999", "Driver": "Fatacuida"}]))
                self.assertEqual(records[circuit_key("Austrian GP")].lap_time, "0:59.999")
                normalized = league_lap_records(self.results([{"Fastest Lap": value}]))
                self.assertEqual(normalized[circuit_key("Austrian GP")].lap_time, "1:08.159")

    def test_aliases_venues_and_equal_laps_are_stable(self):
        results = self.results([
            {"GP Name": "Mexican GP", "Driver": "TomasRodri", "Fastest Lap": "1:20.000"},
            {"GP Name": "Mexico City GP", "Driver": "Polingua", "Fastest Lap": "1:20.000", "Season": "2025-T01"},
            {"GP Name": "Spanish GP", "Circuit": "Barcelona", "Fastest Lap": "1:18.000"},
            {"GP Name": "Spanish GP", "Circuit": "Madring", "Fastest Lap": "1:35.000"},
        ])
        records = league_lap_records(results)
        self.assertEqual(records, league_lap_records(results.iloc[::-1]))
        self.assertEqual(records[circuit_key("Mexico GP")].season, "2025-T01")
        self.assertEqual(records[circuit_key("Barcelona-Catalunya GP")].lap_time, "1:18.000")
        self.assertEqual(records[circuit_key("Spanish GP")].lap_time, "1:35.000")

    def test_shared_record_lines_and_missing_values_in_both_languages(self):
        records = league_lap_records(self.results([{"Season": "2026-<T01>"}]))
        for lang, missing in (("en", "No recorded lap"), ("pt", "Sem volta registada")):
            gallery = circuit_lap_records_html("Austrian GP", lang=lang, league_records=records)
            _, next_race = _next_race_circuit_details("Austrian GP", "Red Bull Ring", lang, records)
            self.assertEqual(gallery, next_race)
            self.assertEqual(gallery.count('class="p-lap-record-line"'), 2)
            self.assertIn("1:10.097", gallery)
            self.assertIn("TomasRodri21 · 2026-&lt;T01&gt;", gallery)
            self.assertNotIn("href=", gallery)
            japan = circuit_lap_records_html("Japanese GP", lang=lang, league_records=records)
            self.assertIn("Kimi Antonelli · 2025", japan)
            self.assertIn(missing, japan)


if __name__ == "__main__":
    unittest.main()
