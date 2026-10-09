"""Session selection must stay stable on reruns without repeating the last visit."""
import shutil
import subprocess
import unittest
from unittest.mock import patch

import dashboard_surface as surface
import puskas_html


class HeroRotationTests(unittest.TestCase):
    def test_three_distinct_packaged_images(self):
        options = puskas_html.hero_image_options()
        self.assertEqual({image["id"] for image in options}, {"floodlit", "wet-night", "sunset"})
        self.assertEqual(len({image["src"] for image in options}), 3)
        for image in options:
            self.assertTrue(image["src"].startswith("data:image/webp;base64,"))

    def test_rerenders_share_visit_but_new_sessions_do_not(self):
        visits = []
        with patch.object(surface, "st") as st:
            component = st.components.v2.component.return_value
            for _ in range(2):
                st.session_state = {}
                surface.render('<div class="p-hero"></div>', lang="en", key="home")
                first = component.call_args.kwargs["data"]
                surface.render('<div class="p-hero"></div>', lang="pt", key="home")
                second = component.call_args.kwargs["data"]
                self.assertEqual(first["heroVisit"], second["heroVisit"])
                self.assertEqual(len(first["heroImages"]), 3)
                visits.append(first["heroVisit"])
            self.assertNotEqual(*visits)
            surface.render('<div>Race Centre</div>', lang="en", key="results")
            self.assertNotIn("heroImages", component.call_args.kwargs["data"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser selection test")
    def test_browser_selection_handles_visits_storage_and_fallbacks(self):
        script = surface.JS + r"""
import assert from 'node:assert/strict';
const options = [{id:'floodlit'}, {id:'wet-night'}, {id:'sunset'}];
let stored = 'floodlit', writes = 0;
globalThis.window = {localStorage:{
  getItem(key) { assert.equal(key,heroStorageKey); return stored; },
  setItem(key,value) { assert.equal(key,heroStorageKey); stored=value; writes++; }
}};
Math.random = () => 0;
assert.equal(chooseHero(options,'first-visit').id, 'wet-night');
// Language changes, data refreshes and component remounts in this visit stay put.
Math.random = () => 0.999;
for (let i=0;i<5;i++) assert.equal(chooseHero(options,'first-visit').id,'wet-night');
assert.equal(writes,1);
assert.equal(chooseHero(options,'second-visit').id,'sunset');
// A new document has no module memory, but still excludes the stored previous image.
heroSelection=null;
assert.notEqual(chooseHero(options,'third-visit').id,'sunset');
// Storage restrictions must not break the header or its stability within a visit.
window.localStorage = {getItem(){throw Error('blocked')}, setItem(){throw Error('blocked')}};
heroSelection=null;
const blocked=chooseHero(options,'blocked-storage');
Math.random = () => 0;
assert.equal(chooseHero(options,'blocked-storage').id,blocked.id);
assert.equal(chooseHero([], 'empty'),null);
assert.equal(chooseHero([options[0]],'one-image').id,'floodlit');
// A removed asset cannot leave a stale selection or empty alternative pool.
assert.equal(chooseHero([options[1]],'one-image').id,'wet-night');
console.log('Session stability, random selection, no-repeat and fallbacks passed');
"""
        result = subprocess.run([shutil.which("node"), "--input-type=module", "-"], input=script,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
