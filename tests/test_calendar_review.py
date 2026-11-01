from io import BytesIO
from types import SimpleNamespace
import base64
import unittest
from unittest.mock import patch

import openpyxl
from streamlit.testing.v1 import AppTest
import workbook_upload as upload


def file_bytes(results, schedule):
    book = openpyxl.Workbook()
    leagues = book.active
    leagues.title = 'Leagues'
    leagues.append(['Game', 'Season', 'League Name', 'Round', 'Type', 'GP Name', 'Driver', 'Team', 'Finish Pos', 'Points'])
    for season, rnd, kind, gp, name, position in results:
        leagues.append(['F1', season, 'League', rnd, kind, gp, name, 'Team', position, 8])
    calendar = book.create_sheet('Calendar')
    calendar.append(['League Name', 'Round', 'GP Name', 'Status', 'Game', 'Season', 'League ID'])
    for rnd, gp, status, *identity in schedule:
        calendar.append(['League', rnd, gp, status, *identity])
    buf = BytesIO()
    book.save(buf)
    book.close()
    return buf.getvalue()


TEXAS = ('T02', 9, 'R', 'United States GP', 'Tom', 1)
MEXICO = ('T02', 10, 'R', 'Mexico City GP', 'Pol', 1)
CAL = [(9, 'United States GP', 'Done'), (10, 'Mexico City GP', 'Done')]


