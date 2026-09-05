import unittest
from unittest.mock import patch
import base64

import pandas as pd

import browser_download
import season_insights


class SeasonInsightsTests(unittest.TestCase):
    meta = {"Game": "F1 26", "SeasonLabel": "2026-T02", "League Name": "Example"}

    def row(self, **changes):
        return {**self.meta, "Driver": "Alice", "Round": 1, "Type": "R", "Points": 25,
                "GP Name": "British GP", "IsSeasonFinal": False, "Finish Pos": 1, **changes}

    def test_exact_season_race_sprint_totals_and_missing_event(self):
        rows = pd.DataFrame([
            self.row(), self.row(Type="SR", Points=6),
            self.row(Round=2, Points=18),
            self.row(Driver="Bob", Points=0, **{"Finish Pos": 15}),
            self.row(SeasonLabel="2025-T02", Points=100),
            self.row(Game="F1 25", Points=100),
            self.row(**{"League Name": "Other", "Points": 100}),
            self.row(IsSeasonFinal=True, Points=49),
        ])
        model = season_insights.season_points(rows, self.meta)
        self.assertEqual(model["rounds"], [1, 2])
        self.assertEqual(model["events"], {1: ["R", "SR"], 2: ["R"]})
        self.assertEqual(sum(v for (d, _, _), v in model["points"].items() if d == "Alice"), 49)
        self.assertEqual(model["points"][("Bob", 1, "R")], 0)
        self.assertNotIn(("Bob", 1, "SR"), model["points"])
        rendered = season_insights.render_season_insights(rows, self.meta)
        self.assertIn('>49</td>', rendered)
        self.assertIn('>—</td>', rendered)

    def test_duplicate_event_rows_are_not_silently_double_counted(self):
        with self.assertRaises(ValueError):
            season_insights.season_points(pd.DataFrame([self.row(), self.row()]), self.meta)

    def test_names_are_escaped_in_table_chart_and_search(self):
        rendered = season_insights.render_season_insights(
            pd.DataFrame([self.row(Driver='<img src=x onerror=alert(1)>')]), self.meta
        )
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img', rendered)

    def test_download_delivers_identical_bytes_without_media_endpoint(self):
        content = b'PK\x03\x04\x00\xff workbook fixture'
        with patch('admin_auth.is_current_admin', return_value=True), patch.object(
            browser_download.st.components.v2, 'component'
        ) as definition:
            browser_download.render_excel_download(content, 'F1_Standings.xlsx',
                label='Download', help_text='Latest Excel', error_text='Try again')
        data = definition.return_value.call_args.kwargs['data']
        self.assertEqual(base64.b64decode(data['content']), content)
        self.assertEqual(data['filename'], 'F1_Standings.xlsx')
        self.assertEqual(data['mime'], browser_download.XLSX_MIME)

    def test_download_never_sends_bytes_to_unauthorized_session(self):
        with patch('admin_auth.is_current_admin', return_value=False), patch.object(
            browser_download.st, 'stop', side_effect=RuntimeError('denied')
        ), patch.object(browser_download.st.components.v2, 'component') as definition:
            with self.assertRaises(RuntimeError):
                browser_download.render_excel_download(b'private', 'file.xlsx',
                    label='Download', help_text='', error_text='')
        definition.assert_not_called()
