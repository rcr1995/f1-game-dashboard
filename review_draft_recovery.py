"""Encrypted browser-local recovery for an authenticated result review.

Vercel can replace the Streamlit process or websocket at any time, so
``st.session_state`` alone is not a durable place for an in-progress review.
This module stores one short-lived, opaque Fernet token in the Admin's browser.
Only normalized review fields and screenshot SHA-256 digests are sealed; image
bytes, filenames, OCR text, credentials, and publication approval are excluded.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Mapping, MutableMapping, Sequence
from hashlib import sha256
import hmac
import json
import math
from numbers import Real
import re
import secrets
import time
from typing import Any
import unicodedata

from cryptography.fernet import Fernet, InvalidToken

import admin_auth


RECOVERY_TTL_SECONDS = 7 * 24 * 60 * 60
STORAGE_KEY = "f1puskasleague.admin-review.v1"
COMPONENT_KEY = "race_import_review_recovery_component_v1"
CACHE_KEY = "race_import_review_recovery_sealed_v1"
SESSION_NONCE_KEY = "race_import_review_recovery_session_nonce_v1"
# This one-shot handshake must survive an authorization transition between an
# active Admin's logout click and the browser's clear acknowledgement.
CLEAR_PENDING_KEY = "review_recovery_clear_pending"
MAX_TOKEN_LENGTH = 131_072
MAX_REVIEW_ROWS = 64

_VERSION = 1
_HEX_64_RE = re.compile(r"[0-9a-f]{64}")
_DRAFT_ID_RE = re.compile(r"[0-9a-f]{12}")
_SOURCE_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}")
_OPERATION_RE = re.compile(r"[0-9a-f]{32}")
_ROW_FIELDS = ("Position", "Driver", "Time", "Fastest Lap")
_ENVELOPE_FIELDS = {
    "version",
    "identity",
    "context_digest",
    "recovery_context_digest",
    "workbook_sha256",
    "source_version",
    "event_type",
    "rows",
    "screenshot_hashes",
    "token_count",
    "draft_id",
    "saved_at",
}

_COMPONENT_JS = r"""
const storageKey = "f1puskasleague.admin-review.v1";
const maxTokenLength = 131072;
let lastOperation = null;

