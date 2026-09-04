"""Opt-in, credential-free GitHub workbook reads for hosted dashboards.

The checked-in workbook is never modified. A validated, immutable snapshot in
the OS temporary directory is selected using an atomic metadata pointer. Both
thread and process locks serialize refreshes; failed downloads retain the last
good snapshot and return a visible stale status to the caller.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import threading
import time
from typing import Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
import zlib

if os.name == "nt":
    import msvcrt
else:
    import fcntl


REFRESH_SECONDS = 60
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_PART_BYTES = 24 * 1024 * 1024
MAX_ZIP_ENTRIES = 512
MAX_COMPRESSION_RATIO = 500
MAX_GRID_CELLS = 2_000_000
NETWORK_TIMEOUT_SECONDS = 5
DOWNLOAD_DEADLINE_SECONDS = 15
LOCK_TIMEOUT_SECONDS = 2
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]*$")
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


class PublicWorkbookError(ValueError):
    """A safe, non-secret reason why a public snapshot was not accepted."""


@dataclass(frozen=True)
class GitHubWorkbookConfig:
    owner: str = "rcr1995"
    repository: str = "f1-game-dashboard"
    branch: str = "main"
    workbook_path: str = "F1_Standings.xlsx"

    def __post_init__(self) -> None:
        if not _OWNER.fullmatch(self.owner) or not _REPO.fullmatch(self.repository):
            raise PublicWorkbookError("Invalid public GitHub owner or repository configuration.")
        for value in (self.branch, self.workbook_path):
            if (not value or len(value) > 240 or ".." in value or "\\" in value
                    or any(not _SEGMENT.fullmatch(part) for part in value.split("/"))):
                raise PublicWorkbookError("Invalid public GitHub branch or workbook path configuration.")
        if not self.workbook_path.lower().endswith(".xlsx"):
            raise PublicWorkbookError("The public GitHub workbook must be an .xlsx file.")

    @property
    def source_url(self) -> str:
        return "https://raw.githubusercontent.com/" + "/".join(
            quote(value, safe="/")
            for value in (self.owner, self.repository, self.branch, self.workbook_path)
        )

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(self.source_url.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkbookSource:
    path: Path
    fingerprint: str
    # mode: local (not opted in), github (verified snapshot), bundled (fallback).
    mode: str
    # status: local, current, stale, bundled_fallback, configuration_error.
    status: str
    source_url: str | None = None
    checked_at: float | None = None
    last_success_at: float | None = None
    warning: str | None = None
    validation_warnings: tuple[str, ...] = ()


def configuration(environ: Mapping[str, str] | None = None) -> GitHubWorkbookConfig | None:
    """Return None unless explicitly enabled; never read private GitHub secrets."""
    env = os.environ if environ is None else environ
    if env.get("F1_PUBLIC_GITHUB_SYNC", "0").strip() != "1":
        return None
    return GitHubWorkbookConfig(
        owner=env.get("F1_PUBLIC_GITHUB_OWNER", "rcr1995").strip(),
        repository=env.get("F1_PUBLIC_GITHUB_REPOSITORY", "f1-game-dashboard").strip(),
        branch=env.get("F1_PUBLIC_GITHUB_BRANCH", "main").strip(),
        workbook_path=env.get("F1_PUBLIC_GITHUB_WORKBOOK_PATH", "F1_Standings.xlsx").strip(),
    )


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_xml(data: bytes) -> ET.Element:
    # Reject declarations before parsing, including UTF-16/32 encodings.
    compact = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in compact or b"<!ENTITY" in compact:
        raise PublicWorkbookError("The GitHub workbook contains unsupported XML declarations.")
    try:
        return ET.fromstring(data)
    except (ET.ParseError, LookupError, ValueError) as exc:
        raise PublicWorkbookError("The GitHub workbook contains invalid XML.") from exc


def _coordinate(reference: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]{1,2})([1-9][0-9]{0,5})", reference)
    if match is None:
        raise PublicWorkbookError("The GitHub workbook exceeds safe worksheet dimensions.")
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - ord("A") + 1
    row = int(match[2])
    if row > 200000 or column * row > MAX_GRID_CELLS:
        raise PublicWorkbookError("The GitHub workbook exceeds safe worksheet dimensions.")
    return column, row


def _worksheet_bounds(root: ET.Element) -> None:
    max_column, max_row = 1, 1
    dimension = root.find(f"{{{_MAIN_NS}}}dimension")
    if dimension is not None:
        for reference in dimension.get("ref", "").split(":"):
            column, row = _coordinate(reference)
            max_column, max_row = max(max_column, column), max(max_row, row)
    for row_element in root.iter(f"{{{_MAIN_NS}}}row"):
        row = row_element.get("r", "")
        if not re.fullmatch(r"[1-9][0-9]{0,5}", row) or int(row) > 200000:
            raise PublicWorkbookError("The GitHub workbook exceeds safe worksheet dimensions.")
        max_row = max(max_row, int(row))
    for cell in root.iter(f"{{{_MAIN_NS}}}c"):
        column, row = _coordinate(cell.get("r", ""))
        max_column, max_row = max(max_column, column), max(max_row, row)
    if max_column * max_row > MAX_GRID_CELLS:
        raise PublicWorkbookError("The GitHub workbook exceeds safe worksheet dimensions.")


def validate_snapshot(content: bytes) -> tuple[str, ...]:
    """Bound decompression first, then reuse the dashboard's schema validation."""
    if not content or len(content) > MAX_DOWNLOAD_BYTES:
        raise PublicWorkbookError("The GitHub workbook is empty or exceeds the download size limit.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > MAX_ZIP_ENTRIES or len(names) != len(set(names)):
                raise PublicWorkbookError("The GitHub workbook has an unsafe package structure.")
            expanded = 0
            parts: dict[str, ET.Element] = {}
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (path.is_absolute() or "\\" in entry.filename
                        or any(part in {".", ".."} for part in entry.filename.split("/"))
                        or ":" in entry.filename or entry.flag_bits & 1
                        or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}):
                    raise PublicWorkbookError("The GitHub workbook has an unsafe package entry.")
                expanded += entry.file_size
                if (entry.file_size > MAX_PART_BYTES or expanded > MAX_EXPANDED_BYTES
                        or entry.file_size > max(1, entry.compress_size) * MAX_COMPRESSION_RATIO):
                    raise PublicWorkbookError("The GitHub workbook exceeds safe expansion limits.")
                # Reading every part also verifies CRCs, without extracting anything.
                data = archive.read(entry)
                if entry.filename.endswith((".xml", ".rels")):
                    root = _safe_xml(data)
                    if entry.filename.startswith("xl/worksheets/"):
                        _worksheet_bounds(root)
                    if entry.filename in {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}:
                        parts[entry.filename] = root
            if not {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}.issubset(names):
                raise PublicWorkbookError("The GitHub file is not an Excel workbook.")
            sheets = parts["xl/workbook.xml"].findall(f".//{{{_MAIN_NS}}}sheet")
            sheet_names = [sheet.get("name") for sheet in sheets]
            if len(sheet_names) != len(set(sheet_names)) or not {"Leagues", "Calendar"}.issubset(sheet_names):
                raise PublicWorkbookError("The GitHub workbook must contain Leagues and Calendar sheets.")
            relationships = {
                item.get("Id"): item for item in
                parts["xl/_rels/workbook.xml.rels"].findall(f"{{{_REL_NS}}}Relationship")
            }
            for sheet in sheets:
                relationship = relationships.get(sheet.get(f"{{{_OFFICE_REL_NS}}}id"))
                if relationship is None or relationship.get("TargetMode") == "External":
                    raise PublicWorkbookError("The GitHub workbook has invalid worksheet relationships.")
                target = relationship.get("Target", "")
                target = target.lstrip("/") if target.startswith("/") else "xl/" + target
                if target not in names or ".." in PurePosixPath(target).parts:
                    raise PublicWorkbookError("The GitHub workbook refers to a missing worksheet.")
    except (BadZipFile, KeyError, RuntimeError, OSError, zlib.error) as exc:
        raise PublicWorkbookError("The GitHub file is not a readable Excel workbook.") from exc

    # This module intentionally never imports the Admin/write implementation.
    import dashboard_core as core

    try:
        warnings = core.validate_workbook(BytesIO(content))
        core.load_calendar_data(BytesIO(content))
    except (core.WorkbookValidationError, ValueError, TypeError, OverflowError) as exc:
        raise PublicWorkbookError("The GitHub workbook failed dashboard data validation.") from exc
    return tuple(warnings)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_etag(value: object) -> str | None:
    if isinstance(value, str) and len(value) <= 256 and all(32 <= ord(char) <= 126 for char in value):
        return value or None
    return None


