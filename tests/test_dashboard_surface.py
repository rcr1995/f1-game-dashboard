from pathlib import Path
import unittest
import dashboard_surface as surface
import season_insights
import pandas as pd
import puskas_html


class DashboardSurfaceTests(unittest.TestCase):
    def test_teammates_rank_by_team_total_then_driver_score(self):
        rows = pd.DataFrame([
            {"Team": "Alpha", "Driver": "A", "Points": 40},
            {"Team": "Zulu", "Driver": "Z2", "Points": 30},
            {"Team": "Alpha", "Driver": "B", "Points": 10},
            {"Team": "Zulu", "Driver": "Z1", "Points": 35},
        ])
        self.assertEqual(puskas_html._rank_teammate_rows(rows).Driver.tolist(), ["Z1", "Z2", "A", "B"])
        # Actual constructor points override current-driver sums after transfers.
        constructors = pd.DataFrame([{"Team": "Alpha", "Points": 90}, {"Team": "Zulu", "Points": 20}])
        self.assertEqual(puskas_html._rank_teammate_rows(rows, constructors).Driver.tolist(), ["A", "B", "Z1", "Z2"])
        self.assertNotIn("_team_points", rows)

    def test_teammate_score_ties_are_stable_and_empty_is_safe(self):
        rows = pd.DataFrame([{"Team": t, "Driver": d, "Points": 2.5}
                             for t, d in [("Z", "C"), ("A", "B"), ("A", "A"), ("Z", "D")]])
        self.assertEqual(puskas_html._rank_teammate_rows(rows).Driver.tolist(), ["A", "B", "C", "D"])
        self.assertTrue(puskas_html._rank_teammate_rows(rows.iloc[:0]).empty)

    def test_content_height_without_embedded_page_or_generated_execution(self):
        source = Path('dashboard_surface.py').read_text(encoding='utf-8')
        self.assertIn("height='content'", source)
        self.assertNotIn('eval(', surface.JS)
        self.assertNotIn('new Function', surface.JS)
        self.assertIn("script,iframe,object,embed", surface.JS)
        self.assertNotIn('st.iframe', Path('dashboard_page.py').read_text(encoding='utf-8'))

    def test_popup_uses_top_layer_and_points_do_not_limit_height(self):
        self.assertIn('popup.showPopover()', surface.JS)
        self.assertIn("pointerenter", surface.JS)
        self.assertIn("else show(true)", surface.JS)
        self.assertIn("e.key==='Escape'", surface.JS)
        self.assertIn('max-height:none;overflow-x:auto', surface.CSS)
        self.assertNotIn('max-height:620px', season_insights.STYLE)

    def test_hero_routes_and_numbered_hall_of_fame(self):
        source = Path('puskas_html.py').read_text(encoding='utf-8')
        for route in ('race-centre','circuits','archive'):
            self.assertIn('/?view='+route, source)
        self.assertIn('<span>05</span>', source)

    def test_teammate_chart_is_script_free_and_lineup_uses_explicit_columns(self):
        source = Path('puskas_html.py').read_text(encoding='utf-8')
        self.assertIn('p-duel-track', source)
        self.assertNotIn('fig.to_html', source)
        self.assertIn('repeat(4,minmax(0,1fr))', surface.CSS)
        self.assertIn('repeat(2,minmax(0,1fr))', surface.CSS)
        self.assertIn("id==='drivers-extra'?'grid'", surface.JS)
