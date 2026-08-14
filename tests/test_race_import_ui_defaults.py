from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pandas as pd

import dashboard_core as core
import league_config
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

    def test_import_options_hide_managed_draft_and_completed_leagues(self):
        identities = [
            ("active-id", "F1 27", "2027-T01", "Active League", "Active"),
            ("completed-id", "F1 26", "2026-T02", "Completed League", "Completed"),
            ("draft-id", "F1 28", "2028-T01", "Draft League", "Draft"),
        ]
        tables = league_config.ConfigTables(
            pd.DataFrame(
                [
                    [league_id, game, season, league, status, "", "2026-08-14T12:00:00Z", 1]
                    for league_id, game, season, league, status in identities
                ],
                columns=league_config.LEAGUE_CONFIG_COLUMNS,
            ),
            pd.DataFrame(
                [
                    [league_id, 1, f"{league_id} Driver", f"{league_id} Team", ""]
                    for league_id, *_ in identities
                ],
                columns=league_config.ROSTER_CONFIG_COLUMNS,
            ),
            pd.DataFrame(
                [
                    [f"{league_id}:R:1", league_id, "R", 1, 0, None]
                    for league_id, *_ in identities
                ],
                columns=league_config.SCORING_PROFILE_COLUMNS,
            ),
            pd.DataFrame(
                [
                    [f"{league_id}:R:1", 1, 25]
                    for league_id, *_ in identities
                ],
                columns=league_config.SCORING_POINT_COLUMNS,
            ),
        )
        league_config.validate_config_tables(tables)
        historical = pd.concat(
            [
                standings_rows(
                    "F1 26", "2026-T02", "Completed League", [(1, "Old GP", "R")]
                ),
                standings_rows(
                    "F1 25", "2025-T01", "Unmanaged Legacy", [(1, "Legacy GP", "R")]
                ),
            ],
            ignore_index=True,
        )

        options = ui._championship_options(historical, tables)

        self.assertIn(("F1 27", "2027-T01", "Active League"), options)
        self.assertIn(("F1 25", "2025-T01", "Unmanaged Legacy"), options)
        self.assertNotIn(("F1 26", "2026-T02", "Completed League"), options)
        self.assertNotIn(("F1 28", "2028-T01", "Draft League"), options)

    def test_done_configured_race_with_undone_sprint_defaults_to_sprint_recovery(self):
        league_id = "active-sprint-recovery"
        game = "F1 27"
        season = "2027-T01"
        league = "Sprint Recovery League"
        tables = league_config.ConfigTables(
            pd.DataFrame(
                [[league_id, game, season, league, "Active", "", "2026-08-14T12:00:00Z", 1]],
                columns=league_config.LEAGUE_CONFIG_COLUMNS,
            ),
            pd.DataFrame(
                [[league_id, 1, "Driver One", "Team One", ""]],
                columns=league_config.ROSTER_CONFIG_COLUMNS,
            ),
            pd.DataFrame(
                [
                    [f"{league_id}:R:1", league_id, "R", 1, 0, None],
                    [f"{league_id}:SR:1", league_id, "SR", 1, 0, None],
                ],
                columns=league_config.SCORING_PROFILE_COLUMNS,
            ),
            pd.DataFrame(
                [
                    [f"{league_id}:R:1", 1, 25],
                    [f"{league_id}:SR:1", 1, 8],
                ],
                columns=league_config.SCORING_POINT_COLUMNS,
            ),
        )
        league_config.validate_config_tables(tables)
        # This is the exact post-Undo state: the complete Race remains, the
        # configured Sprint is absent, and Race publication keeps Calendar Done.
        standings = standings_rows(
            game, season, league, [(1, "British GP", "R")]
        )
        calendar = pd.DataFrame(
            [
                {
                    "League Name": league,
                    "Round": 1,
                    "Date": pd.Timestamp("2027-07-18"),
                    "GP Name": "British GP",
                    "Circuit": "Silverstone",
                    "Status": "Done",
                    "Time (Lisbon)": "15:00",
                    "Game": game,
                    "Season": season,
                    "Has Sprint": True,
                    "League ID": league_id,
                }
            ]
        )

        defaults = ui.infer_admin_defaults(standings, calendar, tables)

        self.assertTrue(defaults.confident)
        self.assertEqual(defaults.championship, (game, season, league))
        self.assertEqual(defaults.event.round_number, 1)
        self.assertEqual(defaults.event.gp_name, "British GP")
        self.assertEqual(defaults.event.event_type, "SR")

        duplicated = pd.concat([calendar, calendar], ignore_index=True)
        ambiguous = ui.infer_admin_defaults(standings, duplicated, tables)
        self.assertFalse(ambiguous.confident)
        self.assertFalse(ambiguous.event.confident)


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

    def test_successful_ocr_can_rotate_upload_widget_without_losing_review_hashes(self):
        key_before = ui._upload_widget_key(
            "source1",
            "championship1",
            2,
            "Australian GP",
        )
        state = {
            key_before: [b"screenshot-one", b"screenshot-two"],
            "race_import_uploads_v2_stale_context_0": [b"stale-screenshot"],
            "race_import_draft": {"screenshot_hashes": ["digest-one", "digest-two"]},
            ui.EXTRACTION_ERROR_KEY: "stale error",
        }
        key_after = ui._upload_widget_key(
            "source1",
            "championship1",
            2,
            "Australian GP",
            generation=1,
        )

        ui.finalize_ocr_attempt(
            state,
            upload_widget_key=key_before,
            upload_generation=0,
        )

        self.assertNotEqual(key_after, key_before)
        self.assertNotIn(key_before, state)
        self.assertFalse(
            any(str(key).startswith("race_import_uploads_v2_") for key in state)
        )
        self.assertEqual(state["race_import_upload_generation"], 1)
        self.assertNotIn(ui.EXTRACTION_ERROR_KEY, state)
        self.assertEqual(
            state["race_import_draft"]["screenshot_hashes"],
            ["digest-one", "digest-two"],
        )

    def test_failed_ocr_discards_uploads_and_old_review_but_keeps_text_error(self):
        current_key = ui._upload_widget_key(
            "source1",
            "championship1",
            2,
            "Australian GP",
            generation=3,
        )
        state = {
            current_key: [b"screenshot-one", b"screenshot-two"],
            "race_import_uploads_v2_other_context_2": [b"older-screenshot"],
            "race_import_draft": {
                "rows": [{"Driver": "Old review"}],
                "screenshot_hashes": ["old-digest"],
            },
            "race_import_detected_notice": "Old session notice",
            "dashboard_filter": "public-state",
        }

        ui.finalize_ocr_attempt(
            state,
            upload_widget_key=current_key,
            upload_generation=3,
            error_message="The selected screenshots could not be reconciled.",
        )

        self.assertFalse(
            any(str(key).startswith("race_import_uploads_v2_") for key in state)
        )
        self.assertNotIn("race_import_draft", state)
        self.assertNotIn("race_import_detected_notice", state)
        self.assertEqual(state["race_import_upload_generation"], 4)
        self.assertEqual(
            state[ui.EXTRACTION_ERROR_KEY],
            "The selected screenshots could not be reconciled.",
        )
        self.assertIsInstance(state[ui.EXTRACTION_ERROR_KEY], str)
        self.assertNotIn("b'screenshot", repr(state).casefold())
        self.assertNotIn("b'older-screenshot", repr(state).casefold())
        self.assertEqual(state["dashboard_filter"], "public-state")

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

    def test_config_only_active_league_is_automatically_selected_for_its_first_event(self):
        setup = league_config.LeagueSetup(
            key=league_config.LeagueKey(
                "league-new",
                "F1 27",
                "2027-T01",
                "New League",
            ),
            calendar=(
                league_config.CalendarRound(
                    1,
                    pd.Timestamp("2027-03-14").date(),
                    "Australian GP",
                    "Albert Park",
                ),
            ),
            roster=(
                league_config.RosterChange(
                    "league-new", 1, "New Driver", "New Team"
                ),
            ),
            scoring_profiles=(
                league_config.ScoringProfile(
                    "league-new:R:1", "league-new", "R", 1
                ),
            ),
            scoring_points=(
                league_config.ScoringPoint("league-new:R:1", 1, 25),
            ),
            status="Active",
        )
        tables = league_config.config_tables_from_setup(setup)
        calendar = pd.DataFrame(
            [
                {
                    "League Name": "New League",
                    "Round": 1,
                    "Date": pd.Timestamp("2027-03-14"),
                    "GP Name": "Australian GP",
                    "Circuit": "Albert Park",
                    "Status": "Upcoming",
                    "Time (Lisbon)": "06:00",
                    "Game": "F1 27",
                    "Season": "2027-T01",
                    "Has Sprint": False,
                    "League ID": "league-new",
                }
            ]
        )

        defaults = ui.infer_admin_defaults(self.standings, calendar, tables)

        self.assertTrue(defaults.confident)
        self.assertEqual(defaults.championship, ("F1 27", "2027-T01", "New League"))
        self.assertEqual(defaults.event.round_number, 1)
        self.assertEqual(defaults.event.gp_name, "Australian GP")


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
