"""Safe GitHub-backed persistence for hosted race imports.

The Streamlit deployment cannot durably edit its checked-out workbook.  This
module instead authenticates as a repository-scoped GitHub App installation,
downloads the reviewed workbook blob, runs the existing preservation-oriented
``race_workbook`` transaction against a temporary copy, and publishes the
validated bytes with the original blob SHA as an optimistic-concurrency guard.

The implementation deliberately has no logging and keeps credentials out of
dataclass representations and exception messages.
"""

from __future__ import annotations

from base64 import b64decode, b64encode, urlsafe_b64encode
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
import time
from typing import Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import race_workbook as workbook


DEFAULT_API_VERSION = "2022-11-28"
DEFAULT_USER_AGENT = "f1-game-dashboard-race-import"


class GitHubPersistenceError(RuntimeError):
    """Base class for hosted workbook persistence failures."""

    publication_may_have_succeeded = False


class GitHubConfigurationError(GitHubPersistenceError):
    """Raised when GitHub App or repository configuration is invalid."""


class GitHubAuthError(GitHubPersistenceError):
    """Raised when GitHub rejects the app or installation credentials."""


class GitHubConflictError(GitHubPersistenceError):
    """Raised when the reviewed Git blob is no longer current."""


class GitHubNetworkError(GitHubPersistenceError):
    """Raised when GitHub cannot be reached or a response cannot be read."""

    def __init__(self, message: str, *, publication_may_have_succeeded: bool = False) -> None:
        super().__init__(message)
        self.publication_may_have_succeeded = publication_may_have_succeeded


