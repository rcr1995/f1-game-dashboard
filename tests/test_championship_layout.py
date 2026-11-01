"""Fixed championship lanes must preserve points and forward circuit progress."""
import shutil
import subprocess
import unittest

import championship_circuit_ui as ui


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for geometry tests")
class ChampionshipLayoutTests(unittest.TestCase):
    def test_pit_departure_is_forward_and_corrections_do_not_drive_backwards(self):
        script = ui.JS + r"""
const assert=require('node:assert/strict');
for(const first of [.001,.01,.2])for(const pitLength of [200,800]){
  let previous=-pitLength;
  for(let i=0;i<=1000;i++){
    const p=first*2*i/1000,s=championshipPitDistance(p,3400,pitLength,first);
    assert.ok(s>=previous-1e-9,'forward pit exit and lap');previous=s;
  }
  assert.equal(championshipPitDistance(0,3400,pitLength,first),-pitLength);
  assert.equal(championshipPitDistance(first,3400,pitLength,first),first*3400);
}
const corrected=[0,.1,.2,.15,.3];
for(let x=2;x<3;x+=.01)assert.equal(championshipForwardProgress(corrected,x),.2);
assert.equal(championshipForwardProgress(corrected,3),.15);
assert.equal(championshipForwardProgress(corrected,4),.3);
assert.equal(championshipCorrectionOpacity(corrected,4),1,'later results remain visible after a correction');
assert.equal(championshipCorrectionOpacity([0,.2,.1],2),1,'final corrected result is visible');
assert.ok(championshipCorrectionOpacity(corrected,2.95)<.5,'fade out before corrected checkpoint');
assert.equal(championshipCorrectionOpacity([0],0),1);
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
// A fixed latest-standing row must never drift during interpolation.
for(const row of [0,1,10,21]){
  const fixed=championshipSeries(Array(8).fill(row));
  for(let x=0;x<=7;x+=.01)assert.ok(Math.abs(fixed(x)-row)<1e-10);
}
console.log('Continuous speed, checkpoint precision, fixed rows and no playback delays passed');
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixed_lanes_keep_tied_drivers_distinct_without_changing_distance(self):
        script = ui.JS + r"""
const assert = require('node:assert/strict');
const length = 3400, order=Array.from({length:22},(_,i)=>String(i));
const entries = values => values.map((progress,i)=>({id:String(i),position:i+1,points:progress*100,progress}));
function check(values) {
  const input=entries(values), layout=championshipTrackLayout(input,order,length);
  assert.equal(layout.size,input.length);
  input.forEach(e=>{
    const p=layout.get(e.id),i=order.indexOf(e.id);
    assert.equal(p.p,Math.min(1,Math.max(0,e.progress||0)));
    assert.equal(p.s,p.p*length,'distance is solely the points fraction, with no crowding adjustment');
    assert.ok(Number.isFinite(p.s));assert.ok(p.s>=0&&p.s<=length);
    assert.equal(p.lane,(i-(order.length-1)/2)*8);
    assert.ok(Math.abs(p.lane)<=84,'22 lanes remain within the widened road');
    assert.equal(p.row,i,'straight rows use the fixed latest order');
    assert.equal(p.pit,!(e.points>0));assert.equal(p.pitIndex,i);
  });
  const reversed=championshipTrackLayout([...input].reverse().map(e=>({...e,position:23-e.position})),order,length);
  input.forEach(e=>assert.deepEqual(layout.get(e.id),reversed.get(e.id),'historical ranks and input order cannot relocate a driver'));
  return layout;
}
for(const p of [0.001,0.03,0.25,0.5,0.97,1])check(Array(22).fill(p));
for(let seed=1;seed<=30;seed++)check(Array.from({length:22},(_,i)=>((i*seed*17)%37)/1000));
const tied=check(Array(22).fill(.2));
assert.equal(new Set([...tied.values()].map(p=>p.lane)).size,22,'tied drivers keep individually distinct lateral lanes');
assert.equal(new Set([...tied.values()].map(p=>p.s)).size,1,'a tie never changes points distance');
const end=check([1,1,0.8,0.4,0,0]);
assert.equal(end.get('0').p,1);assert.equal(end.get('0').s,length);
assert.equal(end.get('1').p,1);assert.equal(end.get('1').s,length);
const grid=check(Array(22).fill(0));
assert.ok([...grid.values()].every(p=>p.pit&&p.p===0&&p.s===0));
assert.equal(new Set([...grid.values()].map(p=>p.pitIndex)).size,22,'every zero-point driver has a distinct pit bay');
assert.equal(championshipTrackLayout([],[],length).size,0);
console.log('Tied lanes, exact distance, finish, pit bays and fixed rows passed');
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rank_changes_cannot_reverse_a_scoring_drivers_circuit_distance(self):
        script = ui.JS + r"""
const assert=require('node:assert/strict');
const order=Array.from({length:22},(_,i)=>String(i)),length=4300,history=[];
for(let race=0;race<12;race++){
  const standings=order.map((id,i)=>({id,position:((i+race*7)%22)+1,points:race*(i%5+1),progress:race*(i%5+1)/200}));
  history.push(championshipTrackLayout(standings,order,length));
}
for(const id of order){
  const distances=history.map(frame=>frame.get(id).s),lane=history[0].get(id).lane,row=history[0].get(id).row;
  history.forEach((frame,i)=>{
    const p=frame.get(id);assert.equal(p.lane,lane);assert.equal(p.row,row);
    if(i)assert.ok(p.s>=history[i-1].get(id).s,'losing a rank cannot send the car backwards');
  });
  const animate=championshipSeries(distances);let previous=animate(0);
  for(let cursor=.002;cursor<=11;cursor+=.002){const next=animate(cursor);assert.ok(next>=previous-1e-9,'interpolated playback remains forwards');previous=next;}
}
console.log('Changing historical ranks cannot reverse fixed-lane circuit motion');
"""
        result = subprocess.run([shutil.which("node"), "-"], input=script,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