class CalendarReviewTests(unittest.TestCase):
    def test_mixed_race_and_sprint_names_and_correct_excel_row_locations(self):
        before = file_bytes([TEXAS, MEXICO], CAL)
        after = file_bytes([TEXAS, ('T02',10,'R','United States GP','Pol',1),
                            ('T02',10,'R','  MEXICO CITY GP ','Tom',2),
                            ('T02',10,'R','United States GP','Fat',3),
                            ('T02',10,'SR','United States GP','Tom',1),
                            ('T02','All','R','Season Final','Tom',1)], CAL)
        review = upload.compare(before, after)['calendar']
        self.assertEqual([(i.problem, i.event, i.uploaded, i.expected, upload._row_ranges(i.rows)) for i in review['new']],
                         [('name','R','United States GP','Mexico City GP','3, 5'),
                          ('name','SR','United States GP','Mexico City GP','6')])
        self.assertEqual(upload.compare(after, before)['calendar']['new'], [])

    def test_legacy_issues_are_reported_without_requiring_new_approval(self):
        mismatched = ('T02',9,'R','Japanese GP','Tom',1)
        original = file_bytes([mismatched, MEXICO], CAL)
        reordered = file_bytes([MEXICO, mismatched], CAL)
        review = upload.compare(original, reordered)['calendar']
        self.assertFalse(review['new'])
        self.assertEqual([(i.uploaded,i.expected,i.rows) for i in review['existing']],
                         [('Japanese GP','United States GP',(3,))])

    def test_calendar_changes_and_winner_readiness(self):
        original = file_bytes([TEXAS, MEXICO], CAL)
        sprint = ('T02',10,'SR','Mexico City GP','Pol',1)
        for rows, calendar, issue in [
            ([TEXAS,MEXICO], [CAL[0],(10,'Canadian GP','Done')], 'name'),
            ([TEXAS,MEXICO], [CAL[0],(10,'Mexico City GP','Upcoming')], 'status'),
            ([TEXAS,sprint], CAL, 'missing_race'),
            ([TEXAS,sprint,(*MEXICO[:-1],2)], CAL, 'missing_winner'),
            ([TEXAS,MEXICO,(*MEXICO[:-2],'Tom',1)], CAL, 'multiple_winners'),
            ([TEXAS,MEXICO,(*MEXICO[:-1],2)], CAL, 'invalid_classification'),
            ([TEXAS,MEXICO], [CAL[0]], 'missing_round'),
        ]:
            with self.subTest(issue=issue):
                issues = upload.compare(original, file_bytes(rows,calendar))['calendar']['new']
                self.assertEqual([(i.round_number,i.problem) for i in issues], [(10,issue)])
        valid_sprint = file_bytes([TEXAS,sprint], [CAL[0],(10,'Mexico City GP','Upcoming')])
        self.assertFalse(upload.compare(original,valid_sprint)['calendar']['new'])

    def test_reused_leagues_need_a_unique_calendar(self):
        results = [('T01',9,'R','Japanese GP','Alice',1), TEXAS]
        unmanaged = file_bytes(results, [CAL[0]])
        review = upload.compare(unmanaged,unmanaged)['calendar']
        self.assertFalse(review['existing'])
        self.assertEqual(len(review['unchecked']), 2)
        managed = file_bytes(results, [(9,'Japanese GP','Done','F1','T01','one'),
                                      (9,'United States GP','Done','F1','T02','two')])
        review = upload.compare(unmanaged,managed)['calendar']
        self.assertEqual(review, {'new':[], 'existing':[], 'unchecked':[], 'new_unchecked':[]})
        self.assertTrue(upload.calendar_review.needs_acknowledgement(upload.compare(managed,unmanaged)['calendar']))

    def test_done_round_is_checked_even_after_all_its_league_results_are_removed(self):
        two_seasons = [(9,'Japanese GP','Done','F1','T01','one'),
                       (9,'United States GP','Done','F1','T02','two')]
        archived = ('T01',9,'R','Japanese GP','Alice',1)
        original = file_bytes([archived,TEXAS],two_seasons)
        review = upload.compare(original,file_bytes([archived],two_seasons))['calendar']
        self.assertEqual([(i.season,i.problem) for i in review['new']], [('T02','missing_race')])

    def test_wrong_gp_requires_separate_acknowledgement_at_publish_time(self):
        original = file_bytes([TEXAS,MEXICO],CAL)
        candidate = file_bytes([TEXAS,('T02',10,'R','United States GP','Pol',1)],CAL)
        preview = upload.compare(original,candidate)
        with patch('admin_auth.is_current_admin',return_value=True), patch('race_github.GitHubAppClient') as factory:
            client = factory.return_value
            client._fetch_with_token.return_value = SimpleNamespace(content=original,blob_sha='base')
            args=dict(expected_sha='base',approved_digest=preview['digest'],approved=True)
            with self.assertRaisesRegex(ValueError,'calendar warnings'):
                upload.publish(None,candidate,**args)
            client._publish_updated_workbook.assert_not_called()
            upload.publish(None,candidate,calendar_acknowledged=True,**args)
            self.assertEqual(client._publish_updated_workbook.call_args.kwargs['updated_bytes'],candidate)

    def test_upload_automatically_displays_warning_and_resets_acknowledgement_for_new_bytes(self):
        original = file_bytes([TEXAS,MEXICO],CAL)
        candidate = file_bytes([TEXAS,('T02',10,'R','United States GP','Pol',1)],CAL)
        payload = {'name':'test.xlsx','content':base64.b64encode(candidate).decode()}
        with (patch('admin_auth.is_current_admin',return_value=True),
              patch('race_github.fetch_remote_workbook',return_value=SimpleNamespace(content=original,blob_sha='base')) as fetch,
              patch('streamlit.components.v2.component',return_value=lambda **kwargs:{'file':payload})):
            app = AppTest.from_string("import workbook_upload; workbook_upload.render(None,lang='en')").run()
            self.assertFalse(app.exception)
            self.assertIn('New or changed calendar warnings',app.warning[0].value)
            self.assertIn('Mexico City GP',app.dataframe[0].value['GP in Calendar'].tolist())
            app.checkbox[1].check().run()
            self.assertTrue(app.button[-1].disabled)
            app.checkbox[0].check().run()
            self.assertFalse(app.button[-1].disabled)
            fetch.assert_called_once()
            payload['content']=base64.b64encode(file_bytes([TEXAS,('T02',10,'R','Japanese GP','Pol',1)],CAL)).decode()
            app.run()
            self.assertFalse(app.checkbox[0].value)
            self.assertTrue(app.button[-1].disabled)
            self.assertFalse(app.exception)

