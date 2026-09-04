from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import hashlib
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
from zipfile import ZIP_DEFLATED, ZipFile

import public_workbook as public


ROOT = Path(__file__).resolve().parents[1]
ENABLED = {"F1_PUBLIC_GITHUB_SYNC": "1"}


def _hold_process_lock(directory, acquired, release):
    with public._cache_lock(Path(directory)):
        acquired.set()
        release.wait(timeout=10)


def _replace_part(content: bytes, name: str, value: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(content)) as original, ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
        for entry in original.infolist():
            target.writestr(entry, value if entry.filename == name else original.read(entry.filename))
    return output.getvalue()


class PublicWorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (ROOT / "F1_Standings.xlsx").read_bytes()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="public-workbook-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.local = self.directory / "manual.xlsx"
        self.local.write_bytes(self.content)
        self.cache = self.directory / "cache"
        self.download = mock.patch.object(public, "_download", return_value=(self.content, '"version1"')).start()
        self.addCleanup(mock.patch.stopall)

    def resolve(self, **kwargs):
        return public.resolve_workbook(self.local, environ=ENABLED, cache_dir=self.cache, **kwargs)

    def test_local_manual_workflow_does_not_request_or_create_cache(self):
        source = public.resolve_workbook(self.local, environ={}, cache_dir=self.cache)
        self.assertEqual(source.path, self.local)
        self.assertEqual(source.status, "local")
        self.assertIsNone(source.warning)
        self.download.assert_not_called()
        self.assertFalse(self.cache.exists())

    def test_validated_download_is_separate_and_fingerprint_stable(self):
        first = self.resolve()
        second = self.resolve()
        self.assertEqual(first.mode, "github")
        self.assertEqual(first.status, "current")
        self.assertIsNone(first.warning)
        self.assertEqual(first.fingerprint, hashlib.sha256(self.content).hexdigest())
        self.assertEqual(first.path, second.path)
        self.assertNotEqual(first.path, self.local)
        self.assertEqual(first.path.read_bytes(), self.content)
        self.assertEqual(self.local.read_bytes(), self.content)
        self.download.assert_called_once()

    def test_not_modified_revalidates_using_etag(self):
        initial = self.resolve()
        self.download.return_value = (None, '"version1"')
        refreshed = self.resolve(force_refresh=True)
        self.assertEqual(initial.fingerprint, refreshed.fingerprint)
        self.assertEqual(self.download.call_args.args[1], '"version1"')
        self.assertEqual(refreshed.status, "current")
        self.assertGreaterEqual(refreshed.last_success_at, initial.last_success_at)

    def test_changed_data_selects_new_immutable_file(self):
        initial = self.resolve()
        with ZipFile(BytesIO(self.content)) as original:
            part = original.read("docProps/core.xml")
        changed = _replace_part(self.content, "docProps/core.xml", part.replace(b"</", b" </", 1))
        self.download.return_value = (changed, '"version2"')
        updated = self.resolve(force_refresh=True)
        self.assertNotEqual(initial.fingerprint, updated.fingerprint)
        self.assertEqual(updated.status, "current")
        self.assertEqual(initial.path.read_bytes(), self.content)
        self.assertEqual(self.local.read_bytes(), self.content)

    def test_invalid_remote_keeps_good_data_and_marks_stale(self):
        initial = self.resolve()
        self.download.return_value = (b"<html>GitHub error</html>", '"broken"')
        failed = self.resolve(force_refresh=True)
        repeated = self.resolve()
        self.assertEqual(failed.path, initial.path)
        self.assertEqual(failed.status, "stale")
        self.assertTrue(failed.warning)
        self.assertEqual(failed.last_success_at, initial.last_success_at)
        self.assertEqual(repeated.status, "stale")
        self.assertEqual(self.download.call_count, 2)
        self.assertEqual(initial.path.read_bytes(), self.content)

    def test_network_error_first_fetch_is_explicit_bundled_fallback_and_throttled(self):
        self.download.side_effect = public.PublicWorkbookError("GitHub is unavailable.")
        for _ in range(2):
            source = self.resolve()
            self.assertEqual(source.mode, "bundled")
            self.assertEqual(source.status, "bundled_fallback")
            self.assertTrue(source.warning)
            self.assertEqual(source.path, self.local)
        self.download.assert_called_once()

    def test_failed_cache_pointer_write_does_not_publish_invalid_pointer(self):
        initial = self.resolve()
        with mock.patch.object(public, "_atomic_write", side_effect=OSError("read only")):
            failed = self.resolve(force_refresh=True)
        self.assertEqual(failed.status, "stale")
        self.assertEqual(failed.path, initial.path)
        self.assertEqual(json.loads((initial.path.parent / "current.json").read_text())["fingerprint"], initial.fingerprint)

    def test_corrupt_cached_file_is_not_used_or_revalidated_by_etag(self):
        initial = self.resolve()
        initial.path.write_bytes(b"bad file")
        self.download.side_effect = public.PublicWorkbookError("No network.")
        source = self.resolve(force_refresh=True)
        self.assertEqual(source.mode, "bundled")
        self.assertEqual(source.path, self.local)
        self.assertIsNone(self.download.call_args.args[1])

    def test_corrupt_metadata_cannot_escape_cache_directory(self):
        source = self.resolve()
        (source.path.parent / "current.json").write_text(json.dumps({"fingerprint": "../../manual"}))
        self.download.side_effect = public.PublicWorkbookError("No network.")
        failed = self.resolve(force_refresh=True)
        self.assertEqual(failed.path, self.local)
        self.assertEqual(failed.status, "bundled_fallback")

    def test_sources_are_isolated(self):
        first = self.resolve()
        second = public.resolve_workbook(self.local, cache_dir=self.cache,
            environ={**ENABLED, "F1_PUBLIC_GITHUB_BRANCH": "codex/test"})
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(self.download.call_count, 2)

    def test_simultaneous_threads_only_download_once(self):
        start = threading.Barrier(6)
        def resolve_thread():
            start.wait()
            return self.resolve()
        with ThreadPoolExecutor(max_workers=6) as pool:
            sources = list(pool.map(lambda _: resolve_thread(), range(6)))
        self.download.assert_called_once()
        self.assertEqual({source.status for source in sources}, {"current"})
        self.assertEqual(len({source.path for source in sources}), 1)

    def test_cache_lock_is_cross_process(self):
        self.cache.mkdir()
        context = multiprocessing.get_context("spawn")
        acquired, release = context.Event(), context.Event()
        process = context.Process(target=_hold_process_lock, args=(str(self.cache), acquired, release))
        process.start()
        try:
            self.assertTrue(acquired.wait(timeout=10))
            with mock.patch.object(public, "LOCK_TIMEOUT_SECONDS", 0.1):
                with self.assertRaises(public.PublicWorkbookError):
                    with public._cache_lock(self.cache):
                        self.fail("Another process's refresh lock was bypassed")
        finally:
            release.set()
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join()
        self.assertEqual(process.exitcode, 0)

    def test_actual_workbook_passes_bounds_and_dashboard_schema(self):
        self.assertIsInstance(public.validate_snapshot(self.content), tuple)

    def test_missing_required_sheets_and_bad_xml_are_rejected(self):
        with ZipFile(BytesIO(self.content)) as archive:
            workbook = archive.read("xl/workbook.xml")
        missing_calendar = _replace_part(self.content, "xl/workbook.xml", workbook.replace(b'name="Calendar"', b'name="Removed"'))
        malformed = _replace_part(self.content, "xl/workbook.xml", b"<broken>")
        for content in (missing_calendar, malformed):
            with self.subTest():
                with self.assertRaises(public.PublicWorkbookError):
                    public.validate_snapshot(content)

    def test_missing_result_headers_are_rejected(self):
        with ZipFile(BytesIO(self.content)) as archive:
            strings = archive.read("xl/sharedStrings.xml")
        changed = _replace_part(self.content, "xl/sharedStrings.xml", strings.replace(b">Finish Pos<", b">Missing Header<"))
        with self.assertRaises(public.PublicWorkbookError):
            public.validate_snapshot(changed)

    def test_zip_bombs_paths_entities_and_duplicate_members_are_rejected(self):
        def package(name, data, duplicate=False):
            result = BytesIO()
            with ZipFile(result, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(name, data)
                if duplicate:
                    archive.writestr(name, data)
            return result.getvalue()
        candidates = [package("../outside.xml", b"<x/>"),
                      package("bomb.xml", b"0" * 1000000),
                      package("x.xml", b'<!DOCTYPE x [<!ENTITY a "bad">]><x>&a;</x>'),
                      package("x.xml", b"<x/>", duplicate=True)]
        for content in candidates:
            with self.subTest():
                with self.assertRaises(public.PublicWorkbookError):
                    public.validate_snapshot(content)

    def test_overlarge_download_rejected_before_zip_open(self):
        with mock.patch.object(public, "MAX_DOWNLOAD_BYTES", 4):
            with self.assertRaises(public.PublicWorkbookError):
                public.validate_snapshot(b"12345")

    def test_sparse_worksheet_cannot_allocate_an_unbounded_grid(self):
        oversized = (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                     b'<dimension ref="A1:ZZ200000"/><sheetData/></worksheet>')
        changed = _replace_part(self.content, "xl/worksheets/sheet1.xml", oversized)
        with self.assertRaises(public.PublicWorkbookError):
            public.validate_snapshot(changed)

    def test_invalid_settings_have_no_network_access(self):
        for key, value in [
            ("F1_PUBLIC_GITHUB_OWNER", "https://evil.example"),
            ("F1_PUBLIC_GITHUB_REPOSITORY", "repo?token=x"),
            ("F1_PUBLIC_GITHUB_BRANCH", "../main"),
            ("F1_PUBLIC_GITHUB_BRANCH", "main#fragment"),
            ("F1_PUBLIC_GITHUB_WORKBOOK_PATH", "//evil.example/file.xlsx"),
            ("F1_PUBLIC_GITHUB_WORKBOOK_PATH", "%2e%2e/file.xlsx"),
            ("F1_PUBLIC_GITHUB_WORKBOOK_PATH", "file.xlsm"),
        ]:
            with self.subTest(key=key, value=value):
                source = public.resolve_workbook(self.local, environ={**ENABLED, key: value}, cache_dir=self.cache)
                self.assertEqual(source.status, "configuration_error")
                self.assertTrue(source.warning)
        self.download.assert_not_called()


class DownloadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.opener = mock.Mock()
        self.patch = mock.patch.object(public, "build_opener", return_value=self.opener)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.response = mock.MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.status = 200
        self.response.headers = {"ETag": '"test"'}
        self.response.read.side_effect = [b"abcd", b""]
        self.opener.open.return_value = self.response

    def test_request_uses_only_fixed_https_host_get_and_no_credentials(self):
        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "must-not-leak", "HTTPS_PROXY": "http://attacker.test"}):
            data, etag = public._download(public.GitHubWorkbookConfig(), '"old"')
        request = self.opener.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://raw.githubusercontent.com/rcr1995/f1-game-dashboard/main/F1_Standings.xlsx?"))
        self.assertEqual(request.method, "GET")
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("must-not-leak", str(request.headers))
        self.assertEqual((data, etag), (b"abcd", '"test"'))
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], public.NETWORK_TIMEOUT_SECONDS)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(public._NoRedirects().redirect_request(None, None, 302, "", {}, "http://localhost/private"))
        self.opener.open.side_effect = HTTPError("https://raw.githubusercontent.com/", 302, "", {}, None)
        with self.assertRaises(public.PublicWorkbookError):
            public._download(public.GitHubWorkbookConfig(), None)

    def test_304_only_accepted_after_validated_snapshot(self):
        self.opener.open.side_effect = HTTPError("https://raw.githubusercontent.com/", 304, "", {}, None)
        self.assertEqual(public._download(public.GitHubWorkbookConfig(), '"known"'), (None, '"known"'))
        with self.assertRaises(public.PublicWorkbookError):
            public._download(public.GitHubWorkbookConfig(), None)

    def test_size_limit_applies_with_and_without_content_length(self):
        self.response.headers = {"Content-Length": str(public.MAX_DOWNLOAD_BYTES + 1)}
        with self.assertRaises(public.PublicWorkbookError):
            public._download(public.GitHubWorkbookConfig(), None)
        self.response.headers = {}
        with mock.patch.object(public, "MAX_DOWNLOAD_BYTES", 3):
            with self.assertRaises(public.PublicWorkbookError):
                public._download(public.GitHubWorkbookConfig(), None)

    def test_encoded_response_is_not_decompressed_unbounded(self):
        self.response.headers = {"Content-Encoding": "gzip"}
        with self.assertRaises(public.PublicWorkbookError):
            public._download(public.GitHubWorkbookConfig(), None)

    def test_bad_etags_are_not_sent_or_persisted(self):
        self.response.headers = {"ETag": "bad\r\ninjected: true"}
        _, etag = public._download(public.GitHubWorkbookConfig(), ["not", "text"])
        request = self.opener.open.call_args.args[0]
        self.assertNotIn("If-none-match", request.headers)
        self.assertIsNone(etag)

    def test_download_has_total_deadline(self):
        with mock.patch.object(public.time, "monotonic", side_effect=[0, public.DOWNLOAD_DEADLINE_SECONDS + 1]):
            with self.assertRaises(public.PublicWorkbookError):
                public._download(public.GitHubWorkbookConfig(), None)


if __name__ == "__main__":
    unittest.main()
