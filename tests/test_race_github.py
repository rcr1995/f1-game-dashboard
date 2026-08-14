from __future__ import annotations

from base64 import b64decode, b64encode, urlsafe_b64decode
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import race_github as github
import race_workbook as workbook


def _der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _der_element(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _der_length(len(value)) + value


def _der_integer(value: int) -> bytes:
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:
        encoded = b"\x00" + encoded
    return _der_element(0x02, encoded)


def test_private_key() -> str:
    """Build a non-secret PKCS1 fixture sufficient to exercise JWT encoding."""
    modulus = (1 << 1024) - 109
    values = [0, modulus, 65537, 1, 1, 1, 1, 1, 1]
    der = _der_element(0x30, b"".join(_der_integer(value) for value in values))
    payload = b64encode(der).decode("ascii")
    lines = [payload[index : index + 64] for index in range(0, len(payload), 64)]
    return "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END RSA PRIVATE KEY-----"


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(content)}\0".encode("ascii") + content,
        usedforsecurity=False,
    ).hexdigest()


def json_response(status: int, payload: object) -> github.HttpResponse:
    return github.HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


class QueueTransport:
    def __init__(self, responses: list[github.HttpResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> github.HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("Unexpected GitHub request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class GitHubPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        temporary_directory = TemporaryDirectory
        temporary_patch = mock.patch.object(
            github,
            "TemporaryDirectory",
            side_effect=lambda **kwargs: temporary_directory(dir=project_root, **kwargs),
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
            round_number=4,
            event_type="R",
            gp_name="Hungarian GP",
        )

    def token_response(self) -> github.HttpResponse:
        return json_response(
            201,
            {"token": "installation-secret", "expires_at": "2026-08-13T14:00:00Z"},
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

    def test_jwt_is_rs256_short_lived_and_does_not_expose_private_key(self):
        token = github._create_app_jwt(self.config, clock=lambda: 1_700_000_000)
        header_segment, payload_segment, signature_segment = token.split(".")

        def decode_segment(segment: str) -> bytes:
            return urlsafe_b64decode(segment + ("=" * (-len(segment) % 4)))

        self.assertEqual(json.loads(decode_segment(header_segment)), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(
            json.loads(decode_segment(payload_segment)),
            {"exp": 1_700_000_540, "iat": 1_699_999_940, "iss": "12345"},
        )
        signature = decode_segment(signature_segment)
        digest = hashlib.sha256(f"{header_segment}.{payload_segment}".encode("ascii")).digest()
        self.assertEqual(len(signature), 128)
        self.assertTrue(signature.startswith(b"\x00\x01\xff"))
        self.assertTrue(signature.endswith(bytes.fromhex("3031300d060960864801650304020105000420") + digest))
        self.assertNotIn("PRIVATE KEY", repr(self.config))

    def test_fetch_scopes_installation_token_and_returns_verified_blob(self):
        original = b"workbook bytes"
        transport = QueueTransport([self.token_response(), self.workbook_response(original)])

        remote = github.fetch_remote_workbook(
            self.config,
            transport=transport,
            clock=lambda: 1_700_000_000,
        )

        self.assertEqual(remote.content, original)
        self.assertEqual(remote.blob_sha, git_blob_sha(original))
        self.assertNotIn(original.decode(), repr(remote))
        token_call, fetch_call = transport.calls
        self.assertEqual(token_call["method"], "POST")
        self.assertTrue(str(token_call["url"]).endswith("/app/installations/67890/access_tokens"))
        self.assertEqual(
            json.loads(token_call["body"]),
            {"repositories": ["f1-game-dashboard"], "permissions": {"contents": "write"}},
        )
        self.assertTrue(str(token_call["headers"]["Authorization"]).startswith("Bearer eyJ"))
        self.assertEqual(fetch_call["method"], "GET")
        self.assertIn("data/F1%20Standings.xlsx?ref=main", str(fetch_call["url"]))
        self.assertEqual(fetch_call["headers"]["Authorization"], "Bearer installation-secret")
        self.assertEqual(fetch_call["headers"]["X-GitHub-Api-Version"], "2022-11-28")

    def test_missing_approval_makes_no_network_request(self):
        transport = QueueTransport([])

        with self.assertRaises(workbook.ApprovalRequiredError):
            github.publish_race_import(
                self.config,
                metadata=self.metadata,
                rows=[],
                scoring_profile={},
                expected_blob_sha="0" * 40,
                approved=False,
                transport=transport,
            )

        self.assertEqual(transport.calls, [])

    def test_stale_review_stops_before_staging_or_publication(self):
        original = b"new remote workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(original)])

        with mock.patch.object(workbook, "commit_race_import") as local_commit:
            with self.assertRaises(github.GitHubConflictError):
                github.publish_race_import(
                    self.config,
                    metadata=self.metadata,
                    rows=[],
                    scoring_profile={},
                    expected_blob_sha="0" * 40,
                    approved=True,
                    transport=transport,
                )

        local_commit.assert_not_called()
        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_validated_workbook_is_published_with_expected_blob_sha(self):
        original = b"original workbook"
        updated = b"validated updated workbook"
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

        def fake_local_commit(path: Path, **kwargs: object) -> workbook.CommitResult:
            temporary_path = Path(path)
            temporary_paths.append(temporary_path)
            self.assertEqual(temporary_path.read_bytes(), original)
            self.assertTrue(kwargs["approved"])
            self.assertTrue(kwargs["require_complete_timing"])
            self.assertEqual(kwargs["expected_sha256"], workbook.workbook_fingerprint(temporary_path))
            temporary_path.write_bytes(updated)
            return workbook.CommitResult(
                rows_added=22,
                first_excel_row=1758,
                last_excel_row=1779,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=True,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(workbook, "commit_race_import", side_effect=fake_local_commit):
            result = github.publish_race_import(
                self.config,
                metadata=self.metadata,
                rows=[{"Position": 1, "Driver": "Driver"}],
                scoring_profile={1: 25.0},
                expected_blob_sha=old_blob_sha,
                approved=True,
                commit_message="Import Hungarian GP",
                transport=transport,
            )

        self.assertEqual(result.commit_sha, commit_sha)
        self.assertEqual(
            result.commit_url,
            f"https://github.com/rcr1995/f1-game-dashboard/commit/{commit_sha}",
        )
        self.assertEqual(result.blob_sha, new_blob_sha)
        self.assertEqual(result.rows_added, 22)
        self.assertTrue(temporary_paths)
        self.assertFalse(temporary_paths[0].exists())
        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET", "PUT"])
        publish_body = json.loads(transport.calls[-1]["body"])
        self.assertEqual(publish_body["sha"], old_blob_sha)
        self.assertEqual(publish_body["branch"], "main")
        self.assertEqual(publish_body["message"], "Import Hungarian GP")
        self.assertEqual(b64decode(publish_body["content"]), updated)

    def test_local_validation_failure_never_calls_publication(self):
        original = b"original workbook"
        transport = QueueTransport([self.token_response(), self.workbook_response(original)])

        with mock.patch.object(
            workbook,
            "commit_race_import",
            side_effect=workbook.WorkbookUpdateError("invalid reviewed rows"),
        ):
            with self.assertRaises(workbook.WorkbookUpdateError):
                github.publish_race_import(
                    self.config,
                    metadata=self.metadata,
                    rows=[],
                    scoring_profile={},
                    expected_blob_sha=git_blob_sha(original),
                    approved=True,
                    transport=transport,
                )

        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET"])

    def test_contents_api_conflict_is_typed_and_not_retried(self):
        original = b"original workbook"
        updated = b"updated workbook"
        transport = QueueTransport(
            [
                self.token_response(),
                self.workbook_response(original),
                json_response(409, {"message": "is at a different sha"}),
            ]
        )

        def fake_local_commit(path: Path, **_: object) -> workbook.CommitResult:
            temporary_path = Path(path)
            temporary_path.write_bytes(updated)
            return workbook.CommitResult(
                rows_added=1,
                first_excel_row=2,
                last_excel_row=2,
                backup_path=temporary_path.parent / "backup.xlsx",
                calendar_updated=False,
                workbook_sha256=workbook.workbook_fingerprint(temporary_path),
            )

        with mock.patch.object(workbook, "commit_race_import", side_effect=fake_local_commit):
            with self.assertRaises(github.GitHubConflictError):
                github.publish_race_import(
                    self.config,
                    metadata=self.metadata,
                    rows=[],
                    scoring_profile={},
                    expected_blob_sha=git_blob_sha(original),
                    approved=True,
                    transport=transport,
                )

        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET", "PUT"])
        self.assertEqual(transport.responses, [])

    def test_auth_api_and_network_errors_are_typed_without_echoing_secrets(self):
        auth_transport = QueueTransport(
            [json_response(401, {"message": "bad private-secret-value"})]
        )
        with self.assertRaises(github.GitHubAuthError) as auth_error:
            github.create_installation_token(self.config, transport=auth_transport)
        self.assertNotIn("private-secret-value", str(auth_error.exception))

        api_transport = QueueTransport(
            [json_response(500, {"message": "installation-secret and internal detail"})]
        )
        with self.assertRaises(github.GitHubAPIError) as api_error:
            github.create_installation_token(self.config, transport=api_transport)
        self.assertEqual(api_error.exception.status_code, 500)
        self.assertNotIn("installation-secret", str(api_error.exception))

        network_transport = QueueTransport([TimeoutError("contains-network-secret")])
        with self.assertRaises(github.GitHubNetworkError) as network_error:
            github.create_installation_token(self.config, transport=network_transport)
        self.assertNotIn("contains-network-secret", str(network_error.exception))


if __name__ == "__main__":
    unittest.main()
