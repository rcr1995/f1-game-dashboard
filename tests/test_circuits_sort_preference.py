"""Sorting is remembered independently from the league and from widget lifetime."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ui_preferences as preferences


OPTIONS = ["name", "country", "races"]


class CircuitsSortPreferenceStateTests(unittest.TestCase):
    def mount(self, state, result=None):
        calls = []
        fake = SimpleNamespace(
            session_state=state,
            components=SimpleNamespace(v2=SimpleNamespace(component=lambda *args, **kwargs:
                lambda **mounted: calls.append(mounted) or result)),
        )
        with patch.dict("sys.modules", {"streamlit": fake}):
            preferences.mount_circuits_sort_preference()
        return calls[-1]

    def select(self, state, value):
        state["circuits_sort"] = value
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences.select_circuits_sort_from_widget()

    def test_first_mount_does_not_write_default_over_saved_browser_sort(self):
        state = {"identity": "private", "password": "private"}
        call = self.mount(state)
        self.assertEqual(call["data"], {
            "kind": "sort", "options": OPTIONS, "ready": False,
            "selection": "name", "write": None,
        })
        self.assertEqual(call["key"], preferences.SORT_COMPONENT_KEY)
        self.assertEqual(call["height"], 0)
        self.assertEqual(state["circuits_sort"], "name")
        self.assertFalse(state.get(preferences.SORT_READY_KEY, False))

    def test_each_saved_code_restores_before_the_native_widget(self):
        for saved in OPTIONS:
            with self.subTest(saved=saved):
                state = {}
                self.mount(state, {"preference": saved})
                self.assertEqual(state["circuits_sort"], saved)
                self.assertEqual(state[preferences.SORT_VALUE_KEY], saved)
                self.assertTrue(state[preferences.SORT_READY_KEY])
                self.assertNotIn(preferences.SORT_WRITE_KEY, state)
                call = self.mount(state)
                self.assertEqual(call["data"]["selection"], saved)
                self.assertTrue(call["data"]["ready"])
                self.assertIsNone(call["data"]["write"])

    def test_new_user_choice_beats_delayed_hydration_and_replayed_response(self):
        state = {}
        self.mount(state)
        self.select(state, "races")
        token = state[preferences.SORT_WRITE_KEY]
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        preferences.hydrate_circuits_sort(state, "country")
        self.mount(state, {"preference": "country"})
        self.assertEqual(state["circuits_sort"], "races")
        self.assertEqual(state[preferences.SORT_VALUE_KEY], "races")
        self.assertEqual(state[preferences.SORT_WRITE_KEY], token)

    def test_alphabetical_sort_is_an_explicit_remembered_choice(self):
        state = {}
        self.mount(state, {"preference": "country"})
        self.select(state, "races")
        previous = state[preferences.SORT_WRITE_KEY]
        self.select(state, "name")
        self.assertEqual(state[preferences.SORT_VALUE_KEY], "name")
        self.assertNotEqual(state[preferences.SORT_WRITE_KEY], previous)
        self.mount(state, {"preference": "country"})
        self.assertEqual(state["circuits_sort"], "name")

    def test_navigation_cleanup_and_language_changes_do_not_reset_sort_or_league(self):
        league = "a" * 24
        state = {preferences.CIRCUITS_VALUE_KEY: league, preferences.CIRCUITS_READY_KEY: True,
                 preferences.CIRCUITS_WRITE_KEY: "league-token", "circuits_league": league}
        self.mount(state, {"preference": "races"})
        self.select(state, "country")
        token = state[preferences.SORT_WRITE_KEY]
        del state["circuits_sort"]  # Streamlit removes widgets on other pages.
        state["app_lang"] = "Português (Portugal)"
        call = self.mount(state)
        self.assertEqual(state["circuits_sort"], "country")
        self.assertEqual(call["data"]["selection"], "country")
        self.assertEqual(call["data"]["write"], token)
        self.assertEqual(state[preferences.CIRCUITS_VALUE_KEY], league)
        self.assertEqual(state["circuits_league"], league)
        self.assertEqual(state[preferences.CIRCUITS_WRITE_KEY], "league-token")

    def test_bad_saved_codes_fall_back_without_writes_or_localized_values(self):
        for saved in (None, "", "all", "Most races", "Mais corridas", "unknown", [], {}, True):
            with self.subTest(saved=saved):
                state = {preferences.SORT_OPTIONS_KEY: tuple(OPTIONS)}
                preferences.hydrate_circuits_sort(state, saved)
                self.assertEqual(state["circuits_sort"], "name")
                self.assertEqual(state[preferences.SORT_VALUE_KEY], "name")
                self.assertNotIn(preferences.SORT_WRITE_KEY, state)

    def test_invalid_widget_or_obsolete_durable_value_cannot_be_persisted(self):
        state = {}
        self.mount(state, {"preference": "country"})
        for value in (None, "unknown", [], {}, True):
            self.select(state, value)
            self.assertEqual(state[preferences.SORT_VALUE_KEY], "country")
            self.assertNotIn(preferences.SORT_WRITE_KEY, state)
        state[preferences.SORT_VALUE_KEY] = "obsolete-option"
        state[preferences.SORT_WRITE_KEY] = "obsolete-token"
        call = self.mount(state)
        self.assertEqual(state["circuits_sort"], "name")
        self.assertIsNone(call["data"]["write"])


@unittest.skipUnless(shutil.which("node"), "Node is required for isolated JavaScript preference checks")
class CircuitsSortPreferenceJavascriptTests(unittest.TestCase):
    def test_saved_sort_initial_read_writes_races_failures_and_league_isolation(self):
        # Use fake Storage objects only; this does not access any browser profile.
        script = r"""
