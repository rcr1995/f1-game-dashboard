"""Circuits display preferences survive visits without trusting browser input."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ui_preferences as preferences


LEAGUE_A = "a" * 24
LEAGUE_B = "b" * 24
OPTIONS = ["all", LEAGUE_A, LEAGUE_B]


class CircuitsPreferenceStateTests(unittest.TestCase):
    def mount(self, state, result=None, options=None):
        calls = []
        fake = SimpleNamespace(
            session_state=state,
            components=SimpleNamespace(v2=SimpleNamespace(component=lambda *args, **kwargs:
                lambda **mounted: calls.append(mounted) or result)),
        )
        with patch.dict("sys.modules", {"streamlit": fake}):
            preferences.mount_circuits_preference(OPTIONS if options is None else options)
        return calls[-1]

    def select(self, state, value):
        state["circuits_league"] = value
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences.select_circuits_from_widget()

    def test_first_mount_is_nonblocking_and_sends_no_default_write(self):
        state = {"identity": "private", "password": "private"}
        call = self.mount(state)
        self.assertEqual(call["data"], {
            "options": OPTIONS, "ready": False, "selection": "all", "write": None,
        })
        self.assertEqual(call["height"], 0)
        self.assertNotIn(preferences.CIRCUITS_READY_KEY, state)
        self.assertEqual(state["circuits_league"], "all")

    def test_saved_value_and_replayed_response_restore_before_selectbox(self):
        state = {}
        self.mount(state, {"preference": LEAGUE_A})
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], LEAGUE_A)
        self.assertEqual(state["circuits_league"], LEAGUE_A)
        self.assertTrue(state[preferences.CIRCUITS_READY_KEY])
        self.assertNotIn(preferences.CIRCUITS_WRITE_KEY, state)
        second = self.mount(state)
        self.assertEqual(second["data"]["selection"], LEAGUE_A)
        self.assertTrue(second["data"]["ready"])
        self.assertIsNone(second["data"]["write"])

    def test_native_selection_wins_over_delayed_and_replayed_hydration(self):
        state = {}
        self.mount(state)
        self.select(state, LEAGUE_B)
        token = state[preferences.CIRCUITS_WRITE_KEY]
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        preferences.hydrate_circuits(state, LEAGUE_A)
        self.mount(state, {"preference": LEAGUE_A})
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], LEAGUE_B)
        self.assertEqual(state["circuits_league"], LEAGUE_B)
        self.assertEqual(state[preferences.CIRCUITS_WRITE_KEY], token)

    def test_widget_cleanup_and_language_reruns_keep_durable_value_and_token(self):
        state = {}
        self.mount(state)
        self.select(state, LEAGUE_B)
        token = state[preferences.CIRCUITS_WRITE_KEY]
        del state["circuits_league"]
        state["app_lang"] = "Português (Portugal)"
        call = self.mount(state)
        self.assertEqual(state["circuits_league"], LEAGUE_B)
        self.assertEqual(call["data"]["write"], token)
        self.assertEqual(call["data"]["selection"], LEAGUE_B)

    def test_all_is_an_explicit_persistable_choice_and_new_click_has_new_token(self):
        state = {}
        self.mount(state, {"preference": LEAGUE_B})
        self.select(state, LEAGUE_A)
        first_token = state[preferences.CIRCUITS_WRITE_KEY]
        self.select(state, "all")
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], "all")
        self.assertNotEqual(state[preferences.CIRCUITS_WRITE_KEY], first_token)
        preferences.hydrate_circuits(state, LEAGUE_B)
        self.assertEqual(state["circuits_league"], "all")

    def test_corrupt_and_deleted_saved_values_fall_back_without_scheduling_write(self):
        for value in ("missing", "", None, 1, True, [], {}, "<script>alert(1)</script>"):
            with self.subTest(value=value):
                state = {preferences.CIRCUITS_OPTIONS_KEY: tuple(OPTIONS)}
                preferences.hydrate_circuits(state, value)
                self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], "all")
                self.assertEqual(state["circuits_league"], "all")
                self.assertTrue(state[preferences.CIRCUITS_READY_KEY])
                self.assertNotIn(preferences.CIRCUITS_WRITE_KEY, state)

    def test_removed_catalog_entry_resets_ui_and_discards_pending_write(self):
        state = {}
        self.mount(state)
        self.select(state, LEAGUE_A)
        call = self.mount(state, options=["all", LEAGUE_B])
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], "all")
        self.assertEqual(state["circuits_league"], "all")
        self.assertIsNone(call["data"]["write"])

    def test_invalid_widget_choice_does_not_create_or_replace_durable_preference(self):
        state = {}
        self.mount(state, {"preference": LEAGUE_A})
        for value in (None, "missing", [], {}, True):
            self.select(state, value)
            self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], LEAGUE_A)
            self.assertNotIn(preferences.CIRCUITS_WRITE_KEY, state)

    def test_component_callback_uses_only_allowlisted_preference_and_ignores_no_ack(self):
        state = {preferences.CIRCUITS_OPTIONS_KEY: tuple(OPTIONS),
                 preferences.CIRCUITS_COMPONENT_KEY: {"preference": LEAGUE_B, "admin": True}}
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences._receive_circuits_preference()
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], LEAGUE_B)
        self.assertNotIn("admin", state)
        state = {preferences.CIRCUITS_COMPONENT_KEY: {"preference": None}}
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences._receive_circuits_preference()
        self.assertNotIn(preferences.CIRCUITS_READY_KEY, state)


@unittest.skipUnless(shutil.which("node"), "Node is required for isolated component JavaScript checks")
class CircuitsPreferenceJavascriptTests(unittest.TestCase):
    def test_browser_read_write_races_failures_and_isolation(self):
        # Execute only our fixed component against fake storage, never a real
        # browser profile. Each new function factory models an independent tab.
        script = r"""
