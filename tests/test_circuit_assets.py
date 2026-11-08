"""Circuit cards render packaged outlines without relying on external hosts."""
import base64
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

import pandas as pd

from circuit_history import circuit_history
from circuit_history_ui import render
from dashboard_core import load_standings_data
from puskas_html import CIRCUIT_SVG_MAP, circuit_lap_records_html


ROOT = Path(__file__).resolve().parents[1]


class CircuitAssetTests(unittest.TestCase):
    def test_all_mapped_layouts_are_embedded_valid_svg_without_remote_dependencies(self):
        layouts = set(CIRCUIT_SVG_MAP.values())
        self.assertEqual(len(layouts), 26)
        for gp, source in CIRCUIT_SVG_MAP.items():
            with self.subTest(gp=gp):
                self.assertTrue(source.startswith("data:image/svg+xml;base64,"))
                content = base64.b64decode(source.split(",", 1)[1], validate=True)
                svg = ET.fromstring(content)
                self.assertEqual(svg.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertEqual(svg.get("viewBox"), "0 0 500 500")
                self.assertGreater(len(svg.findall("{http://www.w3.org/2000/svg}path")), 0)
                for element in svg.iter():
                    self.assertIn(element.tag.rsplit("}", 1)[-1], {"svg", "path"})
                    self.assertFalse(any(k.lower().startswith("on") or
                                         "href" in k.lower() for k in element.attrib))
                self.assertNotIn(b"url(", content)

    def test_gallery_embeds_all_known_circuit_images_and_preserves_aliases(self):
        results = load_standings_data(ROOT / "F1_Standings.xlsx")
        cards = circuit_history(results)
        output = render(cards, results)
        for card in cards:
            if card["venue_recorded"]:
                self.assertIn('src="' + CIRCUIT_SVG_MAP[card["gp_name"]] + '"', output)
        self.assertNotIn("raw.githubusercontent.com", output)
        self.assertEqual(CIRCUIT_SVG_MAP["Brazilian GP"], CIRCUIT_SVG_MAP["São Paulo GP"])
        self.assertEqual(CIRCUIT_SVG_MAP["Mexican GP"], CIRCUIT_SVG_MAP["Mexico City GP"])

    def test_source_license_is_bundled_with_exactly_the_referenced_assets(self):
        directory = ROOT / "assets/circuit-layouts"
        self.assertIn("MIT License", (directory / "LICENSE.txt").read_text())
        self.assertIn("ROY Jules", (directory / "LICENSE.txt").read_text())
        files = list(directory.glob("*.svg"))
        self.assertEqual(len(files), 26)
        embedded = {base64.b64decode(source.split(",", 1)[1]) for source in CIRCUIT_SVG_MAP.values()}
        self.assertEqual({asset.read_bytes() for asset in files}, embedded)

    def test_filtered_lap_record_title_describes_selected_scope_in_both_languages(self):
        for lang in ("en", "pt"):
            output = circuit_lap_records_html("São Paulo GP", lang=lang,
                                             scope_label="2026-T02 · <Teikirise>")
            self.assertIn("2026-T02 · &lt;Teikirise&gt;", output)
            self.assertNotIn("all seasons", output)
            self.assertNotIn("todas as temporadas", output)


if __name__ == "__main__":
    unittest.main()
