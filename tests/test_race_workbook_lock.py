from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import race_workbook as workbook


@contextmanager
def temporary_workbook():
    descriptor, temporary_name = tempfile.mkstemp(suffix=".xlsx")
    os.close(descriptor)
    path = Path(temporary_name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
        workbook._workbook_lock_path(path).unlink(missing_ok=True)


class RaceWorkbookLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata = workbook.RaceMetadata(
            game="F1 26",
            season="Season 1",
            league="Lock test",
            round_number=1,
            event_type="R",
            gp_name="Test GP",
        )

    def commit(self, path: Path):
        return workbook.commit_race_import(
            path,
            metadata=self.metadata,
            rows=(),
            scoring_profile={},
            expected_sha256="unused-by-mocked-transaction",
            approved=True,
        )

    def test_concurrent_calls_for_one_workbook_are_serialized(self):
        with temporary_workbook() as path:
            path.write_bytes(b"unchanged test workbook")
            original_bytes = path.read_bytes()
            callers_ready = threading.Barrier(2)
            state_lock = threading.Lock()
            active_calls = 0
            peak_active_calls = 0
            completed_calls = 0

            def mocked_transaction(*args, **kwargs):
                nonlocal active_calls, peak_active_calls, completed_calls
                with state_lock:
                    active_calls += 1
                    peak_active_calls = max(peak_active_calls, active_calls)
                try:
                    # Sleeping releases the GIL and gives the competing caller
                    # ample opportunity to enter if the interprocess lock is
                    # missing or scoped too narrowly.
                    time.sleep(0.1)
                finally:
                    with state_lock:
                        active_calls -= 1
                        completed_calls += 1
                return completed_calls

            def invoke_commit():
                callers_ready.wait(timeout=2)
                return self.commit(path)

            with mock.patch.object(workbook, "_commit_race_import_locked", side_effect=mocked_transaction):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(invoke_commit) for _ in range(2)]
                    results = [future.result(timeout=3) for future in futures]

            self.assertEqual(peak_active_calls, 1)
            self.assertEqual(sorted(results), [1, 2])
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_lock_timeout_does_not_enter_transaction_or_change_workbook(self):
        with temporary_workbook() as path:
            path.write_bytes(b"unchanged test workbook")
            original_bytes = path.read_bytes()

            with workbook._workbook_lock(path, timeout_seconds=1.0):
                with (
                    mock.patch.object(workbook, "_WORKBOOK_LOCK_TIMEOUT_SECONDS", 0.05),
                    mock.patch.object(workbook, "_WORKBOOK_LOCK_POLL_SECONDS", 0.005),
                    mock.patch.object(workbook, "_commit_race_import_locked") as transaction,
                ):
                    with self.assertRaisesRegex(workbook.WorkbookUpdateError, "Another race import"):
                        self.commit(path)

            transaction.assert_not_called()
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_lock_open_failure_does_not_enter_transaction_or_change_workbook(self):
        with temporary_workbook() as path:
            path.write_bytes(b"unchanged test workbook")
            original_bytes = path.read_bytes()

            with (
                mock.patch.object(
                    workbook,
                    "_open_workbook_lock_file",
                    side_effect=PermissionError("test lock permission failure"),
                ),
                mock.patch.object(workbook, "_commit_race_import_locked") as transaction,
            ):
                with self.assertRaisesRegex(workbook.WorkbookUpdateError, "Could not open"):
                    self.commit(path)

            transaction.assert_not_called()
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_transaction_failure_releases_lock_for_the_next_call(self):
        with temporary_workbook() as path:
            path.write_bytes(b"unchanged test workbook")

            with mock.patch.object(
                workbook,
                "_commit_race_import_locked",
                side_effect=[RuntimeError("staging failed"), "second call completed"],
            ):
                with self.assertRaisesRegex(RuntimeError, "staging failed"):
                    self.commit(path)
                self.assertEqual(self.commit(path), "second call completed")


if __name__ == "__main__":
    unittest.main()