const assert = require('node:assert/strict');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const factory = () => new Function(source.replace('export default function', 'return function'))();
const key = 'f1puskasleague.circuits.league.v1';
const a = 'a'.repeat(24), b = 'b'.repeat(24), options = ['all', a, b];
const browser = initial => {
  let value = initial, blocked = false;
  const writes = [], responses = [];
  return {
    localStorage: {
      getItem(name) { assert.equal(name, key); if (blocked) throw Error('denied'); return value; },
      setItem(name, next) { assert.equal(name, key); if (blocked) throw Error('denied'); writes.push(next); value = next; },
    },
    get value() { return value; },
    set value(next) { value = next; },
    set blocked(next) { blocked = next; },
    writes, responses,
    send(name, next) { assert.equal(name, 'preference'); responses.push(next); },
  };
};
const run = (mount, target, data) => {
  global.window = {localStorage: target.localStorage};
  mount({data: {options, ready: false, selection: 'all', write: null, ...data}, setStateValue: target.send});
};

const profile = browser(a), mount = factory();
run(mount, profile, {});
assert.deepEqual(profile.responses, [a]);
assert.deepEqual(profile.writes, []); // No initial All write can erase saved A.
run(mount, profile, {ready: true, selection: a});
assert.deepEqual(profile.writes, []); // Hydration acknowledgement also never writes.

run(mount, profile, {ready: true, selection: b, write: 'explicit-1'});
assert.equal(profile.value, b);
assert.deepEqual(profile.writes, [b]);
run(mount, profile, {ready: true, selection: b, write: 'explicit-1'});
assert.deepEqual(profile.writes, [b]); // Replayed payload is idempotent.
profile.value = a; // A newer choice was made in another tab.
run(mount, profile, {ready: true, selection: b, write: 'explicit-1'});
assert.equal(profile.value, a); // An unrelated old-tab rerun cannot overwrite it.

run(mount, profile, {ready: true, selection: 'all', write: 'explicit-2'});
assert.equal(profile.value, 'all');
run(mount, profile, {ready: true, selection: b, write: 'explicit-1'});
assert.equal(profile.value, 'all'); // A nonconsecutive stale payload cannot undo the newer choice.
assert.deepEqual(profile.writes, [b, 'all']);
const returningTab = factory();
run(returningTab, profile, {});
assert.equal(profile.responses.at(-1), 'all');

for (const stored of [null, '', 'missing', '<script>', '{}', true]) {
  const bad = browser(stored);
  run(factory(), bad, {});
  assert.deepEqual(bad.responses, ['all']);
  assert.deepEqual(bad.writes, []);
}
const removed = browser(a);
run(factory(), removed, {options: ['all', b]});
assert.deepEqual(removed.responses, ['all']);

const blocked = browser(a), blockedTab = factory();
blocked.blocked = true;
run(blockedTab, blocked, {});
assert.deepEqual(blocked.responses, ['all']);
run(blockedTab, blocked, {ready: true, selection: b, write: 'explicit-denied'});
assert.deepEqual(blocked.writes, []); // Denied persistence never throws through the UI.

const first = browser(a), second = browser(b);
run(factory(), first, {});
run(factory(), second, {});
assert.deepEqual(first.responses, [a]);
assert.deepEqual(second.responses, [b]);
run(factory(), first, {ready: true, selection: 'all', write: 'first-only'});
assert.equal(first.value, 'all');
assert.equal(second.value, b);
console.log('Circuits preference JavaScript checks passed');
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            input=json.dumps(preferences.CIRCUITS_COMPONENT_JS),
            text=True, capture_output=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
