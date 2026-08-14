from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

import race_import as race
import race_import_ui as ui
import race_ocr
import race_workbook as workbook


def synthetic_image(color: str) -> bytes:
    """Return a small in-memory raster; no user screenshot is used as a fixture."""
    buffer = io.BytesIO()
    Image.new("RGB", (32, 18), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def token(
    text: str,
    confidence: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    source: str,
) -> race.OcrToken:
    return race.OcrToken(text, confidence, x_min, y_min, x_max, y_max, source)


def detail_tokens(
    source: str,
    *,
    position: int,
    driver: str,
    team: str,
    fastest_lap: str,
    result_time: str,
    heading: str | None = None,
    row_y: float = 198,
    include_header: bool = True,
) -> list[race.OcrToken]:
    """Synthetic detail-table OCR shaped like the supplied game's BEST/TIME grid."""
    tokens: list[race.OcrToken] = []
    if heading:
        tokens.append(token(heading, 0.99, 300, 135, 600, 155, source))
    if include_header:
        tokens.extend(
            [
                token("POS.DRIVER", 0.99, 500, 180, 575, 190, source),
                token("TEAM", 0.99, 674, 180, 705, 190, source),
                token("GRID", 0.99, 793, 180, 820, 190, source),
                token("STOEPEEST", 0.92, 826, 180, 886, 190, source),
                token("TIME", 0.99, 912, 180, 940, 190, source),
                token("PTS.", 0.99, 995, 180, 1018, 190, source),
            ]
        )
    tokens.extend(
        [
            token(str(position), 0.99, 505, row_y, 515, row_y + 10, source),
            token(driver, 0.99, 560, row_y, 630, row_y + 10, source),
            token(team, 0.99, 680, row_y, 740, row_y + 10, source),
            token(fastest_lap, 0.99, 850, row_y, 910, row_y + 10, source),
            token(result_time, 0.99, 912, row_y, 970, row_y + 10, source),
        ]
    )
    return tokens


def extracted_result(
    position: int,
    driver: str,
    source: str,
    *,
    result_time: str | None = None,
    fastest_lap: str | None = None,
) -> race.ExtractedResult:
    return race.ExtractedResult(
        position,
        f"{position} {driver}",
        driver,
        driver,
        0.99,
        [source],
        "exact",
        [],
        time=result_time,
        suggested_time=result_time,
        time_confidence=0.99 if result_time else 0.0,
        fastest_lap=fastest_lap,
        suggested_fastest_lap=fastest_lap,
        fastest_lap_confidence=0.99 if fastest_lap else 0.0,
        timing_expected=True,
    )


def summary_tokens(source: str) -> list[race.OcrToken]:
    """Synthetic Weekend-summary OCR, intentionally without BEST/TIME columns."""
    return [
        token("POS.", 0.99, 450, 180, 480, 190, source),
        token("DRIVER", 0.99, 500, 180, 570, 190, source),
        token("TEAM", 0.99, 650, 180, 700, 190, source),
        token("SR", 0.99, 800, 180, 820, 190, source),
        token("R", 0.99, 880, 180, 890, 190, source),
        token("PTS.", 0.99, 995, 180, 1018, 190, source),
    ]


class TimingReviewFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = [
            race.DriverEntry("Alice", "Red"),
            race.DriverEntry("Bob", "Blue"),
        ]
        self.scoring = {1: 25.0, 2: 18.0}
        self.uploads = [synthetic_image("red"), synthetic_image("blue")]

    def _token_sets(self) -> list[list[race.OcrToken]]:
        first = detail_tokens(
                "Screenshot 1",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
            )
        first.extend(
            detail_tokens(
                "Screenshot 1",
                position=2,
                driver="Bob",
                team="Blue",
                fastest_lap="1:34.632",
                result_time="+0.946",
                row_y=216,
                include_header=False,
            )
        )
        second = detail_tokens(
            "Screenshot 2",
            position=1,
            driver="Alice",
            team="Red",
            fastest_lap="1:35.122",
            result_time="82:50.787",
        )
        second.extend(
            detail_tokens(
                "Screenshot 2",
                position=2,
                driver="Bob",
                team="Blue",
                fastest_lap="1:34.632",
                result_time="+0.946",
                row_y=216,
                include_header=False,
            )
        )
        return [
            first,
            second,
        ]

    def test_exact_timing_flows_through_review_digest_and_validation(self):
        token_sets = self._token_sets()
        with (
            patch("race_import_ui.race_ocr.extract_tokens", side_effect=token_sets),
            patch(
                "race_import_ui.race_ocr.detect_selected_results_tab",
                side_effect=["R", "R"],
            ),
        ):
            review_rows, token_count = ui._draft_from_ocr(
                self.uploads,
                self.roster,
                require_timing_detail=True,
                expected_event_type="R",
            )

        self.assertEqual(token_count, sum(map(len, token_sets)))
        by_position = {row["Position"]: row for row in review_rows}
        self.assertEqual(by_position[1]["Time"], "82:50.787")
        self.assertEqual(by_position[1]["Fastest Lap"], "1:35.122")
        self.assertEqual(by_position[2]["Time"], "+0.946")
        self.assertEqual(by_position[2]["Fastest Lap"], "1:34.632")

        reviewed = [
            {
                "Position": row["Position"],
                "Driver": row["Driver"],
                "Time": row["Time"],
                "Fastest Lap": row["Fastest Lap"],
                "Timing Expected": True,
            }
            for row in review_rows
        ]
        validation = race.validate_review_rows(reviewed, self.roster, self.scoring)

        self.assertTrue(validation.is_valid, validation.blockers)
        self.assertEqual(validation.rows[0]["Time"], "82:50.787")
        self.assertEqual(validation.rows[0]["Fastest Lap"], "1:35.122")
        self.assertEqual(validation.rows[1]["Time"], "+0.946")
        self.assertEqual(validation.rows[1]["Fastest Lap"], "1:34.632")

        context = {"round": 3, "type": "R", "screenshots": ["one", "two"]}
        digest = race.review_digest(validation.rows, context)
        changed_rows = [dict(row) for row in validation.rows]
        changed_rows[1]["Time"] = "+0.947"
        self.assertNotEqual(digest, race.review_digest(changed_rows, context))

    def test_sprint_detail_schema_preserves_duration_gaps_laps_statuses_and_fastest_laps(self):
        roster = [
            race.DriverEntry(f"Driver {position}", f"Team {position}")
            for position in range(1, 7)
        ]
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        results = {
            1: ("26:40.317", "1:32.888"),
            2: ("+31.451", "1:34.632"),
            3: ("+1:09.463", "1:33.050"),
            4: ("+1 Lap", "1:34.079"),
            5: ("DNF", "1:34.154"),
            6: ("DSQ", "N/A"),
        }

        def page(source: str, positions: tuple[int, ...]) -> list[race.OcrToken]:
            tokens: list[race.OcrToken] = []
            for row_index, position in enumerate(positions):
                result_time, fastest_lap = results[position]
                tokens.extend(
                    detail_tokens(
                        source,
                        position=position,
                        driver=f"Driver {position}",
                        team=f"Team {position}",
                        fastest_lap=fastest_lap,
                        result_time=result_time,
                        heading=(
                            "FORMULA 1 BRITISH GRAND PRIX - SPRINT"
                            if row_index == 0
                            else None
                        ),
                        row_y=198 + row_index * 18,
                        include_header=row_index == 0,
                    )
                )
            return tokens

        token_sets = [
            page("Screenshot 1", (1, 2, 3, 4)),
            page("Screenshot 2", (3, 4, 5, 6)),
        ]
        with (
            patch("race_import_ui.race_ocr.extract_tokens", side_effect=token_sets),
            patch(
                "race_import_ui.race_ocr.detect_selected_results_tab",
                side_effect=["SR", "SR"],
            ),
        ):
            review_rows, _ = ui._draft_from_ocr(
                uploads,
                roster,
                require_timing_detail=True,
                expected_event_type="SR",
                expected_gp="British Grand Prix",
            )

        by_position = {row["Position"]: row for row in review_rows}
        for position, (result_time, fastest_lap) in results.items():
            self.assertEqual(by_position[position]["Time"], result_time)
            self.assertEqual(by_position[position]["Fastest Lap"], fastest_lap)

        scoring = race.scoring_profile_from_project_rules("SR", len(roster))
        reviewed = [
            {
                "Position": row["Position"],
                "Driver": row["Driver"],
                "Time": row["Time"],
                "Fastest Lap": row["Fastest Lap"],
                "Timing Expected": True,
            }
            for row in review_rows
        ]
        validation = race.validate_review_rows(reviewed, roster, scoring)
        self.assertTrue(validation.is_valid, validation.blockers)

        normalized = workbook._validate_commit_rows(
            validation.rows,
            scoring,
            require_complete_timing=True,
        )
        metadata = workbook.RaceMetadata(
            "F1 26",
            "2026-T01",
            "League",
            3,
            "SR",
            "British Grand Prix",
        )
        serialized = {
            row["Position"]: workbook._workbook_row(metadata, row)
            for row in normalized
        }
        self.assertTrue(all(row["E"] == "SR" for row in serialized.values()))
        self.assertEqual(serialized[1]["K"], "26:40.317")
        self.assertEqual(serialized[3]["K"], "+1:09.463")
        self.assertEqual(serialized[4]["K"], "+1 Lap")
        self.assertEqual(serialized[5]["K"], "DNF")
        self.assertEqual(serialized[6]["K"], "DSQ")
        self.assertEqual(serialized[1]["L"], "1:32.888")
        self.assertEqual(serialized[6]["L"], "N/A")

    def test_missing_and_invalid_ui_timing_values_block_approval_validation(self):
        missing = race.validate_review_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Time": "82:50.787",
                    "Fastest Lap": "",
                    "Timing Expected": True,
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Time": "",
                    "Fastest Lap": "1:34.632",
                    "Timing Expected": True,
                },
            ],
            self.roster,
            self.scoring,
        )
        missing_blockers = "\n".join(missing.blockers)
        self.assertIn("needs a confirmed fastest lap", missing_blockers)
        self.assertIn("needs a confirmed result time", missing_blockers)

        invalid = race.validate_review_rows(
            [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Time": "82:50787",
                    "Fastest Lap": "1:35.122",
                    "Timing Expected": True,
                },
                {
                    "Position": 2,
                    "Driver": "Bob",
                    "Time": "+0.946",
                    "Fastest Lap": "+1.234",
                    "Timing Expected": True,
                },
            ],
            self.roster,
            self.scoring,
        )
        invalid_blockers = "\n".join(invalid.blockers)
        self.assertIn("invalid result time", invalid_blockers)
        self.assertIn("invalid fastest lap", invalid_blockers)


