"""Crowded championship fields must remain selectable and inside the road."""
import shutil
import subprocess
import unittest

import championship_circuit_ui as ui


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for geometry tests")
class ChampionshipLayoutTests(unittest.TestCase):
    def test_bounded_packing_preserves_points_and_separates_crowded_fields(self):
        script = ui.JS + r"""
const assert = require('node:assert/strict');
const length = 3400, radius = length / (2 * Math.PI);
const pointAt = (s, lane=0) => ({x:(radius-lane)*Math.cos(s/radius),y:(radius-lane)*Math.sin(s/radius)});
const entries = values => values.map((progress,i)=>({id:String(i),position:i+1,progress}));
function check(values) {
  const input=entries(values), layout=championshipPack(input,length,pointAt);
  assert.equal(layout.size,input.length);
  const placed=[];
  input.forEach(e=>{
    const p=layout.get(e.id), xy=pointAt(p.s,p.lane);
    assert.equal(p.p,Math.min(1,Math.max(0,e.progress||0)));
    assert.ok(Number.isFinite(p.s));
    assert.ok(Math.abs(p.lane)<=40,'never spread onto the grass');
    if(!p.grid) {
      assert.ok(p.s>=0&&p.s<=length,'never wrap a non-grid pack past the finish or before zero');
      placed.forEach(other=>assert.ok(Math.abs(xy.x-other.x)>=40||Math.abs(xy.y-other.y)>=38,'distinct hit areas'));
    }
    placed.push(xy);
  });
  assert.deepEqual([...layout], [...championshipPack([...input].reverse(),length,pointAt)]);
  return layout;
}
for(const p of [0.001,0.03,0.25,0.5,0.97,1])check(Array(22).fill(p));
for(let seed=1;seed<=30;seed++)check(Array.from({length:22},(_,i)=>((i*seed*17)%37)/1000));
const end=check([1,1,0.8,0.4,0,0]);
assert.equal(end.get('0').p,1);assert.equal(end.get('0').s,length);
assert.equal(end.get('1').p,1);assert.equal(end.get('1').s,length);
const grid=championshipPack(entries(Array(22).fill(0)),length,pointAt);
assert.equal(new Set([...grid.values()].map(p=>`${p.s}:${p.lane}`)).size,22);
assert.ok([...grid.values()].every(p=>p.grid&&p.p===0&&p.s<0));
assert.deepEqual([...new Set([...grid.values()].map(p=>p.lane))],[-24,24]);
assert.equal(championshipPack([],length,pointAt).size,0);
console.log('Ties, near ties, finish, zero grid, finite geometry and stable packing passed');
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
