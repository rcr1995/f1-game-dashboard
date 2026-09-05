"""Security and interruption-recovery regressions for Admin result reviews."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch

import pytest

import admin_auth
import review_draft_recovery as recovery


NOW = 2_000_000_000
CONTEXT = "1" * 64
RECOVERY_CONTEXT = "2" * 64
WORKBOOK = "3" * 64
SOURCE_VERSION = "4" * 40
SCREENSHOT_HASH = "5" * 64


def binding(*, identity: str = "a" * 64, key_byte: int = 7) -> admin_auth.AdminRecoveryBinding:
    return admin_auth.AdminRecoveryBinding(
        identity=identity,
        key_material=bytes([key_byte]) * 32,
    )


def draft() -> dict[str, object]:
    return {
        "context_digest": CONTEXT,
        "recovery_context_digest": RECOVERY_CONTEXT,
        "workbook_sha256": WORKBOOK,
        "source_version": SOURCE_VERSION,
        "event_type": "R",
        "rows": [
            {
                "Position": 1,
                "Driver": "Original OCR suggestion",
                "Time": "82:50.787",
                "Fastest Lap": "1:35.122",
                "OCR text": "RAW-OCR-MUST-NOT-PERSIST",
                "Seen in": "private-photo-name.jpg",
            }
        ],
        # The live editor values must take precedence over the original OCR
        # draft when an interrupted review is checkpointed.
        "edited_rows": [
            {
                "Position": 1,
                "Driver": "Reviewed Driver",
                "Time": "82:50.789",
                "Fastest Lap": "1:34.999",
                "OCR notes": "PRIVATE-OCR-NOTE",
            }
        ],
        "screenshot_hashes": [SCREENSHOT_HASH],
        "token_count": 321,
        "draft_id": "abcdef123456",
        "approved": True,
        "raw_screenshot": b"PRIVATE-SCREENSHOT-BYTES",
    }


def restore(token: str, current_binding: admin_auth.AdminRecoveryBinding, **changes: object):
    arguments: dict[str, object] = {
        "expected_context_digest": RECOVERY_CONTEXT,
        "expected_workbook_sha256": WORKBOOK,
        "expected_source_version": SOURCE_VERSION,
        "now": NOW + 60,
    }
    arguments.update(changes)
    return recovery.restore_recovery_draft(token, current_binding, **arguments)


def test_round_trip_restores_latest_edits_with_a_strict_data_allowlist():
    current_binding = binding()
    token = recovery.seal_recovery_draft(draft(), current_binding, now=NOW)

    restored = restore(token, current_binding)

    assert restored is not None
    assert restored["rows"] == [
        {
            "Position": 1,
            "Driver": "Reviewed Driver",
            "Time": "82:50.789",
            "Fastest Lap": "1:34.999",
        }
    ]
    assert restored["screenshot_hashes"] == [SCREENSHOT_HASH]
    assert set(restored) == {
        "context_digest",
        "recovery_context_digest",
        "workbook_sha256",
        "source_version",
        "event_type",
        "rows",
        "screenshot_hashes",
        "token_count",
        "draft_id",
    }

    persisted = f"{token!r} {restored!r}"
    for prohibited in (
        "PRIVATE-SCREENSHOT-BYTES",
        "private-photo-name.jpg",
        "RAW-OCR-MUST-NOT-PERSIST",
        "PRIVATE-OCR-NOTE",
        "approved",
    ):
        assert prohibited not in persisted


@pytest.mark.parametrize(
    ("candidate_binding", "overrides"),
    [
        (binding(identity="b" * 64), {}),
        (binding(key_byte=8), {}),
        (binding(), {"expected_context_digest": "6" * 64}),
        (binding(), {"expected_workbook_sha256": "7" * 64}),
        (binding(), {"expected_source_version": "8" * 40}),
    ],
)
def test_restore_rejects_another_identity_context_workbook_or_source(
    candidate_binding: admin_auth.AdminRecoveryBinding,
    overrides: dict[str, object],
):
    token = recovery.seal_recovery_draft(draft(), binding(), now=NOW)

    assert restore(token, candidate_binding, **overrides) is None


def test_restore_rejects_tampering_expiry_and_oversized_browser_values():
    current_binding = binding()
    token = recovery.seal_recovery_draft(draft(), current_binding, now=NOW)
    replacement = "A" if token[-1] != "A" else "B"

    assert restore(token[:-1] + replacement, current_binding) is None
    assert restore(
        token,
        current_binding,
        now=NOW + recovery.RECOVERY_TTL_SECONDS + 1,
    ) is None
    assert restore("x" * (recovery.MAX_TOKEN_LENGTH + 1), current_binding) is None


def test_unauthorized_runtime_cannot_mount_restore_or_persist_component():
    with (
        patch("review_draft_recovery.admin_auth.current_admin_recovery_binding", return_value=None),
        patch("review_draft_recovery._render_component") as render_component,
    ):
        assert recovery.restore_browser_draft(
            expected_context_digest=RECOVERY_CONTEXT,
            expected_workbook_sha256=WORKBOOK,
            expected_source_version=SOURCE_VERSION,
        ) is None
        assert recovery.persist_browser_draft(draft()) == "unavailable"

    render_component.assert_not_called()


def test_browser_control_result_rejects_non_ascii_operation_without_crashing():
    malformed = {
        "result": {
            "operation_id": "é" * 32,
            "status": "loaded",
            "token": "opaque",
        }
    }

    assert recovery._component_result(malformed, "a" * 32) is None
    for malformed_status in ([], {}, 1, True, None):
        malformed["result"]["operation_id"] = "a" * 32
        malformed["result"]["status"] = malformed_status
        assert recovery._component_result(malformed, "a" * 32) is None


def test_clear_request_is_one_shot_and_logout_has_priority():
    state: dict[object, object] = {"public_language": "en"}
    recovery.request_browser_clear(state, "refresh")
    first = dict(state[recovery.CLEAR_PENDING_KEY])

    recovery.request_browser_clear(state, "refresh")
    assert state[recovery.CLEAR_PENDING_KEY] == first
    assert recovery.pending_clear_reason(state) == "refresh"

    recovery.request_browser_clear(state, "logout")
    assert recovery.pending_clear_reason(state) == "logout"
    assert state[recovery.CLEAR_PENDING_KEY] != first
    assert state["public_language"] == "en"

    with pytest.raises(ValueError, match="invalid browser recovery clear reason"):
        recovery.request_browser_clear(state, "unknown")


def test_browser_clear_requires_ack_then_cleanup_preserves_unowned_state():
    state: dict[object, object] = {
        "public_language": "en",
        recovery.CACHE_KEY: {"token": "opaque"},
        recovery.COMPONENT_KEY: {"result": "old"},
    }
    recovery.request_browser_clear(state, "published")

    with patch("review_draft_recovery._render_component", return_value=None):
        assert recovery.render_pending_clear(state) is False
    with patch(
        "review_draft_recovery._render_component",
        return_value=("cleared", None),
    ):
        assert recovery.render_pending_clear(state) is True

    recovery.finish_pending_clear(state)
    assert state == {"public_language": "en"}


def test_logout_clear_ack_then_server_logout_removes_all_admin_review_state():
    class FakeStreamlit:
        def __init__(self, state: dict[object, object]):
            self.session_state = state
            self.secrets = {"admin_auth": {"mode": "oidc"}}
            self.logout_calls = 0

        def logout(self) -> None:
            # Browser cleanup must already be acknowledged before native OIDC
            # logout makes the protected page unavailable.
            assert recovery.pending_clear_reason(self.session_state) is None
            assert recovery.CACHE_KEY not in self.session_state
            assert recovery.COMPONENT_KEY not in self.session_state
            self.logout_calls += 1

    state: dict[object, object] = {
        "public_language": "en",
        "race_import_draft": {"edited_rows": [{"Driver": "Reviewed Driver"}]},
        recovery.CACHE_KEY: {"token": "opaque-browser-token"},
        recovery.COMPONENT_KEY: {"result": "old"},
    }
    recovery.request_browser_clear(state, "logout")
    with patch(
        "review_draft_recovery._render_component",
        return_value=("cleared", None),
    ):
        assert recovery.render_pending_clear(state) is True
    recovery.finish_pending_clear(state)

    fake = FakeStreamlit(state)
    with patch("admin_auth._streamlit", return_value=fake):
        admin_auth.logout()

    assert fake.logout_calls == 1
    assert state == {"public_language": "en"}


def test_storage_component_uses_one_fixed_key_and_never_persists_plaintext_fields():
    script = recovery._COMPONENT_JS

    assert recovery.STORAGE_KEY in script
    assert "window.localStorage.setItem(storageKey, token)" in script
    assert "window.localStorage.removeItem(storageKey)" in script
    assert "Driver" not in script
    assert "OCR" not in script
    assert "screenshot" not in script.casefold()
    assert "let lastOperation = null" in script
    assert "if (operation === lastOperation) return" in script


def test_component_operations_are_stable_per_session_and_fresh_after_restart():
    first = "1" * 32
    second = "2" * 32
    material = "a" * 64

    first_operation = recovery._session_operation_id("save", first, material)

    assert first_operation == recovery._session_operation_id("save", first, material)
    assert first_operation != recovery._session_operation_id("save", second, material)
    assert first_operation != recovery._session_operation_id("load", first, material)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_storage_component_executes_save_load_clear_and_fail_closed_paths():
    component_source = recovery._COMPONENT_JS.replace(
        "export default function",
        "const component = function",
        1,
    )
    harness = r"""
