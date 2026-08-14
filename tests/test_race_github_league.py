from __future__ import annotations

from base64 import b64decode, b64encode
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import league_workbook
import race_github as github
import race_workbook as workbook

from test_race_github import QueueTransport, git_blob_sha, json_response, test_private_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class HostedLeaguePersistenceTests(unittest.TestCase):
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
            workbook_path="F1_Standings.xlsx",
        )
        self.mutation = league_workbook.LeagueWorkbookMutation(
            league_config=(
                {
                    "League ID": "league-2027-01",
                    "Game": "F1 27",
                    "Season": "2027-T01",
                    "League Name": "New League",
                    "Status": "Active",
                    "Created UTC": "2026-08-14T15:00:00Z",
                    "Schema Version": 1,
                },
            )
        )

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
            "mutation": self.mutation,
            "expected_blob_sha": git_blob_sha(content),
            "approved": True,
            "commit_message": "Create New League 2027",
        }

    def test_missing_approval_makes_no_network_request(self):
        transport = QueueTransport([])
        kwargs = self.publish_kwargs(b"original")
        kwargs["approved"] = False

        with self.assertRaises(workbook.ApprovalRequiredError):
            github.publish_league_workbook_update(
                self.config,
                transport=transport,
                **kwargs,
            )

        self.assertEqual(transport.calls, [])

    def test_stale_blob_stops_before_local_transaction(self):
        remote_content = b"new remote workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(remote_content)])
        kwargs = self.publish_kwargs(b"reviewed old workbook")

        with mock.patch.object(
            league_workbook,
            "commit_league_workbook_update",
        ) as local_commit:
            with self.assertRaises(github.GitHubConflictError):
                github.publish_league_workbook_update(
                    self.config,
                    transport=transport,
                    **kwargs,
                )

        local_commit.assert_not_called()
        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_validated_league_update_is_published_once_with_blob_cas(self):
        original = b"original workbook"
        updated = b"validated league workbook"
        old_blob_sha = git_blob_sha(original)
        new_blob_sha = git_blob_sha(updated)
        commit_sha = "d" * 40
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

        def fake_local_commit(
            path: Path,
            **kwargs: object,
        ) -> league_workbook.LeagueWorkbookCommitResult:
            temporary_path = Path(path)
            temporary_paths.append(temporary_path)
            self.assertEqual(temporary_path.read_bytes(), original)
            self.assertIs(kwargs["mutation"], self.mutation)
            self.assertTrue(kwargs["approved"])
            self.assertEqual(
                kwargs["expected_sha256"],
                workbook.workbook_fingerprint(temporary_path),
            )
            temporary_path.write_bytes(updated)
            return league_workbook.LeagueWorkbookCommitResult(
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
                backup_path=temporary_path.parent / "backup.xlsx",
                rows_added_by_sheet={"League Config": 1, "Roster Config": 22},
                calendar_rows_added=24,
                changed_parts=("xl/workbook.xml", "xl/worksheets/sheet2.xml"),
            )

        with mock.patch.object(
            league_workbook,
            "commit_league_workbook_update",
            side_effect=fake_local_commit,
        ):
            result = github.publish_league_workbook_update(
                self.config,
                transport=transport,
                **self.publish_kwargs(original),
            )

        self.assertEqual(result.commit_sha, commit_sha)
        self.assertEqual(result.blob_sha, new_blob_sha)
        self.assertEqual(result.rows_added_by_sheet["Roster Config"], 22)
        self.assertEqual(result.calendar_rows_added, 24)
        self.assertEqual(
            result.changed_parts,
            ("xl/workbook.xml", "xl/worksheets/sheet2.xml"),
        )
        self.assertTrue(temporary_paths)
        self.assertFalse(temporary_paths[0].exists())
        self.assertEqual(
            [call["method"] for call in transport.calls],
            ["POST", "GET", "PUT"],
        )
        publish_body = json.loads(transport.calls[-1]["body"])
        self.assertEqual(publish_body["sha"], old_blob_sha)
        self.assertEqual(publish_body["branch"], "main")
        self.assertEqual(publish_body["message"], "Create New League 2027")
        self.assertEqual(b64decode(publish_body["content"]), updated)

    def test_local_validation_failure_never_calls_put(self):
        original = b"original workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(original)])

        with mock.patch.object(
            league_workbook,
            "commit_league_workbook_update",
            side_effect=league_workbook.LeagueWorkbookError("invalid mutation"),
        ):
            with self.assertRaises(league_workbook.LeagueWorkbookError):
                github.publish_league_workbook_update(
                    self.config,
                    transport=transport,
                    **self.publish_kwargs(original),
                )

        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_contents_conflict_is_not_retried(self):
        original = b"original workbook"
        updated = b"updated league workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                json_response(409, {"message": "is at a different sha"}),
            ]
        )

        def fake_local_commit(
            path: Path,
            **_: object,
        ) -> league_workbook.LeagueWorkbookCommitResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return league_workbook.LeagueWorkbookCommitResult(
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
                backup_path=temporary_path.parent / "backup.xlsx",
                rows_added_by_sheet={"League Config": 1},
                calendar_rows_added=0,
                changed_parts=("xl/workbook.xml",),
            )

        with mock.patch.object(
            league_workbook,
            "commit_league_workbook_update",
            side_effect=fake_local_commit,
        ):
            with self.assertRaises(github.GitHubConflictError):
                github.publish_league_workbook_update(
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
        updated = b"updated league workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                TimeoutError("connection ended after request"),
            ]
        )

        def fake_local_commit(
            path: Path,
            **_: object,
        ) -> league_workbook.LeagueWorkbookCommitResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return league_workbook.LeagueWorkbookCommitResult(
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
                backup_path=temporary_path.parent / "backup.xlsx",
                rows_added_by_sheet={"League Config": 1},
                calendar_rows_added=0,
                changed_parts=("xl/workbook.xml",),
            )

        with mock.patch.object(
            league_workbook,
            "commit_league_workbook_update",
            side_effect=fake_local_commit,
        ):
            with self.assertRaises(github.GitHubNetworkError) as raised:
                github.publish_league_workbook_update(
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


if __name__ == "__main__":
    unittest.main()