def _download(config: GitHubWorkbookConfig, etag: str | None) -> tuple[bytes | None, str | None]:
    headers = {"Accept": "application/octet-stream", "Accept-Encoding": "identity",
               "Cache-Control": "no-cache", "User-Agent": "F1PuskasLeague-workbook/1"}
    etag = _safe_etag(etag)
    if etag:
        headers["If-None-Match"] = etag
    # A minute-bucket avoids GitHub's raw CDN retaining a superseded branch file
    # for its normal five-minute TTL. The trusted host/path remain fixed.
    url = config.source_url + "?f1_refresh=" + str(int(time.time() // REFRESH_SECONDS))
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(ProxyHandler({}), _NoRedirects())
    started = time.monotonic()
    try:
        with opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise PublicWorkbookError(f"GitHub returned HTTP {response.status}.")
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise PublicWorkbookError("GitHub returned an unsupported content encoding.")
            length = response.headers.get("Content-Length")
            if length and (not length.isdigit() or int(length) > MAX_DOWNLOAD_BYTES):
                raise PublicWorkbookError("The GitHub workbook exceeds the download size limit.")
            chunks, size = [], 0
            while True:
                if time.monotonic() - started > DOWNLOAD_DEADLINE_SECONDS:
                    raise PublicWorkbookError("The GitHub workbook download timed out.")
                chunk = response.read(min(65536, MAX_DOWNLOAD_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise PublicWorkbookError("The GitHub workbook exceeds the download size limit.")
                chunks.append(chunk)
            return b"".join(chunks), _safe_etag(response.headers.get("ETag"))
    except HTTPError as exc:
        exc.close()
        if exc.code == 304 and etag:
            return None, etag
        raise PublicWorkbookError(f"GitHub returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PublicWorkbookError("GitHub could not be reached to refresh the workbook.") from exc


@contextmanager
def _cache_lock(directory: Path) -> Iterator[None]:
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(str(directory), threading.Lock())
    if not lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise PublicWorkbookError("Another request is refreshing the GitHub workbook.")
    handle = None
    acquired = False
    try:
        handle = (directory / "refresh.lock").open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise PublicWorkbookError("Another process is refreshing the GitHub workbook.") from exc
                time.sleep(0.025)
        yield
    finally:
        if handle is not None:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        lock.release()


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _metadata(directory: Path) -> dict:
    try:
        path = directory / "current.json"
        if path.stat().st_size > 16384:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=8)
def _cached_validation(path: str, modified_ns: int, size: int, fingerprint: str) -> tuple[str, ...]:
    if size > MAX_DOWNLOAD_BYTES:
        raise PublicWorkbookError("The cached GitHub workbook exceeds the size limit.")
    content = Path(path).read_bytes()
    if hashlib.sha256(content).hexdigest() != fingerprint:
        raise PublicWorkbookError("The cached GitHub workbook failed its integrity check.")
    return validate_snapshot(content)


def _snapshot(directory: Path, metadata: dict, config: GitHubWorkbookConfig) -> WorkbookSource | None:
    fingerprint = metadata.get("fingerprint", "")
    if not isinstance(fingerprint, str) or not _HASH.fullmatch(fingerprint):
        return None
    try:
        path = directory / (fingerprint + ".xlsx")
        stat = path.stat()
        warnings = _cached_validation(str(path), stat.st_mtime_ns, stat.st_size, fingerprint)
        checked = float(metadata["checked_at"])
        success = float(metadata["last_success_at"])
        if not 0 < success <= checked <= time.time() + 60:
            return None
        warning = metadata.get("warning")
        if warning is not None and not isinstance(warning, str):
            return None
        return WorkbookSource(path, fingerprint, "github", "stale" if warning else "current",
                              config.source_url, checked, success, warning, warnings)
    except (OSError, PublicWorkbookError, ValueError, TypeError, KeyError):
        return None


def resolve_workbook(
    local_path: str | Path, *, environ: Mapping[str, str] | None = None,
    cache_dir: str | Path | None = None, force_refresh: bool = False,
) -> WorkbookSource:
    """Select current data without touching the local/manual workbook.

    Call this on dashboard loads (or a 60-second Streamlit fragment). Use
    ``fingerprint`` as the pandas/Streamlit data-cache key, and visibly render
    ``warning`` whenever present. A failed first fetch uses the bundled file
    with ``bundled_fallback`` status; no silent fallback is represented as live.
    ``force_refresh`` is for explicit post-publication refreshes, not polling.
    """
    local = Path(local_path)
    try:
        config = configuration(environ)
    except PublicWorkbookError as exc:
        return WorkbookSource(local, _fingerprint(local), "bundled", "configuration_error", warning=str(exc))
    if config is None:
        return WorkbookSource(local, _fingerprint(local), "local", "local")

    directory = Path(cache_dir) if cache_dir is not None else Path(tempfile.gettempdir()) / "f1-public-workbook-v1"
    directory = directory / config.cache_key
    snapshot = None
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _cache_lock(directory):
            meta = _metadata(directory)
            snapshot = _snapshot(directory, meta, config)
            now = time.time()
            checked_at = meta.get("checked_at", 0)
            recent = isinstance(checked_at, (int, float)) and 0 <= now - checked_at < REFRESH_SECONDS
            if not force_refresh and recent:
                if snapshot:
                    return snapshot
                if meta.get("warning") and not meta.get("fingerprint"):
                    raise PublicWorkbookError(str(meta["warning"]))
            try:
                content, etag = _download(config, meta.get("etag") if snapshot else None)
                warnings = snapshot.validation_warnings if snapshot else ()
                if content is None:
                    if snapshot is None:
                        raise PublicWorkbookError("GitHub did not provide an initial workbook snapshot.")
                    fingerprint, path = snapshot.fingerprint, snapshot.path
                else:
                    warnings = validate_snapshot(content)
                    fingerprint = hashlib.sha256(content).hexdigest()
                    path = directory / (fingerprint + ".xlsx")
                    if not path.exists() or _fingerprint(path) != fingerprint:
                        _atomic_write(path, content)
                now = time.time()
                new_meta = {"fingerprint": fingerprint, "etag": etag,
                            "checked_at": now, "last_success_at": now}
                _atomic_write(directory / "current.json", json.dumps(new_meta).encode("utf-8"))
                return WorkbookSource(path, fingerprint, "github", "current", config.source_url,
                                      now, now, validation_warnings=warnings)
            except (PublicWorkbookError, OSError) as exc:
                warning = str(exc) if isinstance(exc, PublicWorkbookError) else "The GitHub workbook cache could not be updated."
                failure = {**meta, "checked_at": time.time(), "warning": warning}
                if snapshot is None:
                    failure.pop("fingerprint", None)
                    failure.pop("etag", None)
                try:
                    _atomic_write(directory / "current.json", json.dumps(failure).encode("utf-8"))
                except OSError:
                    pass
                raise PublicWorkbookError(warning) from exc
    except (PublicWorkbookError, OSError) as exc:
        snapshot = snapshot or _snapshot(directory, _metadata(directory), config)
        warning = str(exc) if isinstance(exc, PublicWorkbookError) else "The GitHub workbook cache is unavailable."
        if snapshot:
            return WorkbookSource(snapshot.path, snapshot.fingerprint, "github", "stale", config.source_url,
                                  time.time(), snapshot.last_success_at, warning, snapshot.validation_warnings)
        return WorkbookSource(local, _fingerprint(local), "bundled", "bundled_fallback", config.source_url,
                              checked_at=time.time(), warning=warning)