export default function ({ data, setStateValue }) {
  const operation = data?.operation_id;
  const action = data?.action;
  const reply = (status, token = null) => {
    lastOperation = operation;
    setStateValue("result", { operation_id: operation, status, token });
  };

  if (typeof operation !== "string" || !/^[0-9a-f]{32}$/.test(operation)) {
    reply("invalid");
    return;
  }
  // Streamlit reruns render the component repeatedly. One operation must emit
  // at most one acknowledgement or it can create a permanent rerun loop.
  if (operation === lastOperation) return;
  try {
    if (action === "load") {
      const token = window.localStorage.getItem(storageKey);
      if (token !== null && (typeof token !== "string" || token.length > maxTokenLength)) {
        window.localStorage.removeItem(storageKey);
        reply("invalid");
      } else {
        reply("loaded", token);
      }
      return;
    }
    if (action === "save") {
      const token = data?.token;
      if (typeof token !== "string" || token.length === 0 || token.length > maxTokenLength) {
        reply("invalid");
        return;
      }
      window.localStorage.setItem(storageKey, token);
      reply(window.localStorage.getItem(storageKey) === token ? "saved" : "unavailable");
      return;
    }
    if (action === "clear") {
      window.localStorage.removeItem(storageKey);
      reply("cleared");
      return;
    }
    reply("invalid");
  } catch (_) {
    // If browser storage is disabled, no persisted record is readable either.
    reply("unavailable");
  }
}
"""


class RecoveryDraftError(ValueError):
    """Raised when a recovery draft cannot be safely sealed or restored."""


def _same(candidate: object, expected: str) -> bool:
    if (
        not isinstance(candidate, str)
        or not isinstance(expected, str)
        or len(candidate) != len(expected)
    ):
        return False
    try:
        candidate.encode("ascii")
        expected.encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(candidate, expected)


def _safe_string(value: object, *, maximum: int) -> str:
    if value is None:
        return ""
    if isinstance(value, Real) and not isinstance(value, bool) and math.isnan(float(value)):
        return ""
    if not isinstance(value, str):
        raise RecoveryDraftError("review text has an invalid type")
    value = unicodedata.normalize("NFC", value).strip()
    if len(value) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise RecoveryDraftError("review text is invalid")
    return value


def _safe_position(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RecoveryDraftError("review position has an invalid type")
    numeric = float(value)
    if math.isnan(numeric):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise RecoveryDraftError("review position is invalid")
    position = int(numeric)
    if not 1 <= position <= MAX_REVIEW_ROWS:
        raise RecoveryDraftError("review position is out of range")
    return position


def sanitize_review_rows(rows: object) -> list[dict[str, object]]:
    """Return the only four editable fields allowed in browser recovery."""

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise RecoveryDraftError("review rows are invalid")
    if len(rows) > MAX_REVIEW_ROWS:
        raise RecoveryDraftError("too many review rows")
    clean: list[dict[str, object]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise RecoveryDraftError("review row is invalid")
        clean.append(
            {
                "Position": _safe_position(raw.get("Position")),
                "Driver": _safe_string(raw.get("Driver"), maximum=200),
                "Time": _safe_string(raw.get("Time"), maximum=64),
                "Fastest Lap": _safe_string(raw.get("Fastest Lap"), maximum=64),
            }
        )
    return clean


def _normalized_draft(draft: Mapping[str, object]) -> dict[str, object]:
    context_digest = draft.get("context_digest")
    recovery_context_digest = draft.get("recovery_context_digest")
    workbook_sha256 = draft.get("workbook_sha256")
    source_version = draft.get("source_version")
    event_type = draft.get("event_type")
    draft_id = draft.get("draft_id")
    screenshot_hashes = draft.get("screenshot_hashes", [])
    token_count = draft.get("token_count", 0)
    if not isinstance(context_digest, str) or _HEX_64_RE.fullmatch(context_digest) is None:
        raise RecoveryDraftError("review context is invalid")
    if (
        not isinstance(recovery_context_digest, str)
        or _HEX_64_RE.fullmatch(recovery_context_digest) is None
    ):
        raise RecoveryDraftError("review recovery context is invalid")
    if not isinstance(workbook_sha256, str) or _HEX_64_RE.fullmatch(workbook_sha256) is None:
        raise RecoveryDraftError("workbook fingerprint is invalid")
    if not isinstance(source_version, str) or _SOURCE_RE.fullmatch(source_version) is None:
        raise RecoveryDraftError("source version is invalid")
    if event_type not in {"R", "SR"}:
        raise RecoveryDraftError("event type is invalid")
    if not isinstance(draft_id, str) or _DRAFT_ID_RE.fullmatch(draft_id) is None:
        raise RecoveryDraftError("draft id is invalid")
    if (
        not isinstance(screenshot_hashes, Sequence)
        or isinstance(screenshot_hashes, (str, bytes, bytearray))
        or len(screenshot_hashes) > 4
        or any(not isinstance(item, str) or _HEX_64_RE.fullmatch(item) is None for item in screenshot_hashes)
    ):
        raise RecoveryDraftError("screenshot fingerprints are invalid")
    if isinstance(token_count, bool) or not isinstance(token_count, int) or not 0 <= token_count <= 1_000_000:
        raise RecoveryDraftError("OCR token count is invalid")

    return {
        "context_digest": context_digest,
        "recovery_context_digest": recovery_context_digest,
        "workbook_sha256": workbook_sha256,
        "source_version": source_version,
        "event_type": event_type,
        "rows": sanitize_review_rows(draft.get("edited_rows", draft.get("rows"))),
        "screenshot_hashes": list(screenshot_hashes),
        "token_count": token_count,
        "draft_id": draft_id,
    }


def _fernet(binding: admin_auth.AdminRecoveryBinding) -> Fernet:
    if (
        not isinstance(binding, admin_auth.AdminRecoveryBinding)
        or not isinstance(binding.identity, str)
        or _HEX_64_RE.fullmatch(binding.identity) is None
        or not isinstance(binding.key_material, bytes)
        or len(binding.key_material) != 32
    ):
        raise RecoveryDraftError("admin recovery binding is invalid")
    return Fernet(urlsafe_b64encode(binding.key_material))


def seal_recovery_draft(
    draft: Mapping[str, object],
    binding: admin_auth.AdminRecoveryBinding,
    *,
    now: int | None = None,
) -> str:
    """Encrypt and authenticate a strict, identity-bound draft envelope."""

    normalized = _normalized_draft(draft)
    saved_at = int(time.time()) if now is None else int(now)
    envelope = {
        "version": _VERSION,
        "identity": binding.identity,
        **normalized,
        "saved_at": saved_at,
    }
    payload = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > 65_536:
        raise RecoveryDraftError("review draft is too large")
    token = _fernet(binding).encrypt_at_time(payload, current_time=saved_at).decode("ascii")
    if len(token) > MAX_TOKEN_LENGTH:
        raise RecoveryDraftError("review recovery token is too large")
    return token


def restore_recovery_draft(
    token: object,
    binding: admin_auth.AdminRecoveryBinding,
    *,
    expected_context_digest: str,
    expected_workbook_sha256: str,
    expected_source_version: str,
    now: int | None = None,
) -> dict[str, object] | None:
    """Restore only a fresh token for this identity and exact source context."""

    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    current_time = int(time.time()) if now is None else int(now)
    try:
        payload = _fernet(binding).decrypt_at_time(
            token.encode("ascii"),
            ttl=RECOVERY_TTL_SECONDS,
            current_time=current_time,
        )
        envelope = json.loads(payload.decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, Mapping) or set(envelope) != _ENVELOPE_FIELDS:
        return None
    saved_at = envelope.get("saved_at")
    if (
        envelope.get("version") != _VERSION
        or isinstance(saved_at, bool)
        or not isinstance(saved_at, int)
        or saved_at > current_time + 60
        or not _same(envelope.get("identity"), binding.identity)
        or not _same(envelope.get("recovery_context_digest"), expected_context_digest)
        or not _same(envelope.get("workbook_sha256"), expected_workbook_sha256)
        or not _same(envelope.get("source_version"), expected_source_version)
    ):
        return None
    try:
        restored = _normalized_draft(envelope)
    except RecoveryDraftError:
        return None
    # A recovered draft starts from its compact reviewed values; it never
    # recreates the source OCR text or any uploaded image representation.
    return restored


def _draft_digest(draft: Mapping[str, object]) -> str:
    normalized = _normalized_draft(draft)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _streamlit() -> Any:
    import streamlit as st

    return st


def _component_renderer(st: Any):
    return st.components.v2.component(
        "f1_admin_review_recovery",
        js=_COMPONENT_JS,
    )


def _session_nonce(state: MutableMapping[object, object]) -> str:
    nonce = state.get(SESSION_NONCE_KEY)
    if not isinstance(nonce, str) or _OPERATION_RE.fullmatch(nonce) is None:
        nonce = secrets.token_hex(16)
        state[SESSION_NONCE_KEY] = nonce
    return nonce


def _session_operation_id(action: str, session_nonce: str, material: str) -> str:
    if action not in {"load", "save"} or _OPERATION_RE.fullmatch(session_nonce) is None:
        raise ValueError("invalid recovery operation")
    return sha256(f"{action}\0{session_nonce}\0{material}".encode("ascii")).hexdigest()[:32]


def _component_result(value: object, operation_id: str) -> tuple[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    result = value.get("result")
    if not isinstance(result, Mapping) or not _same(result.get("operation_id"), operation_id):
        return None
    status = result.get("status")
    if not isinstance(status, str) or status not in {
        "loaded",
        "saved",
        "cleared",
        "unavailable",
        "invalid",
    }:
        return None
    return str(status), result.get("token")


def _render_component(*, action: str, operation_id: str, token: str = "") -> tuple[str, object] | None:
    st = _streamlit()
    renderer = _component_renderer(st)
    result = renderer(
        key=COMPONENT_KEY,
        data={"action": action, "operation_id": operation_id, "token": token},
        on_result_change=lambda: None,
        height=0,
        width="stretch",
    )
    current = result if result is not None else st.session_state.get(COMPONENT_KEY)
    return _component_result(current, operation_id)


def restore_browser_draft(
    *,
    expected_context_digest: str,
    expected_workbook_sha256: str,
    expected_source_version: str,
) -> dict[str, object] | None:
    """Read and validate one browser token after the Admin gate has passed."""

    binding = admin_auth.current_admin_recovery_binding()
    if binding is None:
        return None
    st = _streamlit()
    operation_id = _session_operation_id(
        "load",
        _session_nonce(st.session_state),
        f"{binding.identity}\0{expected_context_digest}",
    )
    response = _render_component(action="load", operation_id=operation_id)
    if response is None or response[0] != "loaded" or response[1] is None:
        return None
    restored = restore_recovery_draft(
        response[1],
        binding,
        expected_context_digest=expected_context_digest,
        expected_workbook_sha256=expected_workbook_sha256,
        expected_source_version=expected_source_version,
    )
    if restored is not None:
        st.session_state[CACHE_KEY] = {
            "digest": _draft_digest(restored),
            "token": response[1],
        }
    return restored


def persist_browser_draft(draft: Mapping[str, object]) -> str:
    """Seal the current edited rows and return saved/pending/unavailable."""

    binding = admin_auth.current_admin_recovery_binding()
    if binding is None:
        return "unavailable"
    st = _streamlit()
    try:
        digest = _draft_digest(draft)
    except RecoveryDraftError:
        return "unavailable"
    cached = st.session_state.get(CACHE_KEY)
    if isinstance(cached, Mapping) and cached.get("digest") == digest and isinstance(cached.get("token"), str):
        token = str(cached["token"])
    else:
        try:
            token = seal_recovery_draft(draft, binding)
        except RecoveryDraftError:
            return "unavailable"
        st.session_state[CACHE_KEY] = {"digest": digest, "token": token}
    operation_id = _session_operation_id(
        "save",
        _session_nonce(st.session_state),
        sha256(token.encode("ascii")).hexdigest(),
    )
    response = _render_component(action="save", operation_id=operation_id, token=token)
    if response is None:
        return "pending"
    return "saved" if response[0] == "saved" else "unavailable"


def request_browser_clear(state: MutableMapping[object, object], reason: str) -> None:
    """Start a one-shot browser clear that must be acknowledged before exit."""

    if reason not in {"discard", "logout", "published", "refresh"}:
        raise ValueError("invalid browser recovery clear reason")
    current = state.get(CLEAR_PENDING_KEY)
    if isinstance(current, Mapping) and _OPERATION_RE.fullmatch(str(current.get("operation_id") or "")):
        if reason == "logout" and current.get("reason") != "logout":
            state[CLEAR_PENDING_KEY] = {
                "operation_id": secrets.token_hex(16),
                "reason": reason,
            }
        return
    state[CLEAR_PENDING_KEY] = {
        "operation_id": secrets.token_hex(16),
        "reason": reason,
    }


def pending_clear_reason(state: Mapping[object, object]) -> str | None:
    pending = state.get(CLEAR_PENDING_KEY)
    if not isinstance(pending, Mapping):
        return None
    operation_id = pending.get("operation_id")
    reason = pending.get("reason")
    if not isinstance(operation_id, str) or _OPERATION_RE.fullmatch(operation_id) is None:
        return None
    return str(reason) if reason in {"discard", "logout", "published", "refresh"} else None


def render_pending_clear(state: MutableMapping[object, object]) -> bool:
    """Clear browser storage and return true only after the matching ack."""

    reason = pending_clear_reason(state)
    if reason is None:
        return False
    operation_id = str(state[CLEAR_PENDING_KEY]["operation_id"])  # type: ignore[index]
    response = _render_component(action="clear", operation_id=operation_id)
    # Storage-unavailable means there is no readable browser record to retain.
    return response is not None and response[0] in {"cleared", "unavailable"}


def finish_pending_clear(state: MutableMapping[object, object]) -> None:
    state.pop(CLEAR_PENDING_KEY, None)
    state.pop(CACHE_KEY, None)
    state.pop(COMPONENT_KEY, None)


__all__ = [
    "CACHE_KEY",
    "CLEAR_PENDING_KEY",
    "COMPONENT_KEY",
    "RECOVERY_TTL_SECONDS",
    "SESSION_NONCE_KEY",
    "RecoveryDraftError",
    "finish_pending_clear",
    "pending_clear_reason",
    "persist_browser_draft",
    "render_pending_clear",
    "request_browser_clear",
    "restore_browser_draft",
    "restore_recovery_draft",
    "sanitize_review_rows",
    "seal_recovery_draft",
]
