from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pandas as pd

import dashboard_core as core
import race_import_ui as ui


def standings_rows(
    game: str,
    season: str,
    league: str,
    events: list[tuple[int, str, str]],
) -> pd.DataFrame:
    rows: list[dict] = []
    for round_number, gp_name, event_type in events:
        rows.append(
            {
                "Game": game,
                "Season": season,
                "SeasonLabel": season,
                "League Name": league,
                "Round": round_number,
                "Type": event_type,
                "GP Name": gp_name,
                "Driver": "Driver One",
                "Team": "Team One",
                "Finish Pos": 1,
                "Points": 25,
                "IsSeasonFinal": False,
            }
        )
    return pd.DataFrame(rows)


def calendar_rows(rows: list[tuple[str, int, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "League Name": league,
                "Round": round_number,
                "Date": pd.Timestamp(event_date),
                "GP Name": gp_name,
                "Status": status,
            }
            for league, round_number, event_date, gp_name, status in rows
        ]
    )


class AdminDefaultInferenceTests(unittest.TestCase):
    def test_unique_active_calendar_selects_championship_and_earliest_unresolved_event(self):
        old = standings_rows(
            "F1 25",
            "2025-T01",
            "Old League",
            [(1, "Old GP", "R")],
        )
        current = standings_rows(
            "F1 25: 2026 Season pack",
            "2026-T02",
            "Teikirise",
            [
                (1, "Chinese GP", "R"),
                (2, "British GP", "R"),
                (3, "Belgian GP", "R"),
                (4, "Hungarian GP", "R"),
            ],
        )
        calendar = calendar_rows(
            [
                ("Old League", 2, "2025-06-01", "Old Second GP", "Done"),
                ("Teikirise", 6, "2026-09-13", "Spanish GP", "Upcoming"),
                ("Teikirise", 5, "2026-08-30", "Australian GP", "Upcoming"),
            ]
        )

        defaults = ui.infer_admin_defaults(pd.concat([old, current]), calendar)

        self.assertTrue(defaults.confident)
        self.assertEqual(
            defaults.championship,
            ("F1 25: 2026 Season pack", "2026-T02", "Teikirise"),
        )
        self.assertEqual(defaults.event.round_number, 5)
        self.assertEqual(defaults.event.gp_name, "Australian GP")
        self.assertEqual(defaults.event.event_date.isoformat(), "2026-08-30")
        self.assertEqual(defaults.event.event_type, "R")

    def test_stale_upcoming_race_already_in_standings_is_skipped(self):
        standings = standings_rows(
            "F1 25",
            "2026-T01",
            "League",
            [(1, "British GP", "R")],
        )
        calendar = calendar_rows(
            [
                ("League", 1, "2026-08-01", "British GP", "Upcoming"),
                ("League", 2, "2026-08-15", "Belgian GP", "Upcoming"),
            ]
        )

        defaults = ui.infer_admin_defaults(standings, calendar)

        self.assertTrue(defaults.confident)
        self.assertEqual(defaults.event.round_number, 2)
        self.assertEqual(defaults.event.gp_name, "Belgian GP")

    def test_sprint_already_present_keeps_same_round_and_defaults_to_race(self):
        standings = standings_rows(
            "F1 25",
            "2026-T01",
            "League",
            [(2, "British GP", "SR")],
        )
        calendar = calendar_rows(
            [("League", 2, "2026-08-15", "British GP", "Upcoming")]
        )

        defaults = ui.infer_admin_defaults(standings, calendar)

        self.assertTrue(defaults.confident)
        self.assertEqual(defaults.event.round_number, 2)
        self.assertEqual(defaults.event.event_type, "R")

    def test_two_active_leagues_fail_closed_to_editable_fallback(self):
        one = standings_rows("F1 25", "2026-T01", "League One", [(1, "A GP", "R")])
        two = standings_rows("F1 25", "2026-T01", "League Two", [(1, "B GP", "R")])
        calendar = calendar_rows(
            [
                ("League One", 2, "2026-08-15", "C GP", "Upcoming"),
                ("League Two", 2, "2026-08-16", "D GP", "Upcoming"),
            ]
        )

        defaults = ui.infer_admin_defaults(pd.concat([one, two]), calendar)

        self.assertFalse(defaults.confident)
        self.assertIn(defaults.championship, ui._championship_options(pd.concat([one, two])))

    def test_reused_league_name_and_duplicate_calendar_identity_fail_closed(self):
        old = standings_rows("F1 25", "2025-T01", "League", [(1, "A GP", "R")])
        current = standings_rows("F1 25", "2026-T01", "League", [(1, "A GP", "R")])
        duplicated = calendar_rows(
            [
                ("League", 2, "2026-08-15", "B GP", "Upcoming"),
                ("League", 2, "2026-08-15", "B GP", "Upcoming"),
            ]
        )

        defaults = ui.infer_admin_defaults(pd.concat([old, current]), duplicated)

        self.assertFalse(defaults.confident)
        self.assertFalse(defaults.event.confident)

    def test_missing_calendar_uses_editable_next_round_fallback(self):
        standings = standings_rows(
            "F1 25",
            "2026-T01",
            "League",
            [(3, "British GP", "R")],
        )

        defaults = ui.infer_admin_defaults(standings, core.empty_calendar())

        self.assertFalse(defaults.confident)
        self.assertEqual(defaults.event.round_number, 4)
        self.assertEqual(defaults.event.gp_name, "")

    def test_malformed_calendar_rows_do_not_create_an_automatic_identity(self):
        standings = standings_rows(
            "F1 25",
            "2026-T01",
            "League",
            [(3, "British GP", "R")],
        )
        malformed = pd.DataFrame(
            [
                {
                    "League Name": "League",
                    "Round": pd.NA,
                    "GP Name": "",
                    "Status": "Upcoming",
                }
            ]
        )

        defaults = ui.infer_admin_defaults(standings, malformed)

        self.assertFalse(defaults.confident)
        self.assertEqual(defaults.event.round_number, 4)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.expanded: list[bool] = []
        self.number_values: list[int] = []
        self.radio_indices: list[int] = []
        self.warnings: list[str] = []

    def expander(self, _label, *, expanded=False):
        self.expanded.append(bool(expanded))
        return nullcontext()

    def caption(self, *_args, **_kwargs):
        return None

    def warning(self, message, **_kwargs):
        self.warnings.append(str(message))

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [nullcontext() for _ in range(count)]

    def selectbox(self, _label, options, *, index=0, **_kwargs):
        return options[index]

    def number_input(self, _label, *, value, **_kwargs):
        self.number_values.append(int(value))
        return value

    def text_input(self, _label, *, value, **_kwargs):
        return value

    def radio(self, _label, options, *, index=0, **_kwargs):
        self.radio_indices.append(index)
        return options[index]


