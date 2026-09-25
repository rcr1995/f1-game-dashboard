"""Records must follow the venue without confusing game and real-world timing."""
from pathlib import Path
import unittest

import pandas as pd

import dashboard_core as core
from circuit_records import CIRCUIT_RECORDS, get_circuit_record
from puskas_html import _next_race_circuit_details, render_puskas_dashboard


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
                    self.assertIn(get_circuit_record(gp).source, card)


if __name__ == "__main__":
    unittest.main()
