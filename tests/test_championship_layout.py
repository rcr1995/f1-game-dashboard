"""Crowded championship fields must remain selectable and inside the road."""
import shutil
import subprocess
import unittest

import championship_circuit_ui as ui


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for geometry tests")
class ChampionshipLayoutTests(unittest.TestCase):
    def test_continuous_motion_has_no_checkpoint_stops_or_overshoot(self):
        script = ui.JS + r"""
const assert=require('node:assert/strict');
const values=[0,.04,.09,.15,.17,.28,.31,.40],sample=championshipSeries(values);
const epsilon=1e-5;
values.forEach((v,i)=>assert.ok(Math.abs(sample(i)-v)<1e-12,'exact checkpoint'));
for(let i=1;i<values.length-1;i++){
  const before=(sample(i)-sample(i-epsilon))/epsilon,after=(sample(i+epsilon)-sample(i))/epsilon;
  assert.ok(before>0&&after>0,'no forced stop at a race boundary');
  assert.ok(Math.abs(before-after)<1e-4,'continuous velocity');
}
let previous=sample(0);
for(let x=0;x<=7;x+=.001){const next=sample(x);assert.ok(next>=previous-1e-12);assert.ok(next>=0&&next<=.4);previous=next;}
for(const series of [[0,0,.1,.1,.2],[.2,.1,.1,.3],[4,1,5,2,0]]){
  const f=championshipSeries(series);
  for(let i=0;i<series.length-1;i++)for(let t=0;t<=1;t+=.01){
    const v=f(i+t);assert.ok(v>=Math.min(series[i],series[i+1])-1e-10&&v<=Math.max(series[i],series[i+1])+1e-10,'never overshoot a result or rank');
  }
}
assert.equal(championshipSeries([0])(8),0);
assert.equal(championshipSeries([1])(0),1);
// A single clock passes through boundaries without a separate race delay.
assert.equal(advanceChampionship(.999,24,1,10),1.009);
assert.equal(advanceChampionship(2,2400,.5,10),2.5);
assert.equal(advanceChampionship(2,2400,2,10),4);
assert.equal(advanceChampionship(9.9,2400,1,10),10);
assert.equal(advanceChampionship(3,0,2,10),3);
// Whole rows move with the official order, including a two-driver swap.
const a=championshipSeries([0,1,0]),b=championshipSeries([1,0,1]);
assert.equal(a(1),1);assert.equal(b(1),0);assert.ok(a(.5)>0&&a(.5)<1);assert.ok(b(.5)>0&&b(.5)<1);
console.log('Continuous speed, checkpoint precision, bounded ranks and no playback delays passed');
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
