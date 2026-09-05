from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
import hashlib
import unittest
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl
import workbook_upload as upload
import race_github


class WorkbookUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=Path('F1_Standings.xlsx').read_bytes()

    def modified(self, delete_sheet=False):
        if not delete_sheet:
            out=BytesIO()
            with ZipFile(BytesIO(self.original)) as source,ZipFile(out,'w') as target:
                for item in source.infolist():
                    data=source.read(item.filename)
                    if item.filename=='xl/worksheets/sheet1.xml':
                        ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                        root=ET.fromstring(data)
                        row=root.find(f'{ns}sheetData/{ns}row')
                        root.find(ns+'dimension').set('ref','A1:Q4772')
                        cell=ET.SubElement(row,ns+'c',{'r':'Q1','t':'inlineStr'})
                        ET.SubElement(ET.SubElement(cell,ns+'is'),ns+'t').text='Admin test note'
                        data=ET.tostring(root)
                    target.writestr(item,data)
            return out.getvalue()
        book=openpyxl.load_workbook(BytesIO(self.original))
        if delete_sheet:
            book.remove(book['Calendar'])
        else:
            book['Calendar']['Z1']='Admin test note'
        out=BytesIO();book.save(out);book.close();return out.getvalue()

    def test_valid_preview_reports_changed_cells_without_changing_source(self):
        candidate=self.modified();preview=upload.compare(self.original,candidate)
        self.assertTrue(any(row['Changed cells'] for row in preview['summary']))
        self.assertEqual(preview['digest'],hashlib.sha256(candidate).hexdigest())
        self.assertEqual(self.original,Path('F1_Standings.xlsx').read_bytes())

    def test_invalid_or_missing_sheet_file_is_blocked(self):
        for data in (b'invalid',self.modified(delete_sheet=True)):
            with self.subTest(),self.assertRaises(ValueError):upload.compare(self.original,data)

    def test_no_auth_or_approval_cannot_contact_github(self):
        for auth,approved in ((False,True),(True,False)):
            with patch('admin_auth.is_current_admin',return_value=auth),patch.object(race_github,'GitHubAppClient') as client:
                with self.assertRaises(PermissionError):upload.publish(None,b'test',expected_sha='a'*40,approved_digest='',approved=approved)
                client.assert_not_called()

    def test_changed_candidate_and_stale_github_never_write(self):
        candidate=self.modified()
        with patch('admin_auth.is_current_admin',return_value=True),patch.object(race_github,'GitHubAppClient') as client:
            with self.assertRaises(ValueError):upload.publish(None,candidate,expected_sha='a'*40,approved_digest='wrong',approved=True)
            client.assert_not_called()
            client.return_value._fetch_with_token.return_value=SimpleNamespace(content=self.original,blob_sha='b'*40)
            with self.assertRaises(race_github.GitHubConflictError):upload.publish(None,candidate,expected_sha='a'*40,approved_digest=hashlib.sha256(candidate).hexdigest(),approved=True)
            client.return_value._publish_updated_workbook.assert_not_called()

    def test_approved_upload_publishes_exact_bytes_with_reviewed_sha(self):
        candidate=self.modified()
        with patch('admin_auth.is_current_admin',return_value=True),patch.object(race_github,'GitHubAppClient') as definition:
            client=definition.return_value
            remote=SimpleNamespace(content=self.original,blob_sha='a'*40)
            client._fetch_with_token.return_value=remote
            client._publish_updated_workbook.return_value=('commit','url','blob')
            upload.publish(None,candidate,expected_sha='a'*40,approved_digest=hashlib.sha256(candidate).hexdigest(),approved=True)
            self.assertEqual(client._publish_updated_workbook.call_args.kwargs['updated_bytes'],candidate)
            self.assertIs(client._publish_updated_workbook.call_args.kwargs['remote'],remote)
