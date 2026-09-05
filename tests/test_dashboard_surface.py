from pathlib import Path
import unittest
import dashboard_surface as surface
import season_insights


class DashboardSurfaceTests(unittest.TestCase):
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