class ResultsSessionPreflightTests(unittest.TestCase):
    def test_matching_grand_prix_heading_is_accepted(self):
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                f"Screenshot {index}",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
                heading="FORMULA 1 BRITISH GRAND PRIX - RACE",
            )
            for index in (1, 2)
        ]
        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["R", "R"],
        ):
            errors = ui.validate_results_session_set(
                uploads,
                token_sets,
                "R",
                expected_gp="British Grand Prix",
            )

        self.assertEqual(errors, [])

    def test_wrong_grand_prix_heading_is_rejected(self):
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                "Screenshot 1",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
                heading="FORMULA 1 BRITISH GRAND PRIX - RACE",
            ),
            detail_tokens(
                "Screenshot 2",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
                heading="FORMULA 1 BELGIAN GRAND PRIX - RACE",
            ),
        ]
        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["R", "R"],
        ):
            errors = ui.validate_results_session_set(
                uploads,
                token_sets,
                "R",
                expected_gp="British Grand Prix",
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2", errors[0])
        self.assertIn("Grand Prix heading does not safely match British Grand Prix", errors[0])

    def test_austrian_grand_prix_does_not_fuzzily_match_australian_heading(self):
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                f"Screenshot {index}",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
                heading="FORMULA 1 AUSTRALIAN GRAND PRIX - RACE",
            )
            for index in (1, 2)
        ]
        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["R", "R"],
        ):
            errors = ui.validate_results_session_set(
                uploads,
                token_sets,
                "R",
                expected_gp="Austrian Grand Prix",
            )

        self.assertEqual(len(errors), 2)
        self.assertTrue(all("does not safely match Austrian Grand Prix" in error for error in errors))

    def test_two_three_and_four_consistent_detail_images_pass_preflight(self):
        colors = ["red", "green", "blue", "yellow"]
        for count in (2, 3, 4):
            with self.subTest(count=count):
                uploads = [synthetic_image(color) for color in colors[:count]]
                token_sets = [
                    detail_tokens(
                        f"Screenshot {index}",
                        position=1,
                        driver="Alice",
                        team="Red",
                        fastest_lap="1:35.122",
                        result_time="82:50.787",
                    )
                    for index in range(1, count + 1)
                ]
                with patch(
                    "race_import_ui.race_ocr.detect_selected_results_tab",
                    side_effect=["SR"] * count,
                ):
                    errors = ui.validate_results_session_set(uploads, token_sets, "SR")

                self.assertTrue(ui.valid_screenshot_count(count))
                self.assertEqual(errors, [])

    def test_mixed_race_and_sprint_set_is_rejected_before_row_extraction(self):
        roster = [race.DriverEntry("Alice", "Red")]
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                "Screenshot 1",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
            ),
            detail_tokens(
                "Screenshot 2",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="26:40.317",
            ),
        ]

        with (
            patch("race_import_ui.race_ocr.extract_tokens", side_effect=token_sets),
            patch(
                "race_import_ui.race_ocr.detect_selected_results_tab",
                side_effect=["R", "SR"],
            ),
            patch("race_import_ui.ri.extract_results_from_tokens") as extract_rows,
            self.assertRaisesRegex(
                race_ocr.InvalidScreenshotError,
                "Screenshot 2: the selected tab is Sprint.*Upload one event at a time",
            ),
        ):
            ui._draft_from_ocr(
                uploads,
                roster,
                require_timing_detail=True,
                expected_event_type="R",
            )

        extract_rows.assert_not_called()

    def test_weekend_summary_is_rejected_with_detail_tab_instruction(self):
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [summary_tokens("Screenshot 1"), summary_tokens("Screenshot 2")]

        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["WEEKEND", "WEEKEND"],
        ):
            errors = ui.validate_results_session_set(uploads, token_sets, "SR")

        message = "\n".join(errors)
        self.assertIn("Results (Weekend) is a combined summary", message)
        self.assertIn("Open Results (Sprint) instead", message)
        self.assertIn("BEST and TIME columns were not recognized", message)

    def test_uncertain_selected_tab_fails_closed(self):
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                f"Screenshot {index}",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
            )
            for index in (1, 2)
        ]
        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["R", None],
        ):
            errors = ui.validate_results_session_set(uploads, token_sets, "R")

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2", errors[0])
        self.assertIn("selected red Results tab could not be verified", errors[0])