class GitHubAPIError(GitHubPersistenceError):
    """Raised for a non-authentication, non-conflict GitHub API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        publication_may_have_succeeded: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.publication_may_have_succeeded = publication_may_have_succeeded


@dataclass(frozen=True)
class GitHubAppConfig:
    """Least-privilege GitHub App and workbook repository configuration."""

    app_id: str
    installation_id: int
    private_key: str = field(repr=False)
    owner: str = ""
    repository: str = ""
    branch: str = "main"
    workbook_path: str = "F1_Standings.xlsx"
    api_base_url: str = "https://api.github.com"
    web_base_url: str = "https://github.com"
    api_version: str = DEFAULT_API_VERSION
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not str(self.app_id).strip():
            raise GitHubConfigurationError("GitHub App ID is missing.")
        try:
            installation_id = int(self.installation_id)
        except (TypeError, ValueError) as exc:
            raise GitHubConfigurationError("GitHub App installation ID is invalid.") from exc
        if installation_id <= 0:
            raise GitHubConfigurationError("GitHub App installation ID is invalid.")
        object.__setattr__(self, "installation_id", installation_id)

        private_key = str(self.private_key or "").strip()
        if "\\n" in private_key and "\n" not in private_key:
            private_key = private_key.replace("\\n", "\n")
        if "PRIVATE KEY" not in private_key:
            raise GitHubConfigurationError("GitHub App private key is missing or invalid.")
        object.__setattr__(self, "private_key", private_key)

        for value, label in ((self.owner, "owner"), (self.repository, "repository")):
            if not value or "/" in value or "\\" in value or value in {".", ".."}:
                raise GitHubConfigurationError(f"GitHub {label} is invalid.")
        if not self.branch.strip():
            raise GitHubConfigurationError("GitHub branch is missing.")

        candidate = PurePosixPath(self.workbook_path.replace("\\", "/"))
        if candidate.is_absolute() or not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
            raise GitHubConfigurationError("GitHub workbook path is invalid.")
        object.__setattr__(self, "workbook_path", candidate.as_posix())

        if not self.api_base_url.startswith(("https://", "http://")):
            raise GitHubConfigurationError("GitHub API base URL is invalid.")
        if not self.web_base_url.startswith(("https://", "http://")):
            raise GitHubConfigurationError("GitHub web base URL is invalid.")
        if self.timeout_seconds <= 0:
            raise GitHubConfigurationError("GitHub request timeout must be positive.")


@dataclass(frozen=True)
class InstallationToken:
    token: str = field(repr=False)
    expires_at: str


@dataclass(frozen=True)
class RemoteWorkbook:
    content: bytes = field(repr=False)
    blob_sha: str
    download_url: str | None = None


@dataclass(frozen=True)
class HostedCommitResult:
    commit_sha: str
    commit_url: str
    blob_sha: str
    rows_added: int
    first_excel_row: int
    last_excel_row: int
    calendar_updated: bool
    workbook_sha256: str


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


HttpTransport = Callable[[str, str, Mapping[str, str], bytes | None, float], HttpResponse]
Clock = Callable[[], float]


def _urlopen_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> HttpResponse:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is validated configuration.
            return HttpResponse(
                status=int(response.status),
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        try:
            response_body = exc.read()
        except OSError:
            response_body = b""
        return HttpResponse(status=int(exc.code), body=response_body, headers=dict(exc.headers or {}))
    except (URLError, TimeoutError, OSError) as exc:
        raise GitHubNetworkError("GitHub could not be reached. Try the update again.") from exc


def _base64url(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _read_der_element(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    if offset + 2 > len(data):
        raise ValueError("truncated DER")
    tag = data[offset]
    first_length = data[offset + 1]
    cursor = offset + 2
    if first_length & 0x80:
        length_bytes = first_length & 0x7F
        if length_bytes == 0 or length_bytes > 4 or cursor + length_bytes > len(data):
            raise ValueError("invalid DER length")
        length = int.from_bytes(data[cursor : cursor + length_bytes], "big")
        cursor += length_bytes
    else:
        length = first_length
    end = cursor + length
    if end > len(data):
        raise ValueError("truncated DER value")
    return tag, data[cursor:end], end


def _pem_payload(private_key: str) -> tuple[str, bytes]:
    match = re.fullmatch(
        r"\s*-----BEGIN (RSA PRIVATE KEY|PRIVATE KEY)-----\s*(.*?)\s*"
        r"-----END \1-----\s*",
        private_key,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("unsupported PEM envelope")
    encoded = re.sub(r"\s+", "", match.group(2))
    return match.group(1), b64decode(encoded, validate=True)


def _pkcs1_rsa_values(der: bytes) -> tuple[int, int]:
    tag, sequence, end = _read_der_element(der)
    if tag != 0x30 or end != len(der):
        raise ValueError("invalid RSA key sequence")
    integers: list[int] = []
    cursor = 0
    while cursor < len(sequence):
        item_tag, value, cursor = _read_der_element(sequence, cursor)
        if item_tag != 0x02:
            raise ValueError("invalid RSA key field")
        integers.append(int.from_bytes(value, "big", signed=False))
    if len(integers) < 9 or integers[0] not in {0, 1}:
        raise ValueError("incomplete RSA private key")
    modulus, private_exponent = integers[1], integers[3]
    if modulus <= 0 or private_exponent <= 0:
        raise ValueError("invalid RSA private values")
    return modulus, private_exponent


def _rsa_private_values(private_key: str) -> tuple[int, int]:
    label, der = _pem_payload(private_key)
    if label == "RSA PRIVATE KEY":
        return _pkcs1_rsa_values(der)

    tag, sequence, end = _read_der_element(der)
    if tag != 0x30 or end != len(der):
        raise ValueError("invalid PKCS8 key sequence")
    cursor = 0
    version_tag, _, cursor = _read_der_element(sequence, cursor)
    algorithm_tag, _, cursor = _read_der_element(sequence, cursor)
    key_tag, key_value, cursor = _read_der_element(sequence, cursor)
    if version_tag != 0x02 or algorithm_tag != 0x30 or key_tag != 0x04:
        raise ValueError("invalid PKCS8 private key")
    return _pkcs1_rsa_values(key_value)


def _create_app_jwt(config: GitHubAppConfig, *, clock: Clock = time.time) -> str:
    """Create a GitHub App RS256 JWT using only Python's standard library."""
    now = int(clock())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": now - 60, "exp": now + 540, "iss": str(config.app_id)}
    encoded_header = _base64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _base64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")

    try:
        modulus, private_exponent = _rsa_private_values(config.private_key)
        key_size = (modulus.bit_length() + 7) // 8
        digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
        padding_size = key_size - len(digest_info) - 3
        if padding_size < 8:
            raise ValueError("RSA key is too short")
        encoded_message = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        signature_value = pow(int.from_bytes(encoded_message, "big"), private_exponent, modulus)
        signature = signature_value.to_bytes(key_size, "big")
    except (ValueError, TypeError) as exc:
        raise GitHubConfigurationError("GitHub App private key is invalid.") from exc
    return f"{encoded_header}.{encoded_payload}.{_base64url(signature)}"


def _api_message_mentions_sha(response_body: bytes) -> bool:
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str):
        return False
    return "sha" in message.casefold()