class AdminDefaultUiTests(unittest.TestCase):
    def setUp(self):
        self.standings = standings_rows(
            "F1 25",
            "2026-T01",
            "League",
            [(1, "British GP", "R")],
        )
        self.calendar = calendar_rows(
            [("League", 2, "2026-08-30", "Australian GP", "Upcoming")]
        )

    def test_controls_are_collapsed_and_preselected_on_confident_context(self):
        fake = _FakeStreamlit()
        with patch.object(ui, "st", fake):
            rendered = ui._render_event_filters(
                self.standings,
                self.calendar,
                lang="en",
                source_token="source1",
            )

        self.assertEqual(fake.expanded, [False])
        self.assertEqual(fake.number_values, [2])
        self.assertEqual(fake.radio_indices, [0])
        self.assertEqual(rendered.gp_name, "Australian GP")
        self.assertEqual(rendered.event_type, "R")
        self.assertEqual(fake.warnings, [])

    def test_unanimous_sprint_override_preselects_sprint_without_manual_filter_change(self):
        fake = _FakeStreamlit()
        with patch.object(ui, "st", fake):
            first = ui._render_event_filters(
                self.standings,
                self.calendar,
                lang="en",
                source_token="source1",
            )
            fake.session_state[first.session_override_key] = "SR"
            second = ui._render_event_filters(
                self.standings,
                self.calendar,
                lang="en",
                source_token="source1",
            )

        self.assertEqual(fake.radio_indices, [0, 1])
        self.assertEqual(second.event_type, "SR")

    def test_session_synchronization_keeps_the_same_upload_widget_state(self):
        key_before = ui._upload_widget_key(
            "source1",
            "championship1",
            2,
            "Australian GP",
        )
        state = {key_before: [b"screenshot-one", b"screenshot-two"]}
        state["race_import_session_override"] = "SR"
        key_after = ui._upload_widget_key(
            "source1",
            "championship1",
            2,
            "Australian GP",
        )

        self.assertEqual(key_after, key_before)
        self.assertEqual(state[key_after], [b"screenshot-one", b"screenshot-two"])

    def test_success_reset_removes_stale_filters_uploads_and_draft(self):
        state = {
            "race_import_round": 2,
            "race_import_type": "SR",
            "race_import_uploads": [b"image"],
            "race_import_draft": {"rows": []},
            "admin_language": "English",
        }

        ui.reset_import_state_after_success(state, {"message": "Saved"})

        self.assertEqual(state["race_import_success"], {"message": "Saved"})
        self.assertEqual(state["admin_language"], "English")
        self.assertFalse(
            any(key.startswith("race_import_") and key != "race_import_success" for key in state)
        )


class SessionAutoDetectionTests(unittest.TestCase):
    def test_prepare_draft_uses_unanimous_sprint_tab_instead_of_race_default(self):
        uploads = [b"one", b"two"]
        token_sets = [[], []]
        with (
            patch("race_import_ui.race_ocr.extract_tokens", side_effect=token_sets),
            patch(
                "race_import_ui.detect_results_event_type",
                return_value=("SR", ["SR", "SR"]),
            ),
            patch("race_import_ui.validate_results_session_set", return_value=[]) as validate,
            patch("race_import_ui.ri.extract_results_from_tokens", return_value=[]),
            patch("race_import_ui.validate_screenshot_overlap", return_value=[]),
            patch("race_import_ui.ri.merge_screenshot_results", return_value=[]),
            patch("race_import_ui.ri.build_review_rows", return_value=[]),
        ):
            draft = ui._prepare_ocr_draft(
                uploads,
                [],
                require_timing_detail=True,
                expected_event_type="R",
                expected_gp="Australian GP",
                auto_detect_event_type=True,
            )

        self.assertEqual(draft.event_type, "SR")
        self.assertEqual(validate.call_args.args[2], "SR")

    def test_mixed_tabs_are_not_auto_selected(self):
        with patch(
            "race_import_ui.race_ocr.detect_selected_results_tab",
            side_effect=["R", "SR"],
        ):
            detected, tabs = ui.detect_results_event_type([b"one", b"two"], [[], []])

        self.assertIsNone(detected)
        self.assertEqual(tabs, ["R", "SR"])


if __name__ == "__main__":
    unittest.main()