class ScreenshotOverlapTests(unittest.TestCase):
    def _connected_chain(self) -> list[list[race.ExtractedResult]]:
        # Every neighbouring pair repeats two exact canonical identities at the
        # same positions. Edges use precise Time and/or BEST evidence.
        return [
            [
                extracted_result(1, "Driver 1", "Screenshot 1", result_time="82:50.787"),
                extracted_result(2, "Driver 2", "Screenshot 1", result_time="+0.946"),
                extracted_result(3, "Driver 3", "Screenshot 1", fastest_lap="1:34.526"),
            ],
            [
                extracted_result(2, "Driver 2", "Screenshot 2", result_time="+0.946"),
                extracted_result(3, "Driver 3", "Screenshot 2", fastest_lap="1:34.526"),
                extracted_result(4, "Driver 4", "Screenshot 2", fastest_lap="1:35.224"),
            ],
            [
                extracted_result(3, "Driver 3", "Screenshot 3", fastest_lap="1:34.526"),
                extracted_result(4, "Driver 4", "Screenshot 3", fastest_lap="1:35.224"),
                extracted_result(5, "Driver 5", "Screenshot 3", result_time="+12.345"),
            ],
            [
                extracted_result(4, "Driver 4", "Screenshot 4", fastest_lap="1:35.224"),
                extracted_result(5, "Driver 5", "Screenshot 4", result_time="+12.345"),
                extracted_result(6, "Driver 6", "Screenshot 4", fastest_lap="1:36.789"),
            ],
        ]

    def test_two_three_and_four_image_overlap_chains_are_accepted(self):
        chain = self._connected_chain()
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.assertEqual(ui.validate_screenshot_overlap(chain[:count]), [])

    def test_disjoint_result_sets_are_rejected(self):
        result_sets = [
            [extracted_result(1, "Alice", "Screenshot 1", result_time="82:50.787")],
            [extracted_result(9, "Bob", "Screenshot 2", result_time="+31.451")],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2 is disconnected", errors[0])
        self.assertIn("repeated rows", errors[0])

    def test_one_precise_matching_overlap_row_is_insufficient(self):
        result_sets = [
            [extracted_result(9, "Alice", "Screenshot 1", result_time="+31.451")],
            [extracted_result(9, "Alice", "Screenshot 2", result_time="+31.451")],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2 is disconnected", errors[0])

    def test_statuses_and_lap_deficits_are_not_precise_overlap_evidence(self):
        result_sets = [
            [
                extracted_result(9, "Alice", "Screenshot 1", result_time="+1 Lap"),
                extracted_result(10, "Bob", "Screenshot 1", result_time="DNF"),
            ],
            [
                extracted_result(9, "Alice", "Screenshot 2", result_time="+1 Lap"),
                extracted_result(10, "Bob", "Screenshot 2", result_time="DNF"),
            ],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2 is disconnected", errors[0])

    def test_unconfirmed_driver_suggestions_cannot_establish_overlap(self):
        def suggestion(position: int, driver: str, source: str, result_time: str):
            return race.ExtractedResult(
                position,
                f"{position} {driver}",
                None,
                driver,
                0.70,
                [source],
                "fuzzy",
                ["Driver needs review."],
                time=result_time,
                suggested_time=result_time,
                time_confidence=0.99,
                timing_expected=True,
            )

        result_sets = [
            [
                suggestion(9, "Alice", "Screenshot 1", "+31.451"),
                suggestion(10, "Bob", "Screenshot 1", "+31.718"),
            ],
            [
                suggestion(9, "Alice", "Screenshot 2", "+31.451"),
                suggestion(10, "Bob", "Screenshot 2", "+31.718"),
            ],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertEqual(len(errors), 1)
        self.assertIn("Screenshot 2 is disconnected", errors[0])

    def test_exact_timing_conflict_blocks_even_when_two_other_rows_connect(self):
        result_sets = [
            [
                extracted_result(1, "Alice", "Screenshot 1", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 1", fastest_lap="1:34.632"),
                extracted_result(3, "Charlie", "Screenshot 1", result_time="+3.000"),
            ],
            [
                extracted_result(1, "Alice", "Screenshot 2", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 2", fastest_lap="1:34.632"),
                extracted_result(3, "Charlie", "Screenshot 2", result_time="+4.000"),
            ],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertTrue(any("disagree on Time at position 3" in error for error in errors))

    def test_same_position_different_driver_blocks_despite_two_connecting_rows(self):
        result_sets = [
            [
                extracted_result(1, "Alice", "Screenshot 1", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 1", fastest_lap="1:34.632"),
                extracted_result(3, "Charlie", "Screenshot 1", result_time="+3.000"),
            ],
            [
                extracted_result(1, "Alice", "Screenshot 2", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 2", fastest_lap="1:34.632"),
                extracted_result(3, "Dana", "Screenshot 2", result_time="+3.000"),
            ],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertTrue(any("disagree on the driver at position 3" in error for error in errors))

    def test_same_driver_different_position_blocks_despite_two_connecting_rows(self):
        result_sets = [
            [
                extracted_result(1, "Alice", "Screenshot 1", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 1", fastest_lap="1:34.632"),
                extracted_result(3, "Charlie", "Screenshot 1", result_time="+3.000"),
            ],
            [
                extracted_result(1, "Alice", "Screenshot 2", result_time="82:50.787"),
                extracted_result(2, "Bob", "Screenshot 2", fastest_lap="1:34.632"),
                extracted_result(4, "Charlie", "Screenshot 2", result_time="+3.000"),
            ],
        ]

        errors = ui.validate_screenshot_overlap(result_sets)

        self.assertTrue(any("place Charlie at different positions" in error for error in errors))

    def test_identity_overlap_with_conflicting_timing_is_rejected(self):
        result_sets = [
            [extracted_result(9, "Alice", "Screenshot 1", result_time="+31.451")],
            [extracted_result(9, "Alice", "Screenshot 2", result_time="+31.718")],
        ]

        self.assertTrue(ui.validate_screenshot_overlap(result_sets))

    def test_draft_rejects_disjoint_pages_before_hybrid_review_is_built(self):
        roster = [race.DriverEntry("Alice", "Red"), race.DriverEntry("Bob", "Blue")]
        uploads = [synthetic_image("red"), synthetic_image("blue")]
        token_sets = [
            detail_tokens(
                "Screenshot 1",
                position=1,
                driver="Alice",
                team="Red",
                fastest_lap="1:35.122",
                result_time="82:50.787",
                heading="FORMULA 1 BRITISH GRAND PRIX - RACE",
            ),
            detail_tokens(
                "Screenshot 2",
                position=2,
                driver="Bob",
                team="Blue",
                fastest_lap="1:34.632",
                result_time="+0.946",
                heading="FORMULA 1 BRITISH GRAND PRIX - RACE",
            ),
        ]

        with (
            patch("race_import_ui.race_ocr.extract_tokens", side_effect=token_sets),
            patch(
                "race_import_ui.race_ocr.detect_selected_results_tab",
                side_effect=["R", "R"],
            ),
            patch("race_import_ui.ri.merge_screenshot_results") as merge_results,
            patch("race_import_ui.ri.build_review_rows") as build_review,
            self.assertRaisesRegex(
                race_ocr.InvalidScreenshotError,
                "do not form one trusted overlapping result set",
            ),
        ):
            ui._draft_from_ocr(
                uploads,
                roster,
                require_timing_detail=True,
                expected_event_type="R",
                expected_gp="British Grand Prix",
            )

        merge_results.assert_not_called()
        build_review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
