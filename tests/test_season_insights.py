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

    def test_constructor_points_follow_event_team_after_transfer(self):
        rows = pd.DataFrame([
            self.row(Team="Red"), self.row(Team="Red", Driver="Bob", Points=18),
            self.row(Team="Red", Type="SR", Points=6),
            self.row(Team="Blue", Round=2, Points=15),
            self.row(Team="Red", Round=2, Driver="Bob", Points=10),
        ])
        model = season_insights.season_points(rows, self.meta, "Constructors")
        self.assertEqual(model["drivers"], ["Red", "Blue"])
        self.assertEqual(model["points"][("Red", 1, "R")], 43)
        self.assertEqual(model["points"][("Red", 1, "SR")], 6)
        self.assertEqual(model["points"][("Blue", 2, "R")], 15)
        self.assertEqual(sum(model["points"].values()), rows.Points.sum())
        rendered = season_insights.render_season_insights(rows, self.meta, entity="Constructors")
        self.assertIn('Find constructor', rendered)
        self.assertIn('>59</td>', rendered)

    def test_collapsed_details_keep_identical_round_and_season_totals(self):
        rows = pd.DataFrame([self.row(), self.row(Type="SR", Points=6), self.row(Round=2, Points=18)])
        detailed = season_insights.render_season_insights(rows, self.meta)
        collapsed = season_insights.render_season_insights(rows, self.meta, show_details=False)
        for rendered in (detailed, collapsed):
            self.assertIn('class="si-weekend">31</td>', rendered)
            self.assertIn('class="si-total">49</td>', rendered)
            self.assertNotIn('<svg', rendered)
            self.assertNotIn('Championship progression', rendered)
        self.assertIn('scope="col">Sprint</th>', detailed)
        self.assertNotIn('scope="col">Sprint</th>', collapsed)
        self.assertNotIn('scope="col">Race</th>', collapsed)

    def test_missing_round_is_not_rendered_as_zero_when_collapsed(self):
        rows = pd.DataFrame([self.row(), self.row(Driver="Bob", Round=2, Points=0)])
        rendered = season_insights.render_season_insights(rows, self.meta, show_details=False)
        self.assertIn('class="si-weekend">—</td>', rendered)
        self.assertIn('class="si-weekend">0</td>', rendered)

    def test_names_are_escaped_in_table_chart_and_search(self):
        rendered = season_insights.render_season_insights(
            pd.DataFrame([self.row(Driver='<img src=x onerror=alert(1)>')]), self.meta
        )
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img', rendered)

    def test_positions_are_recorded_finishes_not_points_or_zero_for_missing(self):
        rows = pd.DataFrame([self.row(), self.row(Round=2, **{'Finish Pos':5}),
            self.row(Type='SR', **{'Finish Pos':9}),
            self.row(Driver='Bob', **{'Finish Pos':None}),
            self.row(Driver='Bob', Round=2, **{'Finish Pos':2}),
            self.row(Game='Old', **{'Finish Pos':20})])
        race = season_insights.season_positions(rows, self.meta)
        self.assertEqual(race['averages'], {'Alice':3, 'Bob':2})
        self.assertEqual(race['drivers'], ['Bob','Alice'])
        self.assertNotIn(('Bob',1,'R'), race['positions'])
        both = season_insights.season_positions(rows,self.meta,include_sprint=True)
        self.assertEqual(both['averages']['Alice'],5)
        rendered = season_insights.render_season_insights(rows,self.meta,metric='positions',show_details=False)
        self.assertIn('Average finish',rendered)
        self.assertIn('>3.00</td>',rendered)
        self.assertIn('>—</td>',rendered)
        self.assertNotIn('Grand total',rendered)
        self.assertNotIn('>Sprint</th>',rendered)

    def test_constructor_finish_averages_weight_individual_starts_and_follow_transfers(self):
        rows = pd.DataFrame([self.row(Team='Red'), self.row(Team='Red',Driver='Bob',**{'Finish Pos':5}),
            self.row(Team='Blue',Round=2,**{'Finish Pos':2}), self.row(Team='Red',Driver='Bob',Round=2,**{'Finish Pos':9})])
        model = season_insights.season_positions(rows,self.meta,'Constructors')
        self.assertEqual(model['positions'][('Red',1,'R')],3)
        self.assertEqual(model['averages']['Red'],5) # (1+5+9)/3, not (3+9)/2.
        self.assertEqual(model['averages']['Blue'],2)
        self.assertEqual(model['counts']['Red'],3)

    def test_positions_block_duplicates_and_handle_sprint_only_and_invalid_finish(self):
        with self.assertRaises(ValueError):
            season_insights.season_positions(pd.DataFrame([self.row(),self.row()]),self.meta)
        sprint = pd.DataFrame([self.row(Type='SR')])
        self.assertFalse(season_insights.season_positions(sprint,self.meta)['rounds'])
        self.assertEqual(season_insights.season_positions(sprint,self.meta,include_sprint=True)['averages']['Alice'],1)
        for position in ('DNF',None,0,-1,1.5,float('inf')):
            with self.subTest(position=position):
                model=season_insights.season_positions(pd.DataFrame([self.row(**{'Finish Pos':position})]),self.meta)
                self.assertFalse(model['averages'])

    def test_positions_escape_names_and_localize_labels(self):
        rendered=season_insights.render_season_insights(pd.DataFrame([self.row(Driver='<img src=x>')]),self.meta,'pt',metric='positions')
        self.assertIn('Posição média',rendered)
        self.assertIn('&lt;img',rendered)
        self.assertNotIn('<img src=x>',rendered)

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