class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

const results = [];
const invoke = (data) => {
  let result = null;
  component({
    data,
    setStateValue: (name, value) => {
      if (name !== "result") throw new Error("unexpected state name");
      result = value;
    },
  });
  if (result === null) throw new Error("component did not reply");
  results.push(result);
  return result;
};

globalThis.window = { localStorage: new MemoryStorage() };
const saveOperation = "a".repeat(32);
const loadOperation = "b".repeat(32);
const clearOperation = "c".repeat(32);
const unavailableOperation = "d".repeat(32);
let result = invoke({ action: "save", operation_id: saveOperation, token: "opaque-token" });
if (result.status !== "saved") throw new Error("save failed");
if (window.localStorage.getItem("f1puskasleague.admin-review.v1") !== "opaque-token") {
  throw new Error("wrong persisted value");
}
const repliesAfterSave = results.length;
component({
  data: { action: "save", operation_id: saveOperation, token: "must-not-overwrite" },
  setStateValue: () => { throw new Error("duplicate operation replied"); },
});
if (results.length !== repliesAfterSave || window.localStorage.getItem("f1puskasleague.admin-review.v1") !== "opaque-token") {
  throw new Error("duplicate operation was not idempotent");
}
result = invoke({ action: "load", operation_id: loadOperation, token: "" });
if (result.status !== "loaded" || result.token !== "opaque-token") {
  throw new Error("load failed");
}
result = invoke({ action: "clear", operation_id: clearOperation, token: "" });
if (result.status !== "cleared" || window.localStorage.getItem("f1puskasleague.admin-review.v1") !== null) {
  throw new Error("clear failed");
}
result = invoke({ action: "save", operation_id: "bad", token: "opaque-token" });
if (result.status !== "invalid") throw new Error("invalid operation was accepted");

globalThis.window = {
  localStorage: {
    getItem() { throw new Error("storage disabled"); },
    setItem() { throw new Error("storage disabled"); },
    removeItem() { throw new Error("storage disabled"); },
  },
};
result = invoke({ action: "load", operation_id: unavailableOperation, token: "" });
if (result.status !== "unavailable") throw new Error("storage failure did not fail closed");
"""

    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", component_source + harness],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