class GitHubAppClient:
    """Authenticated client for the two GitHub operations this workflow needs."""

    def __init__(
        self,
        config: GitHubAppConfig,
        *,
        transport: HttpTransport | None = None,
        clock: Clock = time.time,
    ) -> None:
        self.config = config
        self._transport = transport or _urlopen_transport
        self._clock = clock

    def _headers(self, bearer: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {bearer}",
            "X-GitHub-Api-Version": self.config.api_version,
            "User-Agent": DEFAULT_USER_AGENT,
        }

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        bearer: str,
        payload: Mapping[str, object] | None = None,
        expected_status: set[int],
        operation: str,
    ) -> dict[str, object]:
        body = None
        headers = self._headers(bearer)
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            response = self._transport(method, url, headers, body, self.config.timeout_seconds)
        except GitHubNetworkError as exc:
            if method == "PUT" and not exc.publication_may_have_succeeded:
                raise GitHubNetworkError(
                    "GitHub did not confirm the update. Check the app before trying again.",
                    publication_may_have_succeeded=True,
                ) from exc
            raise
        except (TimeoutError, OSError, URLError) as exc:
            raise GitHubNetworkError(
                "GitHub did not confirm the update. Check the app before trying again."
                if method == "PUT"
                else "GitHub could not be reached. Try the update again.",
                publication_may_have_succeeded=method == "PUT",
            ) from exc

        if response.status not in expected_status:
            if response.status in {401, 403}:
                raise GitHubAuthError("GitHub rejected the app credentials or repository permissions.")
            if response.status == 409 or (
                method == "PUT" and response.status == 422 and _api_message_mentions_sha(response.body)
            ):
                raise GitHubConflictError(
                    "The workbook changed while this result was being published. Reload and review again."
                )
            raise GitHubAPIError(
                f"GitHub {operation} failed with status {response.status}.",
                status_code=response.status,
            )
        try:
            parsed = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAPIError(
                f"GitHub returned an invalid response during {operation}.",
                status_code=response.status,
                publication_may_have_succeeded=method == "PUT",
            ) from exc
        if not isinstance(parsed, dict):
            raise GitHubAPIError(
                f"GitHub returned an invalid response during {operation}.",
                status_code=response.status,
                publication_may_have_succeeded=method == "PUT",
            )
        return parsed

    def create_installation_token(self) -> InstallationToken:
        jwt = _create_app_jwt(self.config, clock=self._clock)
        installation = quote(str(self.config.installation_id), safe="")
        url = f"{self.config.api_base_url.rstrip('/')}/app/installations/{installation}/access_tokens"
        response = self._request_json(
            "POST",
            url,
            bearer=jwt,
            payload={
                "repositories": [self.config.repository],
                "permissions": {"contents": "write"},
            },
            expected_status={201},
            operation="installation authentication",
        )
        token = response.get("token")
        expires_at = response.get("expires_at")
        if not isinstance(token, str) or not token or not isinstance(expires_at, str) or not expires_at:
            raise GitHubAuthError("GitHub returned an invalid installation credential.")
        return InstallationToken(token=token, expires_at=expires_at)

    def _contents_url(self, *, include_ref: bool) -> str:
        owner = quote(self.config.owner, safe="")
        repository = quote(self.config.repository, safe="")
        path = quote(self.config.workbook_path, safe="/")
        base = f"{self.config.api_base_url.rstrip('/')}/repos/{owner}/{repository}/contents/{path}"
        return f"{base}?{urlencode({'ref': self.config.branch})}" if include_ref else base

    def _fetch_with_token(self, token: InstallationToken) -> RemoteWorkbook:
        response = self._request_json(
            "GET",
            self._contents_url(include_ref=True),
            bearer=token.token,
            expected_status={200},
            operation="workbook download",
        )
        if response.get("type") != "file" or response.get("encoding") != "base64":
            raise GitHubAPIError("GitHub did not return the configured workbook as a file.")
        content = response.get("content")
        blob_sha = response.get("sha")
        if not isinstance(content, str) or not isinstance(blob_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", blob_sha):
            raise GitHubAPIError("GitHub returned incomplete workbook metadata.")
        try:
            workbook_bytes = b64decode("".join(content.split()), validate=True)
        except (ValueError, TypeError) as exc:
            raise GitHubAPIError("GitHub returned invalid workbook content.") from exc
        calculated_sha = hashlib.sha1(
            f"blob {len(workbook_bytes)}\0".encode("ascii") + workbook_bytes,
            usedforsecurity=False,
        ).hexdigest()
        if calculated_sha.casefold() != blob_sha.casefold():
            raise GitHubAPIError("GitHub workbook content did not match its blob identifier.")
        download_url = response.get("download_url")
        return RemoteWorkbook(
            content=workbook_bytes,
            blob_sha=blob_sha,
            download_url=download_url if isinstance(download_url, str) else None,
        )

    def fetch_workbook(self) -> RemoteWorkbook:
        return self._fetch_with_token(self.create_installation_token())

    def publish_race_import(
        self,
        *,
        metadata: workbook.RaceMetadata,
        rows: Iterable[Mapping[str, object]],
        scoring_profile: Mapping[int, float],
        expected_blob_sha: str,
        approved: bool,
        commit_message: str | None = None,
    ) -> HostedCommitResult:
        """Validate locally and atomically replace the reviewed remote blob."""
        if not approved:
            raise workbook.ApprovalRequiredError("GitHub update requires explicit approval from the review screen.")
        reviewed_blob_sha = str(expected_blob_sha or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", reviewed_blob_sha):
            raise GitHubConflictError("The reviewed workbook version is missing or invalid. Reload and review again.")
        message = (commit_message or "Import race results from approved screenshots").strip()
        if not message:
            raise GitHubConfigurationError("GitHub commit message cannot be empty.")

        token = self.create_installation_token()
        remote = self._fetch_with_token(token)
        if remote.blob_sha.casefold() != reviewed_blob_sha.casefold():
            raise GitHubConflictError(
                "The workbook changed after this review was created. Reload and review again."
            )

        approved_rows = [dict(row) for row in rows]
        with TemporaryDirectory(prefix="f1-hosted-race-import-") as temporary_directory:
            temporary_path = Path(temporary_directory) / Path(self.config.workbook_path).name
            temporary_path.write_bytes(remote.content)
            local_result = workbook.commit_race_import(
                temporary_path,
                metadata=metadata,
                rows=approved_rows,
                scoring_profile=scoring_profile,
                expected_sha256=workbook.workbook_fingerprint(temporary_path),
                approved=True,
                backup_directory=Path(temporary_directory) / "backup",
            )
            updated_bytes = temporary_path.read_bytes()

        response = self._request_json(
            "PUT",
            self._contents_url(include_ref=False),
            bearer=token.token,
            payload={
                "message": message,
                "content": b64encode(updated_bytes).decode("ascii"),
                "sha": remote.blob_sha,
                "branch": self.config.branch,
            },
            expected_status={200},
            operation="workbook publication",
        )
        commit = response.get("commit")
        content = response.get("content")
        if not isinstance(commit, dict) or not isinstance(content, dict):
            raise GitHubAPIError(
                "GitHub accepted the update but returned incomplete commit metadata.",
                status_code=200,
                publication_may_have_succeeded=True,
            )
        commit_sha = commit.get("sha")
        commit_url = commit.get("html_url")
        updated_blob_sha = content.get("sha")
        expected_updated_blob_sha = hashlib.sha1(
            f"blob {len(updated_bytes)}\0".encode("ascii") + updated_bytes,
            usedforsecurity=False,
        ).hexdigest()
        if (
            not isinstance(commit_sha, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha)
            or not isinstance(updated_blob_sha, str)
            or updated_blob_sha.casefold() != expected_updated_blob_sha.casefold()
        ):
            raise GitHubAPIError(
                "GitHub accepted the update but returned incomplete commit metadata.",
                status_code=200,
                publication_may_have_succeeded=True,
            )
        if not isinstance(commit_url, str) or not commit_url:
            owner = quote(self.config.owner, safe="")
            repository = quote(self.config.repository, safe="")
            commit_url = f"{self.config.web_base_url.rstrip('/')}/{owner}/{repository}/commit/{quote(commit_sha, safe='')}"
        return HostedCommitResult(
            commit_sha=commit_sha,
            commit_url=commit_url,
            blob_sha=updated_blob_sha,
            rows_added=local_result.rows_added,
            first_excel_row=local_result.first_excel_row,
            last_excel_row=local_result.last_excel_row,
            calendar_updated=local_result.calendar_updated,
            workbook_sha256=local_result.workbook_sha256,
        )


def create_installation_token(
    config: GitHubAppConfig,
    *,
    transport: HttpTransport | None = None,
    clock: Clock = time.time,
) -> InstallationToken:
    return GitHubAppClient(config, transport=transport, clock=clock).create_installation_token()


def fetch_remote_workbook(
    config: GitHubAppConfig,
    *,
    transport: HttpTransport | None = None,
    clock: Clock = time.time,
) -> RemoteWorkbook:
    return GitHubAppClient(config, transport=transport, clock=clock).fetch_workbook()


def publish_race_import(
    config: GitHubAppConfig,
    *,
    metadata: workbook.RaceMetadata,
    rows: Iterable[Mapping[str, object]],
    scoring_profile: Mapping[int, float],
    expected_blob_sha: str,
    approved: bool,
    commit_message: str | None = None,
    transport: HttpTransport | None = None,
    clock: Clock = time.time,
) -> HostedCommitResult:
    return GitHubAppClient(config, transport=transport, clock=clock).publish_race_import(
        metadata=metadata,
        rows=rows,
        scoring_profile=scoring_profile,
        expected_blob_sha=expected_blob_sha,
        approved=approved,
        commit_message=commit_message,
    )
