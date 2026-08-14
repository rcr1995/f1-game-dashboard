from __future__ import annotations

from base64 import b64decode, b64encode
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import race_correction as correction
import race_github as github
import race_import as race
import race_workbook as workbook

from test_race_github import QueueTransport, git_blob_sha, json_response, test_private_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class HostedCorrectionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = TemporaryDirectory
        temporary_patch = mock.patch.object(
            github,
            "TemporaryDirectory",
            side_effect=lambda **kwargs: temporary_directory(
                dir=TEST_TEMP_ROOT, **kwargs
            ),
        )
        temporary_patch.start()
        self.addCleanup(temporary_patch.stop)
        self.config = github.GitHubAppConfig(
            app_id="12345",
            installation_id=67890,
            private_key=test_private_key(),
            owner="rcr1995",
            repository="f1-game-dashboard",
            branch="main",
            workbook_path="data/F1 Standings.xlsx",
        )
        self.metadata = workbook.RaceMetadata(
            game="F1 25",
            season="2026-T02",
            league="Teikirise",
            round_number=3,
            event_type="R",
            gp_name="Belgian GP",
        )
        self.event_digest = "e" * 64

    def token_response(self) -> github.HttpResponse:
        return json_response(
            201,
            {"token": "installation-secret", "expires_at": "2026-08-14T16:00:00Z"},
        )

    def workbook_response(self, content: bytes) -> github.HttpResponse:
        return json_response(
            200,
            {
                "type": "file",
                "encoding": "base64",
                "content": b64encode(content).decode("ascii"),
                "sha": git_blob_sha(content),
                "download_url": "https://example.invalid/workbook",
            },
        )

    def publish_kwargs(self, content: bytes) -> dict[str, object]:
        return {
            "metadata": self.metadata,
            "action": correction.CorrectionAction.REPLACE,
            "rows": [
                {
                    "Position": 1,
                    "Driver": "Alice",
                    "Team": "Red",
                    "Points": 25,
                    "Time": "80:00.000",
                    "Fastest Lap": "1:20.000",
                }
            ],
            "authoritative_roster": [race.DriverEntry("Alice", "Red")],
            "authoritative_scoring": {1: 25.0},
            "expected_event_digest": self.event_digest,
            "expected_blob_sha": git_blob_sha(content),
            "approved": True,
            "commit_message": "Replace Belgian GP results",
        }

    def test_missing_approval_makes_no_network_request(self):
        transport = QueueTransport([])
        kwargs = self.publish_kwargs(b"original")
        kwargs["approved"] = False

        with self.assertRaises(workbook.ApprovalRequiredError):
            github.publish_event_correction(self.config, transport=transport, **kwargs)

        self.assertEqual(transport.calls, [])

    def test_stale_blob_stops_before_local_transaction_or_put(self):
        remote_content = b"new remote workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(remote_content)])
        kwargs = self.publish_kwargs(b"reviewed old workbook")

        with mock.patch.object(correction, "commit_event_correction") as local_commit:
            with self.assertRaises(github.GitHubConflictError):
                github.publish_event_correction(self.config, transport=transport, **kwargs)

        local_commit.assert_not_called()
        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_validated_correction_is_published_once_with_reviewed_blob_cas(self):
        original = b"original workbook"
        updated = b"validated corrected workbook"
        old_blob_sha = git_blob_sha(original)
        new_blob_sha = git_blob_sha(updated)
        commit_sha = "c" * 40
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                json_response(
                    200,
                    {
                        "content": {"sha": new_blob_sha},
                        "commit": {
                            "sha": commit_sha,
                            "html_url": f"https://github.com/rcr1995/f1-game-dashboard/commit/{commit_sha}",
                        },
                    },
                ),
            ]
        )
        temporary_paths: list[Path] = []

        def fake_local_commit(path: Path, **kwargs: object) -> correction.CorrectionResult:
            temporary_path = Path(path)
            temporary_paths.append(temporary_path)
            self.assertEqual(temporary_path.read_bytes(), original)
            self.assertEqual(kwargs["action"], correction.CorrectionAction.REPLACE)
            self.assertEqual(kwargs["expected_event_digest"], self.event_digest)
            self.assertTrue(kwargs["approved"])
            self.assertEqual(
                kwargs["expected_sha256"],
                workbook.workbook_fingerprint(temporary_path),
            )
            temporary_path.write_bytes(updated)
            return correction.CorrectionResult(
                action=correction.CorrectionAction.REPLACE,
                affected_excel_rows=(1700, 1701),
                rows_replaced=2,
                rows_removed=0,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=False,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(
            correction,
            "commit_event_correction",
            side_effect=fake_local_commit,
        ):
            result = github.publish_event_correction(
                self.config,
                transport=transport,
                **self.publish_kwargs(original),
            )

        self.assertEqual(result.commit_sha, commit_sha)
        self.assertEqual(result.blob_sha, new_blob_sha)
        self.assertEqual(result.action, correction.CorrectionAction.REPLACE)
        self.assertEqual(result.affected_excel_rows, (1700, 1701))
        self.assertEqual(result.rows_replaced, 2)
        self.assertEqual(result.rows_removed, 0)
        self.assertTrue(temporary_paths)
        self.assertFalse(temporary_paths[0].exists())
        self.assertEqual(
            [call["method"] for call in transport.calls],
            ["POST", "GET", "PUT"],
        )
        publish_body = json.loads(transport.calls[-1]["body"])
        self.assertEqual(publish_body["sha"], old_blob_sha)
        self.assertEqual(publish_body["branch"], "main")
        self.assertEqual(publish_body["message"], "Replace Belgian GP results")
        self.assertEqual(b64decode(publish_body["content"]), updated)

    def test_local_failure_never_calls_publication(self):
        original = b"original workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(original)])

        with mock.patch.object(
            correction,
            "commit_event_correction",
            side_effect=correction.EventCorrectionError("invalid correction"),
        ):
            with self.assertRaises(correction.EventCorrectionError):
                github.publish_event_correction(
                    self.config,
                    transport=transport,
                    **self.publish_kwargs(original),
                )

        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_contents_conflict_is_not_retried(self):
        original = b"original workbook"
        updated = b"corrected workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                json_response(409, {"message": "is at a different sha"}),
            ]
        )

        def fake_local_commit(path: Path, **_: object) -> correction.CorrectionResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return correction.CorrectionResult(
                action=correction.CorrectionAction.REPLACE,
                affected_excel_rows=(2,),
                rows_replaced=1,
                rows_removed=0,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=False,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(correction, "commit_event_correction", side_effect=fake_local_commit):
            with self.assertRaises(github.GitHubConflictError):
                github.publish_event_correction(
                    self.config,
                    transport=transport,
                    **self.publish_kwargs(original),
                )

        self.assertEqual(
            [call["method"] for call in transport.calls],
            ["POST", "GET", "PUT"],
        )
        self.assertEqual(transport.responses, [])

    def test_put_network_failure_is_uncertain_and_not_retried(self):
        original = b"original workbook"
        updated = b"corrected workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                TimeoutError("connection ended after request"),
            ]
        )

        def fake_local_commit(path: Path, **_: object) -> correction.CorrectionResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return correction.CorrectionResult(
                action=correction.CorrectionAction.REPLACE,
                affected_excel_rows=(2,),
                rows_replaced=1,
                rows_removed=0,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=False,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(correction, "commit_event_correction", side_effect=fake_local_commit):
            with self.assertRaises(github.GitHubNetworkError) as raised:
                github.publish_event_correction(
                    self.config,
                    transport=transport,
                    **self.publish_kwargs(original),
                )

        self.assertTrue(raised.exception.publication_may_have_succeeded)
        self.assertEqual(
            [call["method"] for call in transport.calls],
            ["POST", "GET", "PUT"],
        )
        self.assertEqual(transport.responses, [])

    def test_incorrect_returned_blob_is_an_uncertain_publication_error(self):
        original = b"original workbook"
        updated = b"corrected workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                json_response(
                    200,
                    {
                        "content": {"sha": "0" * 40},
                        "commit": {
                            "sha": "f" * 40,
                            "html_url": "https://example.invalid/commit",
                        },
                    },
                ),
            ]
        )

        def fake_local_commit(path: Path, **_: object) -> correction.CorrectionResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return correction.CorrectionResult(
                action=correction.CorrectionAction.REPLACE,
                affected_excel_rows=(2,),
                rows_replaced=1,
                rows_removed=0,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=False,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(correction, "commit_event_correction", side_effect=fake_local_commit):
            with self.assertRaises(github.GitHubAPIError) as raised:
                github.publish_event_correction(
                    self.config,
                    transport=transport,
                    **self.publish_kwargs(original),
                )

        self.assertTrue(raised.exception.publication_may_have_succeeded)
        self.assertEqual(
            [call["method"] for call in transport.calls],
            ["POST", "GET", "PUT"],
        )


if __name__ == "__main__":
    unittest.main()
