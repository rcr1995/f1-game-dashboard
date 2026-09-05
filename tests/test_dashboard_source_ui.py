"""Rendered integration for read-only hosted workbook selection.

The actual checked-in workbook is read, never copied or edited. Resolver and
transport mocks keep these tests offline and independent of live GitHub data.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import public_workbook
import season_insights


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "F1_Standings.xlsx"
PAGE = ROOT / "dashboard_page.py"


class DashboardWorkbookSourceTests(unittest.TestCase):
    def setUp(self):
        self.before = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
        self.before_modified = WORKBOOK.stat().st_mtime_ns
        self.source = public_workbook.WorkbookSource(
            path=WORKBOOK,
            fingerprint=self.before,
            mode="github",
            status="current",
            source_url=public_workbook.GitHubWorkbookConfig().source_url,
        )
        st.cache_data.clear()
        self.resolver_patch = patch.object(public_workbook, "resolve_workbook", return_value=self.source)
        self.resolver = self.resolver_patch.start()
        self.addCleanup(self.resolver_patch.stop)
        self.download_patch = patch.object(public_workbook, "_download", side_effect=AssertionError("UI test attempted network access"))
        self.download = self.download_patch.start()
        self.addCleanup(self.download_patch.stop)
        self.write_patch = patch.object(public_workbook, "_atomic_write", side_effect=AssertionError("UI test attempted a snapshot write"))
        self.write = self.write_patch.start()
        self.addCleanup(self.write_patch.stop)

    def tearDown(self):
        self.download.assert_not_called()
        self.write.assert_not_called()
        self.assertEqual(hashlib.sha256(WORKBOOK.read_bytes()).hexdigest(), self.before)
        self.assertEqual(WORKBOOK.stat().st_mtime_ns, self.before_modified)
        st.cache_data.clear()

    def app(self, language="English", view="overview"):
        app = AppTest.from_file(str(PAGE), default_timeout=30)
        app.session_state["app_lang"] = language
        app.query_params['view'] = view
        return app.run()

    def assert_rendered(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])
        self.assertEqual(len(app.tabs), 0)
        self.assertGreater(len(app.get("html")), 0)

    @staticmethod
    def messages(container, kind):
        return [element.value for element in getattr(container, kind)]

    def test_live_source_status_is_visible_in_main_not_collapsed_sidebar(self):
        app = self.app()
        self.assert_rendered(app)
        expected = "Excel: GitHub · updates checked every minute"
        self.assertIn(expected, self.messages(app.main, "caption"))
        self.assertNotIn(expected, self.messages(app.sidebar, "caption"))
        self.assertFalse(any("GitHub update unavailable" in value for value in self.messages(app.main, "warning")))
        self.assertGreaterEqual(self.resolver.call_count, 2)

    def test_race_centre_points_follow_league_entity_and_detail_filters(self):
        with patch.object(season_insights, "render_season_insights", wraps=season_insights.render_season_insights) as render:
            app = self.app(view="race-centre")
            self.assert_rendered(app)
            self.assertFalse(app.sidebar.selectbox)
            self.assertFalse(app.sidebar.radio)
            self.assertEqual(render.call_args.kwargs, {"entity": "Drivers", "show_details": False, "metric": "points"})
            app.radio(key="dash_view").set_value("Constructors").run()
            self.assert_rendered(app)
            self.assertEqual(render.call_args.kwargs["entity"], "Constructors")
            app.toggle(key="round_points_details").set_value(True).run()
            self.assertTrue(render.call_args.kwargs["show_details"])
            app.selectbox(key="round_metric").set_value("positions").run()
            self.assert_rendered(app)
            self.assertEqual(render.call_args.kwargs["metric"], "positions")
            selector = app.selectbox(key="gp_pair")
            different = next(value for value in selector.options[1:] if value != selector.value)
            selector.set_value(different).run()
            self.assert_rendered(app)
            selected_meta = render.call_args.args[1]
            self.assertEqual(f'{selected_meta["SeasonLabel"]} ||| {selected_meta["League Name"]}', different)

    def test_stale_warning_is_visible_and_localized_without_exposing_raw_error(self):
        self.resolver.return_value = replace(
            self.source, status="stale", warning="private diagnostic: never display this detail",
        )
        for language, prefix in (
            ("English", "GitHub update unavailable."),
            ("Português (Portugal)", "Atualização do GitHub indisponível."),
        ):
            with self.subTest(language=language):
                app = self.app(language)
                self.assert_rendered(app)
                warnings = self.messages(app.main, "warning")
                self.assertTrue(any(value.startswith(prefix) for value in warnings))
                self.assertFalse(any(value.startswith(prefix) for value in self.messages(app.sidebar, "warning")))
                self.assertNotIn("private diagnostic", " ".join(warnings))
                self.assertFalse(any(value.startswith("Excel: GitHub") for value in self.messages(app.main, "caption")))

    def test_first_fetch_bundled_fallback_is_not_presented_as_current_github_data(self):
        self.resolver.return_value = replace(
            self.source, mode="bundled", status="bundled_fallback", warning="Offline",
        )
        app = self.app()
        self.assert_rendered(app)
        self.assertTrue(any("GitHub update unavailable" in value for value in self.messages(app.main, "warning")))
        self.assertFalse(any(value.startswith("Excel: GitHub") for value in self.messages(app.main, "caption")))

    def test_local_manual_mode_has_no_hosted_status_or_periodic_source_check(self):
        self.resolver.return_value = replace(self.source, mode="local", status="local", source_url=None)
        app = self.app()
        self.assert_rendered(app)
        self.assertFalse(any("GitHub" in value for value in self.messages(app.main, "caption")))
        self.assertFalse(any("GitHub" in value for value in self.messages(app.main, "warning")))
        self.resolver.assert_called_once()

    def test_same_revision_reuses_data_cache_but_new_revision_reloads_same_path(self):
        # A revision change must invalidate data even if a path and mtime stay
        # unchanged. Instrument pandas reads while returning genuine data.
        with patch.object(pd, "read_excel", wraps=pd.read_excel) as reads:
            app = self.app()
            self.assert_rendered(app)
            initial_reads = reads.call_count
            self.assertGreater(initial_reads, 0)
            app.run()
            self.assert_rendered(app)
            self.assertEqual(reads.call_count, initial_reads)

            self.resolver.return_value = replace(self.source, fingerprint="b" * 64)
            app.run()
            self.assert_rendered(app)
            self.assertGreater(reads.call_count, initial_reads)
        self.assertEqual(WORKBOOK.stat().st_mtime_ns, self.before_modified)

    def test_revision_changed_during_fragment_check_reruns_app_to_new_source(self):
        updated = replace(self.source, fingerprint="c" * 64)
        calls = 0

        def resolve(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 6:
                raise AssertionError("Unbounded rerun loop after source revision changed")
            return self.source if calls == 1 else updated

        self.resolver.side_effect = resolve
        app = self.app()
        self.assert_rendered(app)
        # First load/check differs, then the full app load/check both agree.
        self.assertEqual(calls, 4)
        self.assertIn("Excel: GitHub · updates checked every minute", self.messages(app.main, "caption"))


if __name__ == "__main__":
    unittest.main()
