from __future__ import annotations

import unittest

import race_import as race


def token(
    text: str,
    confidence: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    source: str = "Screenshot 1",
) -> race.OcrToken:
    return race.OcrToken(text, confidence, x_min, y_min, x_max, y_max, source)


def race_header() -> list[race.OcrToken]:
    # Compact fixture based on the supplied photographs' real RapidOCR output.
    return [
        token("POS.DRIVER", 0.95, 500, 180, 575, 190),
        token("TEAM", 0.90, 674, 180, 705, 190),
        token("GRID", 0.99, 793, 180, 820, 190),
        token("STOEPEEST", 0.62, 826, 180, 886, 190),
        token("TIME", 0.95, 912, 180, 940, 190),
        token("PTS.", 0.78, 995, 180, 1018, 190),
    ]


class TimingHeaderTests(unittest.TestCase):
    def test_detects_credible_best_and_time_columns(self):
        columns = race.detect_timing_columns(race_header())

        self.assertIsNotNone(columns)
        assert columns is not None
        self.assertLess(columns.fastest_lap_x, columns.time_x)
        self.assertLess(columns.fastest_lap_min_x, columns.split_x)
        self.assertLess(columns.split_x, columns.time_max_x)

    def test_rejects_sprint_weekend_summary_columns(self):
        sprint_header = [
            token("POS.", 0.99, 450, 180, 480, 190),
            token("DRIVER", 0.99, 500, 180, 570, 190),
            token("TEAM", 0.99, 650, 180, 700, 190),
            token("SR", 0.99, 800, 180, 820, 190),
            token("R", 0.99, 880, 180, 890, 190),
            token("PTS.", 0.99, 995, 180, 1018, 190),
        ]

        self.assertIsNone(race.detect_timing_columns(sprint_header))


class TimingExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = [
            race.DriverEntry("Alice", "Red"),
            race.DriverEntry("Bob", "Blue"),
        ]

    def test_extracts_exact_fields_and_stages_repairs_for_review(self):
        tokens = race_header() + [
            token("1", 0.99, 505, 198, 515, 208),
            token("Alice", 0.96, 560, 198, 620, 208),
            token("Red", 0.96, 680, 198, 720, 208),
            token("1:35.122", 0.87, 850, 198, 910, 208),
            token("82:50.787", 0.96, 912, 198, 958, 208),
            token("2", 0.99, 505, 216, 515, 226),
            token("Bob", 0.96, 560, 216, 620, 226),
            token("Blue", 0.96, 680, 216, 720, 226),
            token("134.526", 0.97, 850, 216, 910, 226),
            token("+11825", 0.69, 912, 216, 958, 226),
        ]

        rows = race.extract_results_from_tokens(tokens, self.roster, source="Screenshot 1")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].fastest_lap, "1:35.122")
        self.assertEqual(rows[0].time, "82:50.787")
        self.assertEqual(rows[0].fastest_lap_confidence, 0.87)
        self.assertEqual(rows[0].time_confidence, 0.96)
        self.assertIsNone(rows[1].fastest_lap)
        self.assertEqual(rows[1].suggested_fastest_lap, "1:34.526")
        self.assertIn("repaired", " ".join(rows[1].fastest_lap_issues))
        self.assertIsNone(rows[1].time)
        self.assertEqual(rows[1].suggested_time, "+11.825")
        self.assertIn("repaired", " ".join(rows[1].time_issues))

    def test_summary_rows_do_not_gain_timing_fields(self):
        summary_tokens = [
            token("POS.", 0.99, 450, 180, 480, 190),
            token("DRIVER", 0.99, 500, 180, 570, 190),
            token("TEAM", 0.99, 650, 180, 700, 190),
            token("SR", 0.99, 800, 180, 820, 190),
            token("R", 0.99, 880, 180, 890, 190),
            token("PTS.", 0.99, 995, 180, 1018, 190),
            token("1", 0.99, 455, 200, 465, 210),
            token("Alice", 0.96, 520, 200, 580, 210),
            token("Red", 0.96, 660, 200, 700, 210),
            token("8", 0.99, 805, 200, 815, 210),
            token("25", 0.99, 995, 200, 1010, 210),
        ]

        extracted = race.extract_results_from_tokens(summary_tokens, self.roster, source="Sprint")
        review = race.build_review_rows(extracted, len(self.roster))

        self.assertEqual(len(extracted), 1)
        self.assertFalse(extracted[0].timing_expected)
        self.assertNotIn("Time", review[0])
        self.assertNotIn("Fastest Lap", review[0])

    def test_recovers_only_a_position_forced_between_monotonic_detail_anchors(self):
        roster = self.roster + [
            race.DriverEntry("Charlie", "Green"),
            race.DriverEntry("Dana", "Gold"),
        ]
        tokens = race_header() + [
            token("1", 0.99, 505, 198, 515, 208),
            token("Alice", 0.96, 560, 198, 620, 208),
            token("1:35.122", 0.90, 850, 198, 910, 208),
            token("82:50.787", 0.90, 912, 198, 958, 208),
            token("Bob", 0.96, 560, 216, 620, 226),
            token("1:34.526", 0.90, 850, 216, 910, 226),
            token("+11.825", 0.90, 912, 216, 958, 226),
            token("3", 0.99, 505, 234, 515, 244),
            token("Charlie", 0.96, 560, 234, 640, 244),
            token("1:34.100", 0.90, 850, 234, 910, 244),
            token("+15.000", 0.90, 912, 234, 958, 244),
            token("4", 0.99, 505, 252, 515, 262),
            token("Dana", 0.96, 560, 252, 620, 262),
            token("1:35.900", 0.90, 850, 252, 910, 262),
            token("+1 Lap", 0.90, 912, 252, 958, 262),
        ]

        rows = race.extract_results_from_tokens(tokens, roster, source="Race")
        bob = next(row for row in rows if row.suggested_driver == "Bob")

        self.assertEqual(bob.position, 2)
        self.assertIn("inferred from contiguous detail rows", " ".join(bob.issues))

    def test_does_not_recover_position_across_a_detail_row_gap(self):
        roster = self.roster + [
            race.DriverEntry("Charlie", "Green"),
            race.DriverEntry("Dana", "Gold"),
        ]
        tokens = race_header() + [
            token("1", 0.99, 505, 198, 515, 208),
            token("Alice", 0.96, 560, 198, 620, 208),
            token("1:35.122", 0.90, 850, 198, 910, 208),
            token("82:50.787", 0.90, 912, 198, 958, 208),
            token("Bob", 0.96, 560, 216, 620, 226),
            token("1:34.526", 0.90, 850, 216, 910, 226),
            token("+11.825", 0.90, 912, 216, 958, 226),
            token("3", 0.99, 505, 248, 515, 258),
            token("Charlie", 0.96, 560, 248, 640, 258),
            token("1:34.100", 0.90, 850, 248, 910, 258),
            token("+15.000", 0.90, 912, 248, 958, 258),
            token("4", 0.99, 505, 266, 515, 276),
            token("Dana", 0.96, 560, 266, 620, 276),
            token("1:35.900", 0.90, 850, 266, 910, 276),
            token("+1 Lap", 0.90, 912, 266, 958, 276),
        ]

        rows = race.extract_results_from_tokens(tokens, roster, source="Race")
        bob = next(row for row in rows if row.suggested_driver == "Bob")

        self.assertIsNone(bob.position)

    def test_recovers_leading_row_on_a_later_page_from_two_local_anchors(self):
        roster = [race.DriverEntry(f"Driver {position}", f"Team {position}") for position in range(1, 12)]
        tokens = race_header() + [
            token("Driver 9", 0.96, 560, 198, 630, 208),
            token("1:34.632", 0.90, 850, 198, 910, 208),
            token("+31.451", 0.90, 912, 198, 958, 208),
            token("10", 0.99, 505, 216, 520, 226),
            token("Driver 10", 0.96, 560, 216, 640, 226),
            token("1:34.100", 0.90, 850, 216, 910, 226),
            token("+35.000", 0.90, 912, 216, 958, 226),
            token("11", 0.99, 505, 234, 520, 244),
            token("Driver 11", 0.96, 560, 234, 640, 244),
            token("1:35.900", 0.90, 850, 234, 910, 244),
            token("+1 Lap", 0.90, 912, 234, 958, 244),
        ]

        rows = race.extract_results_from_tokens(tokens, roster, source="Race page 2")
        driver_nine = next(row for row in rows if row.suggested_driver == "Driver 9")

        self.assertEqual(driver_nine.position, 9)
        self.assertIn("inferred from contiguous detail rows", " ".join(driver_nine.issues))

    def test_no_header_means_no_ordered_position_recovery(self):
        roster = self.roster + [race.DriverEntry("Charlie", "Green")]
        tokens = [
            token("1", 0.99, 505, 198, 515, 208),
            token("Alice", 0.96, 560, 198, 620, 208),
            token("1:35.122", 0.90, 850, 198, 910, 208),
            token("Bob", 0.96, 560, 216, 620, 226),
            token("1:34.526", 0.90, 850, 216, 910, 226),
            token("3", 0.99, 505, 234, 515, 244),
            token("Charlie", 0.96, 560, 234, 640, 244),
            token("1:34.100", 0.90, 850, 234, 910, 244),
        ]

        rows = race.extract_results_from_tokens(tokens, roster, source="Unknown table")
        bob = next(row for row in rows if row.suggested_driver == "Bob")

        self.assertIsNone(bob.position)

    def test_merge_conflict_requires_manual_timing_choice(self):
        first = race.ExtractedResult(
            1,
            "1 Alice 1:35.122 82:50.787",
            "Alice",
            "Alice",
            0.9,
            ["Screenshot 1"],
            "exact",
            [],
            time="82:50.787",
            suggested_time="82:50.787",
            time_confidence=0.9,
            fastest_lap="1:35.122",
            suggested_fastest_lap="1:35.122",
            fastest_lap_confidence=0.9,
            timing_expected=True,
        )
        second = race.ExtractedResult(
            1,
            "1 Alice 1:35.122 82:51.000",
            "Alice",
            "Alice",
            0.95,
            ["Screenshot 2"],
            "exact",
            [],
            time="82:51.000",
            suggested_time="82:51.000",
            time_confidence=0.95,
            fastest_lap="1:35.122",
            suggested_fastest_lap="1:35.122",
            fastest_lap_confidence=0.95,
            timing_expected=True,
        )

        merged = race.merge_screenshot_results([[first], [second]])

        self.assertEqual(len(merged), 1)
        self.assertIsNone(merged[0].time)
        self.assertEqual(merged[0].suggested_time, "82:51.000")
        self.assertIn("Conflicting result time values", " ".join(merged[0].time_issues))
        self.assertEqual(merged[0].fastest_lap, "1:35.122")


class TimingReviewValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = [
            race.DriverEntry("Alice", "Red"),
            race.DriverEntry("Bob", "Blue"),
        ]
        self.scoring = {1: 25.0, 2: 18.0}

    def test_review_rows_expose_field_specific_confidence_and_notes(self):
        extracted = [
            race.ExtractedResult(
                1,
                "1 Alice",
                "Alice",
                "Alice",
                0.9,
                ["Screenshot 1"],
                "exact",
                [],
                time="82:50.787",
                suggested_time="82:50.787",
                time_confidence=0.96,
                fastest_lap=None,
                suggested_fastest_lap="1:35.122",
                fastest_lap_confidence=0.65,
                fastest_lap_issues=["Low OCR confidence; confirm the fastest lap."],
                timing_expected=True,
            )
        ]

        rows = race.build_review_rows(extracted, 2)

        self.assertEqual(rows[0]["Time"], "82:50.787")
        self.assertEqual(rows[0]["Time Confidence"], 0.96)
        self.assertEqual(rows[0]["Suggested Fastest Lap"], "1:35.122")
        self.assertIn("Low OCR confidence", rows[0]["Fastest Lap Notes"])
        self.assertTrue(rows[1]["Timing Expected"])
        self.assertIn("not recognized", rows[1]["Time Notes"])

    def test_validation_blocks_unconfirmed_or_malformed_timing(self):
        validation = race.validate_review_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Time": "82:50787",
                    "Fastest Lap": "",
                    "Suggested Fastest Lap": "1:35.122",
                    "Timing Expected": True,
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Time": "+11.825",
                    "Fastest Lap": "1:34.526",
                    "Timing Expected": True,
                },
            ],
            self.roster,
            self.scoring,
        )

        blockers = "\n".join(validation.blockers)
        self.assertIn("row 1 has an invalid result time", blockers)
        self.assertIn("row 1 needs a confirmed fastest lap", blockers)

    def test_editable_timing_columns_remain_required_if_hidden_marker_is_dropped(self):
        validation = race.validate_review_rows(
            [
                {"Position": 1, "Driver": "Alice", "Time": "", "Fastest Lap": ""},
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Time": "+11.825",
                    "Fastest Lap": "1:34.526",
                },
            ],
            self.roster,
            self.scoring,
        )

        blockers = "\n".join(validation.blockers)
        self.assertIn("row 1 needs a confirmed result time", blockers)
        self.assertIn("row 1 needs a confirmed fastest lap", blockers)

    def test_short_unprefixed_clock_is_not_accepted_as_a_race_total(self):
        self.assertIsNone(race.normalize_race_time("1:09.463"))

    def test_validation_preserves_confirmed_canonical_timing(self):
        validation = race.validate_review_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Time": "82:50,787",
                    "Fastest Lap": "1:35,122",
                    "Timing Expected": True,
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Time": "+1 Lap",
                    "Fastest Lap": "N/A",
                    "Timing Expected": True,
                },
            ],
            self.roster,
            self.scoring,
        )

        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.rows[0]["Time"], "82:50.787")
        self.assertEqual(validation.rows[0]["Fastest Lap"], "1:35.122")
        self.assertEqual(validation.rows[1]["Time"], "+1 Lap")
        self.assertEqual(validation.rows[1]["Fastest Lap"], "N/A")

    def test_legacy_manual_review_shape_is_unchanged(self):
        validation = race.validate_review_rows(
            [
                {"Position": 1, "Driver": "Alice"},
                {"Position": 2, "Driver": "Bob"},
            ],
            self.roster,
            self.scoring,
        )

        self.assertTrue(validation.is_valid)
        self.assertEqual(
            validation.rows[0],
            {"Position": 1, "Driver": "Alice", "Team": "Red", "Points": 25.0},
        )


if __name__ == "__main__":
    unittest.main()
