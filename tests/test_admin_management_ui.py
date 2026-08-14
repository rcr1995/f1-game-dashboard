from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
import time as clock
from unittest.mock import Mock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import admin_auth
import admin_management_ui as ui
import league_config
import league_workbook
import race_github
import race_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
GITHUB_SECRETS = {
    "github": {
        "owner": "example-owner",
        "repository": "example-repository",
        "branch": "main",
        "workbook_path": "F1_Standings.xlsx",
        "app_id": "123",
        "installation_id": 456,
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-only\n-----END RSA PRIVATE KEY-----",
    }
}


class AdminManagementRoutingTests(unittest.TestCase):
    def call_router(self, selected: str, **renderers: Mock) -> None:
        with patch.object(ui.st, "radio", return_value=selected):
            ui.render_admin_management(
                "F1_Standings.xlsx",
                pd.DataFrame(),
                pd.DataFrame(),
                lang="en",
                clear_data_cache=Mock(),
                source_version="a" * 40,
                import_publisher=Mock(),
                setup_publisher=Mock(),
                correction_publisher=Mock(),
                dashboard_url="https://example.test/",
                **renderers,
            )

    def test_import_section_executes_only_import_renderer(self):
        renderers = {
            "import_renderer": Mock(),
            "setup_renderer": Mock(),
            "correction_renderer": Mock(),
        }
        self.call_router(ui.IMPORT_SECTION, **renderers)
        renderers["import_renderer"].assert_called_once()
        renderers["setup_renderer"].assert_not_called()
        renderers["correction_renderer"].assert_not_called()

    def test_setup_section_executes_only_setup_renderer(self):
        renderers = {
            "import_renderer": Mock(),
            "setup_renderer": Mock(),
            "correction_renderer": Mock(),
        }
        self.call_router(ui.SETUP_SECTION, **renderers)
        renderers["import_renderer"].assert_not_called()
        renderers["setup_renderer"].assert_called_once()
        renderers["correction_renderer"].assert_not_called()

    def test_correction_section_executes_only_correction_renderer(self):
        renderers = {
            "import_renderer": Mock(),
            "setup_renderer": Mock(),
            "correction_renderer": Mock(),
        }
        self.call_router(ui.CORRECTION_SECTION, **renderers)
        renderers["import_renderer"].assert_not_called()
        renderers["setup_renderer"].assert_not_called()
        renderers["correction_renderer"].assert_called_once()

    def test_every_workflow_state_prefix_is_cleared_by_existing_logout_rule(self):
        self.assertTrue(ui.SECTION_KEY.startswith("race_import_"))
        self.assertTrue(ui.SETUP_PREFIX.startswith("race_import_"))
        self.assertTrue(ui.CORRECTION_PREFIX.startswith("race_import_"))


