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

    def test_router_renders_without_language_component_response_and_on_rerun(self):
        # Reproduce a lost browser handshake/new server session. Previously this
        # stopped on the bilingual loading caption forever, before routing.
        with patch("ui_preferences.mount_browser_language"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assert_rendered(app)
            self.assertFalse(any("Loading /" in element.value for element in app.caption))
            app.run()
            self.assert_rendered(app)


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

    def test_championship_selector_changes_only_playback_and_rejects_unknown_keys(self):
        import championship_circuit
        import championship_circuit_ui
        import dashboard_surface
        import puskas_html

        with (
            patch.object(championship_circuit, 'build_model', wraps=championship_circuit.build_model) as build,
            patch.object(championship_circuit_ui, 'render', wraps=championship_circuit_ui.render) as chart,
            patch.object(puskas_html, 'render_puskas_dashboard', wraps=puskas_html.render_puskas_dashboard) as dashboard,
            patch.object(dashboard_surface, 'render', wraps=dashboard_surface.render) as surface,
        ):
            app = self.app()
            self.assert_rendered(app)
            current = dashboard.call_args.kwargs['circuit_model']
            offered = surface.call_args.kwargs['circuit']
            self.assertEqual(offered['meta'], current['meta'])
            self.assertNotIn('catalog', current)
            self.assertNotIn('selectedKey', current)
            self.assertEqual(build.call_count, 1)
            selected = next(item for item in offered['catalog'] if item['meta'] != current['meta'])

            app.query_params['championship'] = selected['key']
            app.run()
            self.assert_rendered(app)
            displayed = surface.call_args.kwargs['circuit']
            self.assertEqual(displayed['selectedKey'], selected['key'])
            self.assertEqual(displayed['meta'], selected['meta'])
            self.assertEqual(dashboard.call_args.args[3], current['meta'])
            self.assertEqual(dashboard.call_args.kwargs['circuit_model'], current)
            self.assertIs(dashboard.call_args.kwargs['championship_model'], displayed)
            chart.assert_called_with(displayed, 'en')
            self.assertEqual(build.call_count, 2)

            # A URL can request a known key, never inject workbook metadata.
            app.query_params['championship'] = '../../unknown-league'
            app.run()
            self.assert_rendered(app)
            fallback = surface.call_args.kwargs['circuit']
            self.assertEqual(fallback['selectedKey'], offered['selectedKey'])
            self.assertEqual(fallback['meta'], current['meta'])
            self.assertEqual(dashboard.call_args.kwargs['circuit_model'], current)
            self.assertEqual(build.call_count, 2)

    def test_circuit_cards_and_history_use_the_full_published_source_in_both_languages(self):
        import circuit_history
        import circuit_history_ui
        import dashboard_core as core
        import dashboard_surface

        expected = core.load_standings_data(WORKBOOK)
        for language, lang, heading in (
            ('English', 'en', 'Circuit Layouts'),
            ('Português (Portugal)', 'pt', 'Layouts dos Circuitos'),
        ):
            with (
                self.subTest(lang=lang),
                patch.object(circuit_history, 'circuit_history', wraps=circuit_history.circuit_history) as history,
                patch.object(circuit_history_ui, 'render', wraps=circuit_history_ui.render) as gallery,
                patch.object(dashboard_surface, 'render', wraps=dashboard_surface.render) as surface,
            ):
                app = self.app(language, view='circuits')
                self.assert_rendered(app)
                self.assertTrue(any(heading in item.value for item in app.markdown))
                history.assert_called_once()
                pd.testing.assert_frame_equal(history.call_args.args[0], expected)
                self.assertFalse(history.call_args.args[1].empty)
                cards = gallery.call_args.args[0]
                self.assertGreater(len(cards), 0)
                self.assertEqual(len(cards), len({card['key'] for card in cards}))
                pd.testing.assert_frame_equal(gallery.call_args.args[1], expected)
                self.assertEqual(gallery.call_args.kwargs, {'lang': lang, 'scope_label': None})
                self.assertEqual(surface.call_args.kwargs, {'lang': lang, 'key': 'circuits_surface'})
                self.assertIn('p-track-card', surface.call_args.args[0])
                self.assertIn('<dialog', surface.call_args.args[0])

    def test_circuit_filter_scopes_cards_history_and_lap_records_without_changing_source(self):
        import championship_circuit
        import circuit_history_ui
        import dashboard_core as core
        results = core.load_standings_data(WORKBOOK)
        catalog = championship_circuit.championship_catalog(results)
        with patch.object(circuit_history_ui, 'render', wraps=circuit_history_ui.render) as gallery:
            app = self.app(view='circuits')
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_league').value, 'all')
            for season, winner in [('2026-T02', 'TomasRodri21'), ('2026-T01', 'Polingua')]:
                selected = next(entry for entry in catalog if entry['meta']['SeasonLabel'] == season)
                app.selectbox(key='circuits_league').set_value(selected['key']).run()
                self.assert_rendered(app)
                displayed = gallery.call_args.args[1]
                for column, value in selected['meta'].items():
                    self.assertEqual(set(displayed[column]), {value})
                australia = next(card for card in gallery.call_args.args[0] if card['gp_name'] == 'Australian GP')
                self.assertEqual(australia['race_count'], 1)
                self.assertEqual(australia['leaders'], [{'driver': winner, 'wins': 1}])
                self.assertEqual(gallery.call_args.kwargs['scope_label'], selected['label'])
            app.session_state['app_lang'] = 'Português (Portugal)'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_league').value, selected['key'])
            self.assertEqual(app.selectbox(key='circuits_league').label, 'Liga / época')
            app.selectbox(key='circuits_league').set_value('all').run()
            self.assert_rendered(app)
            pd.testing.assert_frame_equal(gallery.call_args.args[1], results)
            australia = next(card for card in gallery.call_args.args[0] if card['gp_name'] == 'Australian GP')
            self.assertGreater(australia['race_count'], 1)

    def test_circuit_filter_handles_summary_only_seasons_and_stale_selection(self):
        import championship_circuit
        import dashboard_core as core
        results = core.load_standings_data(WORKBOOK)
        catalog = championship_circuit.championship_catalog(results)
        summary = next(entry for entry in catalog if results[
            (results['Game'] == entry['meta']['Game']) &
            (results['SeasonLabel'] == entry['meta']['SeasonLabel']) &
            (results['League Name'] == entry['meta']['League Name'])]['IsSeasonFinal'].all())
        app = self.app(view='circuits')
        app.selectbox(key='circuits_league').set_value(summary['key']).run()
        self.assert_rendered(app)
        self.assertIn('No race-by-race circuit history is available for this league/season.',
                      self.messages(app.main, 'info'))
        with patch.object(championship_circuit, 'championship_catalog',
                          return_value=[entry for entry in catalog if entry['key'] != summary['key']]):
            app.run()
        self.assert_rendered(app)
        self.assertEqual(app.selectbox(key='circuits_league').value, 'all')

    def test_circuit_search_and_sort_combine_with_league_scope_and_head_to_head(self):
        import championship_circuit
        import circuit_history_ui
        import dashboard_core as core
        catalog = championship_circuit.championship_catalog(core.load_standings_data(WORKBOOK))
        selected = next(entry for entry in catalog if entry['meta']['SeasonLabel'] == '2026-T01')
        with patch.object(circuit_history_ui, 'render', wraps=circuit_history_ui.render) as gallery:
            app = self.app(view='circuits')
            self.assert_rendered(app)
            app.text_input(key='circuits_search').set_value('Brasil').run()
            self.assert_rendered(app)
            self.assertEqual([card['gp_name'] for card in gallery.call_args.args[0]], ['São Paulo GP'])
            app.selectbox(key='circuits_league').set_value(selected['key']).run()
            self.assert_rendered(app)
            brazil = gallery.call_args.args[0][0]
            self.assertEqual(brazil['race_count'], 1)
            polingua = next(row for row in brazil['head_to_head'] if row['driver'] == 'Polingua')
            self.assertEqual(polingua['wins'], 1)
            self.assertEqual(polingua['podiums'], 1)
            self.assertEqual(gallery.call_args.kwargs['scope_label'], selected['label'])
            app.selectbox(key='circuits_league').set_value('all').run()
            app.text_input(key='circuits_search').set_value('United States').run()
            app.selectbox(key='circuits_sort').set_value('races').run()
            self.assert_rendered(app)
            cards = gallery.call_args.args[0]
            self.assertEqual([card['gp_name'] for card in cards],
                             ['Miami GP', 'United States GP', 'Las Vegas GP'])
            app.selectbox(key='circuits_sort').set_value('country').run()
            self.assert_rendered(app)
            self.assertEqual([card['gp_name'] for card in gallery.call_args.args[0]],
                             ['Las Vegas GP', 'Miami GP', 'United States GP'])
            app.text_input(key='circuits_search').set_value('no such circuit').run()
            self.assert_rendered(app)
            self.assertIn('No circuits match your search. Try another name or country.',
                          self.messages(app.main, 'info'))
            app.text_input(key='circuits_search').set_value('').run()
            self.assert_rendered(app)
            self.assertEqual(len(gallery.call_args.args[0]), 26)

    def test_circuit_preference_restores_fresh_visits_and_survives_page_navigation(self):
        import championship_circuit
        import circuit_history_ui
        import dashboard_core as core
        import ui_preferences
        catalog = championship_circuit.championship_catalog(core.load_standings_data(WORKBOOK))
        saved = next(entry for entry in catalog if entry['meta']['SeasonLabel'] == '2026-T01')
        factory = st.components.v2.component

        def browser_response(name, *args, **kwargs):
            if name == 'f1_circuits_preference':
                return lambda **mounted: {'preference': saved['key']}
            if name == 'f1_circuits_sort_preference':
                return lambda **mounted: {'preference': 'races'}
            return factory(name, *args, **kwargs)

        with (patch('streamlit.components.v2.component', side_effect=browser_response),
              patch.object(circuit_history_ui, 'render', wraps=circuit_history_ui.render) as gallery):
            app = self.app(view='circuits')
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_league').value, saved['key'])
            self.assertEqual(app.selectbox(key='circuits_sort').value, 'races')
            australia = next(card for card in gallery.call_args.args[0] if card['gp_name'] == 'Australian GP')
            self.assertEqual(australia['leaders'], [{'driver': 'Polingua', 'wins': 1}])
            app.query_params['view'] = 'overview'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.session_state[ui_preferences.CIRCUITS_VALUE_KEY], saved['key'])
            self.assertEqual(app.session_state[ui_preferences.SORT_VALUE_KEY], 'races')
            app.query_params['view'] = 'circuits'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_league').value, saved['key'])
            self.assertEqual(app.selectbox(key='circuits_sort').value, 'races')
            app.selectbox(key='circuits_sort').set_value('country').run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_sort').value, 'country')
            self.assertEqual(app.selectbox(key='circuits_league').value, saved['key'])
            app.session_state['app_lang'] = 'Português (Portugal)'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_sort').label, 'Ordenar por')
            self.assertEqual(app.selectbox(key='circuits_sort').value, 'country')
            # Explicit All beats a replay of the old browser response.
            app.selectbox(key='circuits_league').set_value('all').run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='circuits_league').value, 'all')
            fresh = self.app(view='circuits')
            self.assert_rendered(fresh)
            self.assertEqual(fresh.selectbox(key='circuits_league').value, saved['key'])
            self.assertEqual(fresh.selectbox(key='circuits_sort').value, 'races')

    def test_empty_circuit_catalog_explains_why_no_cards_are_shown(self):
        import circuit_history
        import circuit_history_ui
        with (patch.object(circuit_history, 'circuit_history', return_value=[]),
              patch.object(circuit_history_ui, 'render') as gallery):
            app = self.app(view='circuits')
            self.assert_rendered(app)
            self.assertIn('No GP winner data available.', self.messages(app.main, 'info'))
            gallery.assert_not_called()

    def test_race_centre_points_follow_league_entity_and_detail_filters(self):
        with patch.object(season_insights, "render_season_insights", wraps=season_insights.render_season_insights) as render:
            app = self.app(view="race-centre")
            self.assert_rendered(app)
            self.assertFalse(app.sidebar.selectbox)
            self.assertFalse(app.sidebar.radio)
            self.assertEqual(render.call_args.kwargs, {"entity": "Drivers", "show_details": False, "metric": "points", "event_scope": "all"})
            app.radio(key="dash_view").set_value("Constructors").run()
            self.assert_rendered(app)
            self.assertEqual(render.call_args.kwargs["entity"], "Constructors")
            app.toggle(key="round_points_details").set_value(True).run()
            self.assertTrue(render.call_args.kwargs["show_details"])
            app.selectbox(key="round_metric").set_value("Finishing positions").run()
            self.assert_rendered(app)
            self.assertEqual(render.call_args.kwargs["metric"], "positions")
            selector = app.selectbox(key="gp_pair")
            different = next(value for value in selector.options[1:] if value != selector.value)
            selector.set_value(different).run()
            self.assert_rendered(app)
            selected_meta = render.call_args.args[1]
            self.assertEqual(f'{selected_meta["SeasonLabel"]} ||| {selected_meta["League Name"]}', different)
            app.session_state['app_lang'] = 'Português (Portugal)'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='round_metric').value, 'Posições finais')
            self.assertEqual(render.call_args.kwargs['metric'], 'positions')

    def test_sprint_filter_controls_tables_charts_and_survives_language_change(self):
        import dashboard_core as core
        with (
            patch('importlib.reload', side_effect=lambda module: module),
            patch.object(season_insights, 'render_season_insights', wraps=season_insights.render_season_insights) as render,
            patch.object(core, 'cumulative_points_wide', wraps=core.cumulative_points_wide) as progression,
            patch.object(core, 'championship_tension', wraps=core.championship_tension) as tension,
            patch.object(core, 'position_delta_table', wraps=core.position_delta_table) as delta,
        ):
            app = self.app(view='race-centre')
            app.selectbox(key='race_event_scope').set_value('sprint').run()
            self.assert_rendered(app)
            self.assertEqual(render.call_args.kwargs['event_scope'],'sprint')
            for calculation in (render,progression,tension,delta):
                self.assertEqual(set(calculation.call_args.args[0]['Type']),{'SR'})
            self.assertFalse(app.toggle)
            app.selectbox(key='round_metric').set_value('Finishing positions').run()
            self.assertEqual(render.call_args.kwargs['metric'],'positions')
            app.radio(key='dash_view').set_value('Constructors').run()
            self.assertEqual(render.call_args.kwargs['entity'],'Constructors')
            app.session_state['app_lang'] = 'Português (Portugal)'
            app.run()
            self.assert_rendered(app)
            self.assertEqual(app.selectbox(key='race_event_scope').value,'sprint')
            self.assertIn('Só Sprints',app.selectbox(key='race_event_scope').options)
            app.selectbox(key='race_event_scope').set_value('race').run()
            self.assert_rendered(app)
            for calculation in (render,progression,tension,delta):
                self.assertEqual(set(calculation.call_args.args[0]['Type']),{'R'})

    def test_sprint_empty_selection_is_explained_and_filter_can_be_changed(self):
        import dashboard_core as core
        filter_events = core.filter_event_results
        def without_sprints(rows, scope='all'):
            return filter_events(rows[rows['Type']=='R'],scope)
        with (patch('importlib.reload', side_effect=lambda module: module),
              patch.object(core,'filter_event_results',side_effect=without_sprints)):
            app = self.app(view='race-centre')
            app.selectbox(key='race_event_scope').set_value('sprint').run()
            self.assert_rendered(app)
            self.assertIn('No Sprint results have been published for this selection.', self.messages(app.main,'info'))
            self.assertFalse(app.get('plotly_chart'))
            app.selectbox(key='race_event_scope').set_value('all').run()
            self.assert_rendered(app)
            self.assertTrue(app.get('plotly_chart'))

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
