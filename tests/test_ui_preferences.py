"""Language persistence must never treat browser values as trusted app state."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import ui_preferences as preferences


ROOT = Path(__file__).resolve().parents[1]


class LanguageStateTests(unittest.TestCase):
    def test_first_visit_preserves_existing_default_without_marking_browser_ready(self):
        state = {}
        self.assertEqual(preferences.language_name(state), "Português (Portugal)")
        self.assertEqual(state, {})

    def test_saved_language_hydrates_both_native_selectors(self):
        for code, name in (("en", "English"), ("pt", "Português (Portugal)")):
            with self.subTest(code=code):
                state = {}
                preferences.hydrate_language(state, code)
                self.assertEqual(state["app_lang"], name)
                self.assertEqual(state["app_lang_selector"], name)
                self.assertEqual(state["admin_language"], name)
                self.assertTrue(state[preferences.READY_KEY])

    def test_unknown_or_malformed_browser_value_falls_back_safely(self):
        for value in (None, "", "es", "<script>", {"admin": True}, ["en"], 1, True):
            with self.subTest(value=value):
                state = {}
                preferences.hydrate_language(state, value)
                self.assertEqual(preferences.language_name(state), preferences.DEFAULT_LANGUAGE)
                self.assertNotIn("admin", state)

    def test_initial_browser_response_cannot_overwrite_a_newer_user_choice(self):
        state = {}
        preferences.select_language(state, "English")
        preferences.hydrate_language(state, "pt")
        self.assertEqual(preferences.language_name(state), "English")

    def test_returning_between_pages_keeps_latest_native_selection(self):
        state = {}
        preferences.hydrate_language(state, "en")
        preferences.select_language(state, "Português (Portugal)")
        self.assertEqual(state["app_lang_selector"], state["admin_language"])
        self.assertEqual(preferences.language_name(state), "Português (Portugal)")
        preferences.select_language(state, "English")
        self.assertEqual(state["app_lang_selector"], state["admin_language"])
        self.assertEqual(preferences.language_name(state), "English")

    def test_invalid_native_choice_does_not_mutate_preferences(self):
        state = {"app_lang": "English"}
        for value in ("en", "French", None, [], {}):
            preferences.select_language(state, value)
        self.assertEqual(state, {"app_lang": "English"})

    def test_mount_never_sends_the_default_as_a_write_before_browser_ack(self):
        calls = []
        state = {"identity": "private", "password": "private", "app_lang": "English"}
        fake_streamlit = SimpleNamespace(
            session_state=state,
            components=SimpleNamespace(v2=SimpleNamespace(
                component=lambda *args, **kwargs: lambda **mounted: calls.append(mounted)
            )),
        )
        with patch.dict("sys.modules", {"streamlit": fake_streamlit}):
            preferences.mount_browser_language()
            self.assertEqual(calls[-1]["data"], {"ready": False, "language": None})
            preferences.hydrate_language(state, "en")
            preferences.mount_browser_language()
            self.assertEqual(calls[-1]["data"], {"ready": True, "language": "en"})
            self.assertEqual(calls[-1]["height"], 0)

    def test_component_callback_accepts_only_its_language_response(self):
        state = {preferences.COMPONENT_KEY: {"preference": "en", "admin": True}}
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences._receive_browser_language()
        self.assertEqual(preferences.language_name(state), "English")
        self.assertNotIn("admin", state)

    def test_header_flags_change_shared_language_and_ignore_invalid_values(self):
        state = {"ui_page_header": {"selection": "en"}}
        with patch.dict("sys.modules", {"streamlit": SimpleNamespace(session_state=state)}):
            preferences._receive_header_language()
            self.assertEqual(preferences.language_name(state), "English")
            state["ui_page_header"] = {"selection": "pt"}
            preferences._receive_header_language()
            self.assertEqual(preferences.language_name(state), "Português (Portugal)")
            state["ui_page_header"] = {"selection": {"admin": True}}
            preferences._receive_header_language()
            self.assertNotIn("admin", state)

    def test_navigation_is_hidden_and_light_theme_implementation_removed(self):
        self.assertIn('position="hidden"', (ROOT / "app.py").read_text(encoding="utf-8"))
        for filename in ("dashboard_page.py", "admin_page.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn('with st.sidebar', source)
            self.assertIn('ui_preferences.render_page_header', source)
            self.assertNotIn('theme_mode', source)
        self.assertNotIn('LIGHT_STYLE', (ROOT / 'season_insights.py').read_text(encoding='utf-8'))

    def test_both_entrypoints_mount_preference_before_routing(self):
        for filename in ("app.py", "admin_app.py"):
            tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
            preference = next(node for node in calls if ast.unparse(node.func) == "ui_preferences.mount_browser_language")
            navigation = next(node for node in calls if ast.unparse(node.func) == "st.navigation")
            page_config = next(node for node in calls if ast.unparse(node.func) == "st.set_page_config")
            self.assertLess(page_config.lineno, preference.lineno)
            self.assertLess(preference.lineno, navigation.lineno)
            page_run = next(node for node in calls if ast.unparse(node.func) == "navigation.run")
            self.assertFalse(any(ast.unparse(node.func) == "st.stop" for node in calls))
            self.assertLess(navigation.lineno, page_run.lineno)
            self.assertIn('initial_sidebar_state="collapsed"', (ROOT / filename).read_text(encoding="utf-8"))

    def test_mount_recovers_replayed_value_without_callback(self):
        state = {}
        fake = SimpleNamespace(session_state=state, query_params={"lang": "pt"},
            components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k:
                lambda **mounted: {"preference": "en"})))
        with patch.dict("sys.modules", {"streamlit": fake}):
            preferences.mount_browser_language()
        self.assertEqual(state["app_lang"], "English")
        self.assertTrue(state[preferences.READY_KEY])

    def test_unresponsive_component_keeps_url_hint_without_blocking_later_hydration(self):
        state = {}
        fake = SimpleNamespace(session_state=state, query_params={"lang": "en"},
            components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k:
                lambda **mounted: None)))
        with patch.dict("sys.modules", {"streamlit": fake}):
            preferences.mount_browser_language()
            preferences.mount_browser_language()
        self.assertEqual(state["app_lang"], "English")
        self.assertFalse(state.get(preferences.READY_KEY, False))
        preferences.hydrate_language(state, "pt")
        self.assertEqual(state["app_lang"], "Português (Portugal)")


@unittest.skipUnless(shutil.which("node"), "Node is required for the component's isolated JavaScript tests")
class LanguageJavascriptTests(unittest.TestCase):
    def test_component_read_write_and_storage_failure_contract(self):
        # Execute only our static component against a fake Storage object: this
        # does not inspect or mutate any actual browser profile or storage.
        script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const source = JSON.parse(fs.readFileSync(0, "utf8"));
const mount = new Function(source.replace("export default function", "return function"))();
const key = "f1puskasleague.language.v1";
let stored = "en", writes = [], responses = [], blocked = false;
global.window = {location:{search:''},localStorage: {
    getItem(name) { assert.equal(name, key); if (blocked) throw Error("blocked"); return stored; },
    setItem(name, value) { assert.equal(name, key); if (blocked) throw Error("blocked"); writes.push(value); stored = value; },
}};
const send = (name, value) => { assert.equal(name, "preference"); responses.push(value); };

// A fresh session reads its saved value and never first writes the default.
mount({data: {ready: false, language: null}, setStateValue: send});
assert.deepEqual(responses, ["en"]);
assert.deepEqual(writes, []);
mount({data: {ready: true, language: "en"}, setStateValue: send});
assert.deepEqual(writes, []);

// A click is persisted without an unnecessary component-induced script loop.
mount({data: {ready: true, language: "pt"}, setStateValue: send});
assert.deepEqual(writes, []);
assert.deepEqual(responses, ["en"]);
stored = "pt"; // Only an explicit flag click writes the preference.
mount({data: {ready: false, language: null}, setStateValue: send});
assert.equal(responses.at(-1), "pt");
window.location.search = '?view=race-centre&lang=en';
mount({data: {ready: false, language: null}, setStateValue: send});
assert.equal(responses.at(-1), "pt"); // The latest explicit choice beats an older link.
stored = null;
mount({data: {ready: false, language: null}, setStateValue: send});
assert.equal(responses.at(-1), "en");
assert.deepEqual(writes, []);
window.location.search = '';

// Corrupt and absent values are neither evaluated nor sent to the server.
for (storedValue of [null, "", "EN", "es", '<script>alert(1)</script>']) {
    stored = storedValue;
    mount({data: {ready: false, language: null}, setStateValue: send});
    assert.equal(responses.at(-1), "pt");
}

// Denied reads/writes do not break first paint or native language changes.
blocked = true;
mount({data: {ready: false, language: null}, setStateValue: send});
assert.equal(responses.at(-1), "pt");
mount({data: {ready: true, language: "en"}, setStateValue: send});
assert.deepEqual(writes, []);
console.log("Language component JavaScript checks passed");
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            input=json.dumps(preferences.LANGUAGE_COMPONENT_JS),
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