class AdminPageSetupCallbackTests(unittest.TestCase):
    def test_admin_language_inherits_and_synchronizes_dashboard_widget_state(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        with (
            patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.AUTHORIZED,
            ),
            patch(
                "admin_auth.current_claims",
                return_value={"email": "admin@example.com"},
            ),
            patch("admin_auth.is_current_admin", return_value=True),
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="a" * 40,
                ),
            ),
            patch("admin_management_ui.render_admin_management") as render,
            patch(
                "tempfile.TemporaryDirectory",
                side_effect=lambda *args, **kwargs: nullcontext(
                    str(TEST_TEMP_ROOT)
                ),
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.session_state["app_lang"] = "English"
            app.session_state["app_lang_selector"] = "English"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual("en", render.call_args.kwargs["lang"])

            app.selectbox(key="admin_language").set_value(
                "Português (Portugal)"
            )
            app.run()

        self.assertFalse(app.exception)
        self.assertEqual("Português (Portugal)", app.session_state["app_lang"])
        self.assertEqual(
            "Português (Portugal)",
            app.session_state["app_lang_selector"],
        )
        self.assertEqual("pt", render.call_args.kwargs["lang"])

    def test_callback_rebuilds_new_and_roster_drafts_after_authorization(self):
        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        for mode in ("new", "roster"):
            with self.subTest(mode=mode):
                draft = {
                    "identity": {"mode": mode},
                    "source_version": "a" * 40,
                }
                mutation = object()
                publish_result = SimpleNamespace(commit_url="https://example.test/commit")

                def render(*_args, **kwargs):
                    self.assertEqual("en", kwargs["lang"])
                    callback = kwargs["setup_publisher"]
                    self.assertIs(
                        publish_result,
                        callback(draft, "a" * 40, True),
                    )

                with (
                    patch(
                        "admin_auth.current_admin_state",
                        return_value=admin_auth.AdminState.AUTHORIZED,
                    ),
                    patch(
                        "admin_auth.current_claims",
                        return_value={"email": "admin@example.com"},
                    ),
                    patch("admin_auth.is_current_admin", return_value=True),
                    patch(
                        "race_github.fetch_remote_workbook",
                        return_value=race_github.RemoteWorkbook(
                            content=workbook_content,
                            blob_sha="a" * 40,
                        ),
                    ),
                    patch(
                        "admin_management_ui.build_setup_publication",
                        return_value=mutation,
                    ) as build,
                    patch(
                        "race_github.publish_league_workbook_update",
                        return_value=publish_result,
                    ) as publish,
                    patch(
                        "admin_management_ui.render_admin_management",
                        side_effect=render,
                    ),
                    patch(
                        "tempfile.TemporaryDirectory",
                        side_effect=lambda *args, **kwargs: nullcontext(
                            str(TEST_TEMP_ROOT)
                        ),
                    ),
                ):
                    app = AppTest.from_file("admin_page.py", default_timeout=60)
                    app.secrets = GITHUB_SECRETS
                    app.session_state["app_lang"] = "English"
                    app.run()

                self.assertFalse(app.exception)
                build.assert_called_once()
                self.assertIs(build.call_args.args[0], draft)
                publish.assert_called_once()
                self.assertIs(publish.call_args.kwargs["mutation"], mutation)
                self.assertEqual(
                    "a" * 40, publish.call_args.kwargs["expected_blob_sha"]
                )
                self.assertTrue(publish.call_args.kwargs["approved"])

    def test_correction_publisher_accepts_legacy_six_field_metadata_cache(self):
        @dataclass(frozen=True)
        class LegacyRaceMetadata:
            game: str
            season: str
            league: str
            round_number: int
            event_type: str
            gp_name: str

        workbook_content = (PROJECT_ROOT / "F1_Standings.xlsx").read_bytes()
        publish_result = SimpleNamespace(
            commit_url="https://example.test/correction"
        )
        request = {
            "source_version": "a" * 40,
            "operation": "replace",
            "event": {
                "game": "F1 25",
                "season": "2026-T02",
                "league": "Teikirise",
                "round": 3,
                "type": "R",
                "gp": "British Grand Prix",
                "league_id": "league-teikirise",
            },
            "authoritative_roster": [],
            "authoritative_scoring": {},
            "expected_event_digest": "e" * 64,
            "new_rows": [],
        }

        def legacy_factory(event, **_kwargs):
            return race_metadata.make_race_metadata(
                game=event["game"],
                season=event["season"],
                league=event["league"],
                round_number=event["round"],
                event_type=event["type"],
                gp_name=event["gp"],
                league_id=event["league_id"],
                metadata_class=LegacyRaceMetadata,
            )

        def render(*_args, **kwargs):
            result = kwargs["correction_publisher"](
                request, "a" * 40, True
            )
            self.assertIs(result, publish_result)

        with (
            patch(
                "admin_auth.current_admin_state",
                return_value=admin_auth.AdminState.AUTHORIZED,
            ),
            patch(
                "admin_auth.current_claims",
                return_value={"email": "admin@example.com"},
            ),
            patch("admin_auth.is_current_admin", return_value=True),
            patch(
                "race_github.fetch_remote_workbook",
                return_value=race_github.RemoteWorkbook(
                    content=workbook_content,
                    blob_sha="a" * 40,
                ),
            ),
            patch(
                "race_metadata.from_event_mapping",
                side_effect=legacy_factory,
            ),
            patch(
                "race_github.publish_event_correction",
                return_value=publish_result,
            ) as publish,
            patch(
                "admin_management_ui.render_admin_management",
                side_effect=render,
            ),
            patch(
                "tempfile.TemporaryDirectory",
                side_effect=lambda *args, **kwargs: nullcontext(
                    str(TEST_TEMP_ROOT)
                ),
            ),
        ):
            app = AppTest.from_file("admin_page.py", default_timeout=60)
            app.secrets = GITHUB_SECRETS
            app.session_state["app_lang"] = "English"
            app.run()

        self.assertFalse(app.exception)
        metadata = publish.call_args.kwargs["metadata"]
        self.assertEqual("league-teikirise", metadata.league_id)
        self.assertEqual(3, metadata.round_number)


class AdminManagementPureHelperTests(unittest.TestCase):
    def standings(self) -> pd.DataFrame:
        rows = []
        for position, driver in enumerate(("Alice", "Bob", "Cara"), start=1):
            rows.append(
                {
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "SeasonLabel": "2026-T02",
                    "League Name": "League A",
                    "Round": 2,
                    "GP Name": "Australian GP",
                    "Type": "R",
                    "Driver": driver,
                    "Team": f"Team {position}",
                    "Finish Pos": position,
                    "Points": 4 - position,
                    "IsSeasonFinal": False,
                }
            )
        return pd.DataFrame(rows)

    def test_published_events_include_only_complete_unique_results(self):
        standings = self.standings()
        events = ui._published_events(standings)
        self.assertEqual(1, len(events))
        self.assertEqual("Australian GP", events[0]["gp"])

        standings.loc[1, "Finish Pos"] = 1
        self.assertEqual([], ui._published_events(standings))

    def test_published_event_uses_exact_calendar_league_id(self):
        standings = self.standings()
        calendar = pd.DataFrame(
            [
                {
                    "League Name": "League A",
                    "Round": 2,
                    "GP Name": "Australian GP",
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "League ID": "league-a",
                }
            ]
        )
        events = ui._published_events(standings, calendar)
        self.assertEqual("league-a", events[0]["league_id"])

        ambiguous = pd.concat([calendar, calendar], ignore_index=True)
        self.assertEqual([], ui._published_events(standings, ambiguous))

    def test_event_rows_are_bound_to_full_identity(self):
        standings = self.standings()
        event = ui._published_events(standings)[0]
        selected = ui._event_rows(standings, event)
        self.assertEqual([1, 2, 3], selected["Finish Pos"].tolist())
        self.assertEqual(["Alice", "Bob", "Cara"], selected["Driver"].tolist())

    def test_approval_digest_changes_with_source_or_review(self):
        review = {"source_version": "a" * 40, "rows": [{"Driver": "Alice"}]}
        first = ui._digest(review)
        changed_source = ui._digest({**review, "source_version": "b" * 40})
        changed_row = ui._digest(
            {"source_version": "a" * 40, "rows": [{"Driver": "Bob"}]}
        )
        self.assertNotEqual(first, changed_source)
        self.assertNotEqual(first, changed_row)

    def test_roster_change_clears_every_dependent_editor_and_review(self):
        state = {
            f"{ui.SETUP_PREFIX}race_scoring": [{"Position": 1, "Points": 25}],
            f"{ui.SETUP_PREFIX}sprint_scoring": [{"Position": 1, "Points": 8}],
            f"{ui.SETUP_PREFIX}bonuses": {"R": {"enabled": True}},
            f"{ui.SETUP_PREFIX}calendar": [{"Round": 1}],
            f"{ui.SETUP_PREFIX}race_scoring_editor_old": object(),
            f"{ui.SETUP_PREFIX}bonus_points_R_old": 1.0,
            f"{ui.SETUP_PREFIX}identity": {"mode": "new"},
        }
        changed = ui._reset_roster_dependents(
            state,
            [{"Driver": "Alice", "Team": "Red"}],
            [
                {"Driver": "Alice", "Team": "Red"},
                {"Driver": "Bob", "Team": "Blue"},
            ],
        )

        self.assertTrue(changed)
        self.assertEqual(
            {f"{ui.SETUP_PREFIX}identity": {"mode": "new"}}, state
        )

    def test_unchanged_roster_preserves_submitted_downstream_state(self):
        roster = [{"Driver": "Alice", "Team": "Red"}]
        state = {f"{ui.SETUP_PREFIX}race_scoring": [{"Position": 1, "Points": 25}]}

        self.assertFalse(ui._reset_roster_dependents(state, roster, roster))
        self.assertIn(f"{ui.SETUP_PREFIX}race_scoring", state)

    def test_failed_correction_ocr_discards_uploads_and_stale_review(self):
        upload_key = f"{ui.CORRECTION_PREFIX}uploads_current_2"
        generation_key = f"{ui.CORRECTION_PREFIX}upload_generation"
        draft_key = f"{ui.CORRECTION_PREFIX}draft"
        error_key = f"{ui.CORRECTION_PREFIX}extract_error"
        state = {
            upload_key: [b"new-image-one", b"new-image-two"],
            f"{ui.CORRECTION_PREFIX}uploads_stale_1": [b"old-image"],
            generation_key: 2,
            draft_key: {"rows": [{"Driver": "Old review"}]},
            "public_filter": "unchanged",
        }

        ui._finalize_correction_ocr_attempt(
            state,
            upload_key=upload_key,
            upload_generation_key=generation_key,
            upload_generation=2,
            draft_key=draft_key,
            error_key=error_key,
            error_message="The screenshots did not agree.",
        )

        self.assertFalse(
            any(
                str(key).startswith(f"{ui.CORRECTION_PREFIX}uploads_")
                for key in state
            )
        )
        self.assertNotIn(draft_key, state)
        self.assertEqual(3, state[generation_key])
        self.assertEqual("The screenshots did not agree.", state[error_key])
        self.assertNotIn("b'new-image", repr(state).casefold())
        self.assertEqual("unchanged", state["public_filter"])

    def test_successful_correction_ocr_keeps_review_but_no_uploads(self):
        upload_key = f"{ui.CORRECTION_PREFIX}uploads_current_0"
        generation_key = f"{ui.CORRECTION_PREFIX}upload_generation"
        draft_key = f"{ui.CORRECTION_PREFIX}draft"
        error_key = f"{ui.CORRECTION_PREFIX}extract_error"
        state = {
            upload_key: [b"image-one", b"image-two"],
            draft_key: {
                "screenshot_hashes": ["digest-one", "digest-two"],
                "rows": [{"Driver": "Reviewed"}],
            },
            error_key: "old error",
        }

        ui._finalize_correction_ocr_attempt(
            state,
            upload_key=upload_key,
            upload_generation_key=generation_key,
            upload_generation=0,
            draft_key=draft_key,
            error_key=error_key,
            error_message=None,
        )

        self.assertNotIn(upload_key, state)
        self.assertNotIn(error_key, state)
        self.assertEqual(1, state[generation_key])
        self.assertEqual(
            ["digest-one", "digest-two"],
            state[draft_key]["screenshot_hashes"],
        )

    def test_completed_managed_event_offers_replace_only(self):
        event = {"league_id": "managed-one"}
        with (
            patch("league_config.load_config_tables", return_value=object()),
            patch(
                "league_config.configured_league_status",
                return_value="Completed",
            ),
        ):
            operations, status = ui._correction_operations("unused.xlsx", event)

        self.assertEqual(("replace",), operations)
        self.assertEqual("Completed", status)
        self.assertEqual(
            (("replace", "undo"), None),
            ui._correction_operations("unused.xlsx", {"league_id": ""}),
        )

    def test_new_identity_duplicate_check_is_case_and_whitespace_insensitive(self):
        options = ui._championships(self.standings())
        self.assertEqual([("F1 25", "2026-T02", "League A")], options)
        normalized = {
            (game.casefold(), season.casefold(), league.casefold())
            for game, season, league in options
        }
        self.assertIn(("f1 25", "2026-t02", "league a"), normalized)

    def test_configured_roster_clone_preserves_canonical_ocr_aliases(self):
        key = league_config.LeagueKey(
            "league-a", "F1 25", "2026-T02", "League A"
        )
        tables = SimpleNamespace(
            roster_config=pd.DataFrame(
                [
                    {
                        "League ID": "league-a",
                        "Effective From Round": 1,
                    }
                ]
            )
        )
        configured = (
            league_config.RosterChange(
                "league-a",
                1,
                "Alice",
                "Team A",
                ("A. Lice", "Alice Game"),
            ),
        )
        identity = {
            "mode": "new",
            "source": ["F1 25", "2026-T02", "League A"],
        }
        with (
            patch("league_config.load_config_tables", return_value=tables),
            patch("league_config.configured_league_keys", return_value=(key,)),
            patch(
                "league_config.resolve_roster_snapshot",
                return_value=configured,
            ),
        ):
            cloned = ui._source_rows(
                "unused.xlsx", pd.DataFrame(), identity
            )

        self.assertEqual("A. Lice | Alice Game", cloned.iloc[0]["OCR Aliases"])

    def test_legacy_roster_clone_starts_with_blank_aliases(self):
        identity = {
            "mode": "new",
            "source": ["F1 25", "2026-T02", "League A"],
        }
        with patch(
            "league_config.load_config_tables", side_effect=ValueError("legacy")
        ):
            cloned = ui._source_rows(
                "unused.xlsx", self.standings(), identity
            )
        self.assertTrue(cloned["OCR Aliases"].eq("").all())

    def test_alias_text_is_canonical_and_collisions_are_friendly(self):
        self.assertEqual(
            "A. Lice | Alice Game",
            ui._canonical_alias_text(
                " A. Lice ; Alice Game | alice game "
            ),
        )
        errors = ui._roster_alias_errors(
            [
                {"Driver": "Alice", "Team": "Red", "OCR Aliases": "Bob"},
                {
                    "Driver": "Bob",
                    "Team": "Blue",
                    "OCR Aliases": "Shared",
                },
                {
                    "Driver": "Cara",
                    "Team": "Green",
                    "OCR Aliases": "shared",
                },
            ]
        )
        self.assertTrue(any("matches driver Bob" in error for error in errors))
        self.assertTrue(any("more than one driver" in error for error in errors))

    def test_next_season_code_uses_start_year_and_highest_existing_suffix(self):
        championships = (
            ("F1 26", "2026-T01", "League One"),
            ("F1 26", "2026-T02", "League Two"),
            ("F1 26", "2025-T04", "Older League"),
        )
        self.assertEqual(
            "2026-T03",
            ui.derive_next_season_code(date(2026, 8, 20), championships),
        )
        self.assertEqual(
            "2027-T01",
            ui.derive_next_season_code(date(2027, 1, 5), championships),
        )

    def test_current_workbook_next_2026_season_is_t03(self):
        import dashboard_core

        workbook_path = PROJECT_ROOT / "F1_Standings.xlsx"
        standings = dashboard_core.load_standings_data(workbook_path)
        calendar = dashboard_core.load_calendar_data(workbook_path)
        identities = ui._season_code_championships(
            str(workbook_path), standings, calendar
        )
        self.assertEqual(
            "2026-T03",
            ui.derive_next_season_code(date(2026, 9, 1), identities),
        )

    def test_next_season_code_advances_across_a_historical_gap(self):
        self.assertEqual(
            "2026-T04",
            ui.derive_next_season_code(
                date(2026, 9, 1),
                (
                    ("F1 26", "2026-T01", "League One"),
                    ("F1 26", "2026-T03", "League Three"),
                ),
            ),
        )

    def test_next_season_code_fails_closed_on_ambiguous_or_malformed_history(self):
        with self.assertRaisesRegex(ValueError, "multiple championship"):
            ui.derive_next_season_code(
                date(2026, 9, 1),
                (
                    ("F1 26", "2026-T01", "League One"),
                    ("F1 26", "2026-T01", "Different League"),
                ),
            )
        with self.assertRaisesRegex(ValueError, "does not use YYYY-TNN"):
            ui.derive_next_season_code(
                date(2026, 9, 1),
                (("F1 26", "2026-SECOND", "Broken League"),),
            )

    def test_calendar_only_managed_identity_is_included_in_season_scan(self):
        calendar = pd.DataFrame(
            [
                {
                    "Game": "F1 26",
                    "Season": "2026-T02",
                    "League Name": "Calendar Only",
                    "League ID": "league-calendar-only",
                }
            ]
        )
        with patch(
            "league_config.load_config_tables", side_effect=ValueError("legacy")
        ):
            identities = ui._season_code_championships(
                "unused.xlsx", pd.DataFrame(), calendar
            )
        self.assertIn(
            ("F1 26", "2026-T02", "id:league-calendar-only"), identities
        )

    def test_admin_management_translations_have_complete_matching_keys(self):
        self.assertEqual(set(ui._COPY["en"]), set(ui._COPY["pt"]))
        self.assertEqual(
            "Define future driver–team lineup",
            ui._text("en", "roster_change"),
        )
        self.assertEqual(
            "Definir grelha futura de pilotos e equipas",
            ui._text("pt", "roster_change"),
        )
        self.assertEqual(
            "Corrected event screenshots",
            ui._text("en", "corrected_uploads"),
        )

    def test_legacy_six_field_metadata_keeps_managed_id_without_type_error(self):
        @dataclass(frozen=True)
        class LegacyRaceMetadata:
            game: str
            season: str
            league: str
            round_number: int
            event_type: str
            gp_name: str

        metadata = ui.event_metadata_from_mapping(
            {
                "game": "F1 26",
                "season": "2026-T02",
                "league": "League Two",
                "round": 3,
                "type": "R",
                "gp": "British Grand Prix",
                "league_id": "league-two",
            },
            metadata_class=LegacyRaceMetadata,
        )
        self.assertEqual("league-two", metadata.league_id)
        self.assertEqual(3, metadata.round_number)

    def test_managed_writer_guard_reloads_stale_module_and_fails_closed(self):
        @dataclass(frozen=True)
        class LegacyRaceMetadata:
            game: str
            season: str
            league: str
            round_number: int
            event_type: str
            gp_name: str

        stale = SimpleNamespace(
            RACE_METADATA_API_VERSION=0,
            RaceMetadata=LegacyRaceMetadata,
        )
        current = SimpleNamespace(
            RACE_METADATA_API_VERSION=2,
            RaceMetadata=__import__("race_workbook").RaceMetadata,
        )
        with patch("race_metadata.importlib.reload", return_value=current) as reload:
            self.assertIs(
                current, race_metadata.ensure_current_race_workbook(stale)
            )
        reload.assert_called_once_with(stale)

        with patch("race_metadata.importlib.reload", return_value=stale):
            with self.assertRaisesRegex(RuntimeError, "does not support"):
                race_metadata.ensure_current_race_workbook(stale)

    def test_managed_writer_reload_is_serialized_and_rechecked_inside_lock(self):
        @dataclass(frozen=True)
        class LegacyRaceMetadata:
            game: str
            season: str
            league: str
            round_number: int
            event_type: str
            gp_name: str

        stale = SimpleNamespace(
            RACE_METADATA_API_VERSION=0,
            RaceMetadata=LegacyRaceMetadata,
        )

        def refresh(module):
            clock.sleep(0.05)
            module.RACE_METADATA_API_VERSION = 2
            module.RaceMetadata = __import__("race_workbook").RaceMetadata
            return module

        with patch(
            "race_metadata.importlib.reload", side_effect=refresh
        ) as reload:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        race_metadata.ensure_current_race_workbook,
                        [stale] * 4,
                    )
                )

        self.assertTrue(all(result is stale for result in results))
        self.assertEqual(1, reload.call_count)

    def test_correction_selection_survives_legacy_six_field_cache(self):
        @dataclass(frozen=True)
        class LegacyRaceMetadata:
            game: str
            season: str
            league: str
            round_number: int
            event_type: str
            gp_name: str

        event = {
            "game": "F1 26",
            "season": "2026-T02",
            "league": "League Two",
            "round": 3,
            "type": "R",
            "gp": "British Grand Prix",
            "league_id": "league-two",
        }
        snapshot = SimpleNamespace(rows=(), digest="d" * 64)
        replacement = Mock()
        with (
            patch.object(ui.st, "session_state", {}),
            patch.object(ui.st, "header"),
            patch.object(ui.st, "write"),
            patch.object(ui.st, "subheader"),
            patch.object(ui.st, "dataframe"),
            patch.object(ui.st, "selectbox", return_value=event),
            patch.object(ui.st, "radio", return_value="replace"),
            patch.object(ui, "_published_events", return_value=[event]),
            patch.object(
                ui,
                "_correction_operations",
                return_value=(("replace",), "Active"),
            ),
            patch(
                "race_metadata.ensure_current_race_workbook",
                return_value=SimpleNamespace(RaceMetadata=LegacyRaceMetadata),
            ),
            patch(
                "race_correction.load_event_snapshot",
                return_value=snapshot,
            ),
            patch.object(
                ui, "_render_replace_correction", replacement
            ),
        ):
            ui.render_event_correction(
                "unused.xlsx",
                pd.DataFrame(),
                pd.DataFrame(),
                lang="en",
                clear_data_cache=Mock(),
                source_version="a" * 40,
                hosted_publisher=Mock(),
            )

        metadata = replacement.call_args.kwargs["metadata"]
        self.assertEqual("league-two", metadata.league_id)
        self.assertEqual(3, metadata.round_number)

    def test_every_production_metadata_constructor_uses_guarded_factory(self):
        for filename in (
            "admin_page.py",
            "admin_management_ui.py",
            "race_import_ui.py",
            "race_correction.py",
        ):
            with self.subTest(filename=filename):
                source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("RaceMetadata(", source)
                self.assertIn("race_metadata", source)

    def test_new_league_name_is_globally_unique_across_history(self):
        draft = {
            "identity": {
                "mode": "new",
                "source": ["F1 25", "2026-T02", "League A"],
                "game": "F1 26",
                "season": "2027-T01",
                "league": "  LEAGUE   A ",
                "created_utc": "2026-08-14T12:00:00Z",
            },
            "roster": [],
        }
        with self.assertRaisesRegex(ValueError, "unique across every"):
            ui.build_setup_publication(
                draft,
                str(PROJECT_ROOT / "F1_Standings.xlsx"),
                self.standings(),
            )

    def test_new_league_mutation_rejects_alias_matching_another_driver(self):
        draft = {
            "identity": {
                "mode": "new",
                "source": ["F1 25", "2026-T02", "League A"],
                "game": "F1 26",
                "season": "2027-T01",
                "league": "Alias Collision League",
                "created_utc": "2026-08-14T12:00:00Z",
            },
            "roster": [
                {
                    "Driver": "Alice",
                    "Team": "Red",
                    "OCR Aliases": "Bob",
                },
                {"Driver": "Bob", "Team": "Blue", "OCR Aliases": ""},
            ],
            "scoring": {
                "R": [
                    {"Position": 1, "Points": 2.0},
                    {"Position": 2, "Points": 1.0},
                ],
                "SR": [
                    {"Position": 1, "Points": 1.0},
                    {"Position": 2, "Points": 0.0},
                ],
            },
            "fastest_lap": {
                "R": {
                    "enabled": False,
                    "points": 0.0,
                    "eligibility_max_position": 0,
                },
                "SR": {
                    "enabled": False,
                    "points": 0.0,
                    "eligibility_max_position": 0,
                },
            },
            "calendar": [
                {
                    "Round": 1,
                    "Date": date(2027, 1, 10),
                    "GP Name": "Australian GP",
                    "Circuit": "Melbourne",
                    "Status": "Upcoming",
                    "Time (Lisbon)": time(20, 0),
                    "Has Sprint": False,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "matches another driver"):
            ui.build_setup_publication(
                draft,
                str(PROJECT_ROOT / "F1_Standings.xlsx"),
                self.standings(),
            )

    def test_new_league_review_builds_one_valid_hashed_mutation(self):
        project_root = Path(__file__).resolve().parents[1]
        draft = {
            "identity": {
                "mode": "new",
                "source": ["F1 25", "2026-T02", "League A"],
                "game": "F1 26",
                "season": "2027-T01",
                "league": "League B",
                "effective_round": 1,
                "created_utc": "2026-08-14T12:00:00Z",
            },
            "roster": [
                {
                    "Driver": "Alice",
                    "Team": "Team A",
                    "OCR Aliases": "A. Lice ; Alice Game",
                },
                {"Driver": "Bob", "Team": "Team B"},
                {"Driver": "Cara", "Team": "Team C"},
            ],
            "scoring": {
                "R": [
                    {"Position": 1, "Points": 3.0},
                    {"Position": 2, "Points": 2.0},
                    {"Position": 3, "Points": 1.0},
                ],
                "SR": [
                    {"Position": 1, "Points": 2.0},
                    {"Position": 2, "Points": 1.0},
                    {"Position": 3, "Points": 0.0},
                ],
            },
            "fastest_lap": {
                "R": {"enabled": True, "points": 1.0, "eligibility_max_position": 3},
                "SR": {"enabled": False, "points": 0.0, "eligibility_max_position": 0},
            },
            "calendar": [
                {
                    "Round": 1,
                    "Date": date(2027, 1, 10),
                    "GP Name": "Australian GP",
                    "Circuit": "Melbourne",
                    "Status": "Upcoming",
                    "Time (Lisbon)": time(20, 0),
                    "Has Sprint": True,
                }
            ],
            "source_version": "a" * 40,
        }
        mutation = ui.build_setup_publication(
            draft,
            str(project_root / "F1_Standings.xlsx"),
            self.standings(),
        )
        repeated = ui.build_setup_publication(
            draft,
            str(project_root / "F1_Standings.xlsx"),
            self.standings(),
        )
        self.assertEqual(1, len(mutation.league_config))
        self.assertEqual(3, len(mutation.roster_config))
        self.assertEqual(2, len(mutation.scoring_profiles))
        self.assertEqual(6, len(mutation.scoring_points))
        self.assertEqual(1, len(mutation.calendar))
        self.assertTrue(str(mutation.league_config[0]["League ID"]).startswith("league-"))
        self.assertTrue(mutation.calendar[0]["Has Sprint"])
        alice = next(
            row for row in mutation.roster_config if row["Driver Name"] == "Alice"
        )
        self.assertEqual("A. Lice | Alice Game", alice["OCR Aliases"])
        self.assertEqual(
            league_workbook.mutation_digest(mutation, source_version="a" * 40),
            league_workbook.mutation_digest(repeated, source_version="a" * 40),
        )

    def test_roster_update_builds_round_effective_scoring_profiles(self):
        key = league_config.LeagueKey(
            "league-a", "F1 25", "2026-T02", "League A"
        )
        tables = SimpleNamespace(
            league_config=pd.DataFrame(
                [{"League ID": "league-a", "Status": "Active"}]
            )
        )
        draft = {
            "identity": {
                "mode": "roster",
                "source": ["F1 25", "2026-T02", "League A"],
                "game": "F1 25",
                "season": "2026-T02",
                "league": "League A",
                "effective_round": 3,
                "created_utc": "2026-08-14T12:00:00Z",
            },
            "roster": [
                {
                    "Driver": "Alice",
                    "Team": "New Team",
                    "OCR Aliases": "A Lice | Alice AI",
                },
                {"Driver": "Bob", "Team": "Team B"},
                {"Driver": "Dana", "Team": "Team D"},
            ],
            "scoring": {
                "R": [
                    {"Position": 1, "Points": 3.0},
                    {"Position": 2, "Points": 2.0},
                    {"Position": 3, "Points": 1.0},
                ],
                "SR": [
                    {"Position": 1, "Points": 2.0},
                    {"Position": 2, "Points": 1.0},
                    {"Position": 3, "Points": 0.0},
                ],
            },
            "fastest_lap": {
                "R": {
                    "enabled": True,
                    "points": 1.0,
                    "eligibility_max_position": 3,
                },
                "SR": {
                    "enabled": False,
                    "points": 0.0,
                    "eligibility_max_position": 0,
                },
            },
            "calendar": [],
            "source_version": "a" * 40,
        }
        with (
            patch("league_config.load_config_tables", return_value=tables),
            patch("league_config.configured_league_keys", return_value=(key,)),
            patch("dashboard_core.load_calendar_data", return_value=pd.DataFrame()),
            patch("admin_management_ui._managed_roster_rounds", return_value=[3]),
            patch("league_config.validate_roster_snapshot_update") as validate,
            patch(
                "league_workbook.mutation_from_roster_snapshot_update",
                side_effect=lambda _existing, update: update,
            ),
        ):
            update = ui.build_setup_publication(
                draft, "unused.xlsx", self.standings()
            )

        validate.assert_called_once()
        self.assertEqual(3, update.effective_from_round)
        self.assertEqual(
            {"league-a:R:3", "league-a:SR:3"},
            {profile.profile_id for profile in update.scoring_profiles},
        )
        self.assertEqual(6, len(update.scoring_points))
        alice = next(
            row for row in update.complete_roster if row.driver_name == "Alice"
        )
        self.assertEqual(("A Lice", "Alice AI"), alice.ocr_aliases)

    def test_roster_update_cannot_rewrite_published_round_authority(self):
        key = league_config.LeagueKey(
            "league-a", "F1 25", "2026-T02", "League A"
        )
        draft = {
            "identity": {
                "mode": "roster",
                "source": ["F1 25", "2026-T02", "League A"],
                "game": "F1 25",
                "season": "2026-T02",
                "league": "League A",
                "effective_round": 2,
            },
            "roster": [{"Driver": "Alice", "Team": "Team A"}],
            "scoring": {"R": [], "SR": []},
            "fastest_lap": {},
        }
        tables = SimpleNamespace(
            league_config=pd.DataFrame(
                [{"League ID": "league-a", "Status": "Active"}]
            )
        )
        with (
            patch("league_config.load_config_tables", return_value=tables),
            patch("league_config.configured_league_keys", return_value=(key,)),
            patch("dashboard_core.load_calendar_data", return_value=pd.DataFrame()),
            patch("admin_management_ui._managed_roster_rounds", return_value=[2]),
        ):
            with self.assertRaisesRegex(ValueError, "already published results"):
                ui.build_setup_publication(
                    draft, "unused.xlsx", self.standings()
                )

    def test_next_roster_round_prefers_next_unpublished_calendar_round(self):
        calendar = pd.DataFrame(
            [
                {
                    "League Name": "League A",
                    "Round": 3,
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "Status": "Upcoming",
                },
                {
                    "League Name": "League A",
                    "Round": 4,
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "Status": "Upcoming",
                },
            ]
        )
        with patch(
            "league_config.load_config_tables", side_effect=ValueError("legacy")
        ):
            value = ui._next_unpublished_round(
                "unused.xlsx",
                self.standings(),
                calendar,
                ("F1 25", "2026-T02", "League A"),
            )
        self.assertEqual(3, value)

    def test_roster_rounds_use_only_exact_managed_upcoming_calendar_rows(self):
        key = league_config.LeagueKey(
            "league-a", "F1 25", "2026-T02", "League A"
        )
        tables = SimpleNamespace(
            league_config=pd.DataFrame(
                [{"League ID": "league-a", "Status": "Active"}]
            ),
            roster_config=pd.DataFrame(
                [{"League ID": "league-a", "Effective From Round": 1}]
            ),
        )
        calendar = pd.DataFrame(
            [
                {
                    "League ID": "league-a",
                    "League Name": "League A",
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "Round": 3,
                    "Status": "Upcoming",
                },
                {
                    "League ID": "league-a",
                    "League Name": "League A",
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "Round": 4,
                    "Status": "Done",
                },
                {
                    "League ID": "another-league",
                    "League Name": "League A",
                    "Game": "F1 25",
                    "Season": "2026-T02",
                    "Round": 5,
                    "Status": "Upcoming",
                },
            ]
        )
        with (
            patch("league_config.load_config_tables", return_value=tables),
            patch("league_config.configured_league_keys", return_value=(key,)),
        ):
            rounds = ui._managed_roster_rounds(
                "unused.xlsx",
                self.standings(),
                calendar,
                ("F1 25", "2026-T02", "League A"),
            )
        self.assertEqual([3], rounds)

    def test_roster_sources_include_only_active_configured_leagues(self):
        active = league_config.LeagueKey(
            "active", "F1 25", "2026-T02", "League A"
        )
        completed = league_config.LeagueKey(
            "completed", "F1 24", "2025-T01", "League Old"
        )
        tables = SimpleNamespace(
            league_config=pd.DataFrame(
                [
                    {"League ID": "active", "Status": "Active"},
                    {"League ID": "completed", "Status": "Completed"},
                ]
            )
        )
        with (
            patch("league_config.load_config_tables", return_value=tables),
            patch(
                "league_config.configured_league_keys",
                return_value=(active, completed),
            ),
        ):
            options = ui._active_configured_championships("unused.xlsx")
        self.assertEqual([("F1 25", "2026-T02", "League A")], options)

    def test_calendar_clone_uses_full_source_identity(self):
        calendar = pd.DataFrame(
            [
                {
                    "League Name": "League A",
                    "Round": 1,
                    "Date": date(2026, 1, 1),
                    "GP Name": "Old GP",
                    "Circuit": "Old",
                    "Time (Lisbon)": time(20),
                    "Has Sprint": False,
                    "Game": "F1 24",
                    "Season": "2025-T01",
                },
                {
                    "League Name": "League A",
                    "Round": 1,
                    "Date": date(2027, 1, 1),
                    "GP Name": "New GP",
                    "Circuit": "New",
                    "Time (Lisbon)": time(20),
                    "Has Sprint": True,
                    "Game": "F1 25",
                    "Season": "2026-T02",
                },
            ]
        )
        seed = ui._calendar_seed(
            calendar,
            {"source": ["F1 25", "2026-T02", "League A"]},
        )
        self.assertEqual(["New GP"], seed["GP Name"].tolist())

    def test_reused_legacy_calendar_label_without_identity_is_not_cloned(self):
        calendar = pd.DataFrame(
            [
                {
                    "League Name": "Family League",
                    "Round": 1,
                    "Date": date(2027, 1, 1),
                    "GP Name": "Unknown season GP",
                    "Circuit": "Unknown",
                    "Time (Lisbon)": time(20),
                    "Has Sprint": False,
                    "Game": "",
                    "Season": "",
                    "League ID": "",
                }
            ]
        )
        identities = (
            ("F1 24", "2025-T01", "Family League"),
            ("F1 25", "2026-T01", "Family League"),
        )
        with self.assertRaisesRegex(ValueError, "without an exact"):
            ui._calendar_seed(
                calendar,
                {"source": ["F1 25", "2026-T01", "Family League"]},
                championship_identities=identities,
            )

    def test_active_league_with_unfinished_calendar_is_preview_blocker(self):
        calendar = pd.DataFrame(
            [
                {"League ID": "active-one", "Status": "Done", "Round": 1},
                {"League ID": "active-one", "Status": "Upcoming", "Round": 2},
            ]
        )
        with patch("pandas.read_excel", return_value=calendar):
            with self.assertRaisesRegex(ValueError, "unfinished Calendar rounds"):
                ui._require_completed_calendar("unused.xlsx", ["active-one"])

    def test_active_sprint_weekend_requires_both_complete_events(self):
        calendar = pd.DataFrame(
            [
                {
                    "League ID": "league-a",
                    "League Name": "League A",
                    "Round": 2,
                    "GP Name": "Australian GP",
                    "Status": "Done",
                    "Has Sprint": True,
                }
            ]
        )
        key = league_config.LeagueKey(
            "league-a", "F1 25", "2026-T02", "League A"
        )
        roster = tuple(
            league_config.RosterChange(
                "league-a", 1, driver, f"Team {position}"
            )
            for position, driver in enumerate(("Alice", "Bob", "Cara"), start=1)
        )
        with (
            patch("pandas.read_excel", return_value=calendar),
            patch("league_config.load_config_tables", return_value=Mock()),
            patch("league_config.configured_league_keys", return_value=(key,)),
            patch("league_config.resolve_roster_snapshot", return_value=roster),
        ):
            with self.assertRaisesRegex(ValueError, "R2 Sprint"):
                ui._require_completed_calendar(
                    "unused.xlsx",
                    ["league-a"],
                    standings=self.standings(),
                )

    def test_has_sprint_raw_false_string_does_not_become_true(self):
        self.assertFalse(ui._reviewed_bool("False", field_name="Has Sprint"))
        self.assertTrue(ui._reviewed_bool("yes", field_name="Has Sprint"))
        with self.assertRaisesRegex(ValueError, "explicit true/false"):
            ui._reviewed_bool("maybe", field_name="Has Sprint")


if __name__ == "__main__":
    unittest.main()