const assert = require('node:assert/strict');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const factory = () => new Function(source.replace('export default function', 'return function'))();
const sortKey = 'f1puskasleague.circuits.sort.v1';
const leagueKey = 'f1puskasleague.circuits.league.v1';
const league = 'a'.repeat(24);
const browser = (savedSort, savedLeague = league) => {
  const values = new Map([[sortKey, savedSort], [leagueKey, savedLeague]]);
  const writes = [], responses = [];
  let blocked = false;
  return {
    values, writes, responses,
    set blocked(value) { blocked = value; },
    localStorage: {
      getItem(key) { assert.ok([sortKey, leagueKey].includes(key)); if (blocked) throw Error('denied'); return values.get(key); },
      setItem(key, value) { assert.ok([sortKey, leagueKey].includes(key)); if (blocked) throw Error('denied'); writes.push([key, value]); values.set(key, value); },
    },
    send(name, value) { assert.equal(name, 'preference'); responses.push(value); },
  };
};
const run = (mount, profile, data = {}) => {
  global.window = {localStorage: profile.localStorage};
  mount({data: {kind: 'sort', options: ['name', 'country', 'races'], ready: false,
               selection: 'name', write: null, ...data}, setStateValue: profile.send});
};
const profile = browser('races'), mount = factory();
run(mount, profile);
assert.deepEqual(profile.responses, ['races']);
assert.deepEqual(profile.writes, []); // No default alphabetical write erases saved Most races.
run(mount, profile, {ready: true, selection: 'races'});
assert.deepEqual(profile.writes, []);
run(mount, profile, {ready: true, selection: 'country', write: 'sort-1'});
assert.equal(profile.values.get(sortKey), 'country');
assert.equal(profile.values.get(leagueKey), league);
assert.deepEqual(profile.writes, [[sortKey, 'country']]);
run(mount, profile, {ready: true, selection: 'country', write: 'sort-1'});
assert.equal(profile.writes.length, 1);
profile.values.set(sortKey, 'races'); // A newer choice in another tab wins over old reruns.
run(mount, profile, {ready: true, selection: 'country', write: 'sort-1'});
assert.equal(profile.values.get(sortKey), 'races');
run(mount, profile, {ready: true, selection: 'name', write: 'sort-2'});
run(mount, profile, {ready: true, selection: 'country', write: 'sort-1'});
assert.equal(profile.values.get(sortKey), 'name'); // Nonconsecutive stale payload also cannot overwrite.
assert.equal(profile.writes.length, 2);
run(factory(), profile);
assert.equal(profile.responses.at(-1), 'name');

// A league update does not write or reset the independent sorting preference.
run(factory(), profile, {kind: undefined, options: ['all', league], selection: 'all', ready: true, write: 'league-1'});
assert.equal(profile.values.get(leagueKey), 'all');
assert.equal(profile.values.get(sortKey), 'name');
for (const value of [null, '', 'Most races', 'Mais corridas', 'unknown', '{}', true]) {
  const corrupt = browser(value);
  run(factory(), corrupt);
  assert.deepEqual(corrupt.responses, ['name']);
  assert.deepEqual(corrupt.writes, []);
  assert.equal(corrupt.values.get(leagueKey), league);
}
const denied = browser('country'), deniedMount = factory();
denied.blocked = true;
run(deniedMount, denied);
assert.deepEqual(denied.responses, ['name']);
run(deniedMount, denied, {ready: true, selection: 'races', write: 'sort-denied'});
assert.deepEqual(denied.writes, []);
const other = browser('country');
run(factory(), other);
assert.deepEqual(other.responses, ['country']);
assert.equal(profile.values.get(sortKey), 'name');
console.log('Sorting preference JavaScript checks passed');
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script], input=json.dumps(preferences.CIRCUITS_COMPONENT_JS),
            text=True, capture_output=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
