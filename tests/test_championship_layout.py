"""Neutral team lanes, zero-point initial state and continuous straight playback."""
import shutil
import subprocess
import unittest

import championship_circuit_ui as ui


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for controller tests")
class ChampionshipLayoutTests(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run([shutil.which("node"), "-"], input=ui.JS + checks,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_team_groups_are_adjacent_alphabetical_and_independent_of_points(self):
        self.run_js(r"""
const assert=require('node:assert/strict');
const drivers=[
  {id:'champion',name:'Zoe',team:'McLaren',points:900},
  {id:'zero',name:'Alex',team:'McLaren',points:0},
  {id:'m2',name:'Bob',team:'Mercedes',points:100},
  {id:'m1',name:'Alice',team:'Mercedes',points:200},
  {id:'unknown',name:'Abel',team:'',points:1000},
  {id:'audi',name:'Nico',team:'Audi',points:50}
];
const expected=['audi','zero','champion','m1','m2','unknown'];
assert.deepEqual(championshipTeamOrder(drivers),expected);
assert.deepEqual(championshipTeamOrder([...drivers].reverse().map(d=>({...d,points:1000-d.points}))),expected);
assert.deepEqual(championshipTeamOrder([]),[]);
assert.deepEqual(championshipTeamOrder([{id:'a',name:'A',team:'red'},{id:'b',name:'B',team:' Red '}]),['a','b']);
""")

    def test_starting_grid_is_used_even_when_backend_default_is_latest(self):
        self.run_js(r"""
const assert=require('node:assert/strict');
const drivers=[{id:'a',name:'Alice',team:'Red'},{id:'b',name:'Bob',team:'Blue'}];
const grid={name:'grid',round:0,standings:drivers.map((d,i)=>({id:d.id,points:0,gap:0,progress:0,position:i+1}))};
const latest={name:'Mexico',standings:[{id:'a',points:254,progress:.4},{id:'b',points:125,progress:.2}]};
const model={drivers,frames:[grid,latest],defaultIndex:1,playback:true};
const before=JSON.stringify(model),frames=championshipPlaybackFrames(model);
assert.equal(frames[0].name,'grid');
assert.ok(frames[0].standings.every(e=>e.points===0&&e.progress===0&&e.gap===0));
assert.equal(frames[1].standings[0].points,254);
assert.equal(JSON.stringify(model),before,'UI must not alter shared scoring data');
const summary=championshipPlaybackFrames({drivers,frames:[latest],defaultIndex:0,playback:false,totalRaces:24});
assert.equal(summary[0].name,'grid');assert.equal(summary[0].target,null);
assert.ok(summary[0].standings.every(e=>e.progress===0&&e.points===0));
assert.equal(summary[1],latest,'saved standings remain available explicitly without fabricated history');
""")

    def test_continuous_motion_meets_checkpoints_without_race_boundary_stops(self):
        self.run_js(r"""
const assert=require('node:assert/strict');
const values=[0,.04,.09,.15,.17,.28,.31,.4],sample=championshipSeries(values),epsilon=1e-5;
values.forEach((v,i)=>assert.ok(Math.abs(sample(i)-v)<1e-12));
for(let i=1;i<values.length-1;i++){
 const before=(sample(i)-sample(i-epsilon))/epsilon,after=(sample(i+epsilon)-sample(i))/epsilon;
 assert.ok(before>0&&after>0);assert.ok(Math.abs(before-after)<1e-4);
}
let previous=sample(0);
for(let x=0;x<=7;x+=.001){const next=sample(x);assert.ok(next>=previous-1e-12&&next<=.4);previous=next;}
assert.equal(advanceChampionship(.999,24,1,10),1.009);
assert.equal(advanceChampionship(2,2400,.5,10),2.5);
assert.equal(advanceChampionship(2,2400,2,10),4);
assert.equal(advanceChampionship(9.9,2400,1,10),10);
assert.equal(championshipSeries([0])(10),0);
const corrections=[0,.1,.2,.15,.3];
for(let x=2;x<3;x+=.01)assert.equal(championshipForwardProgress(corrections,x),.2);
assert.equal(championshipForwardProgress(corrections,3),.15);
assert.equal(championshipForwardProgress(corrections,4),.3);
assert.equal(championshipCorrectionOpacity(corrections,4),1);
assert.equal(championshipCorrectionOpacity([0,.2,.1],2),1);
""")

    def test_removed_view_has_no_markup_or_controller(self):
        model={'meta':{},'notes':[]}
        rendered=ui.render(model)
        self.assertNotIn('cc-view-switch',rendered)
        self.assertNotIn('cc-layout',rendered)
        self.assertNotIn('cc-track',rendered)
        self.assertNotIn('pit',rendered.lower())
        self.assertNotIn('getTotalLength',ui.JS)
        self.assertNotIn('championshipSeededOrder',ui.JS)
        self.assertNotIn('championshipTrackLayout',ui.JS)
        self.assertIn('Team',rendered)
        self.assertIn('Starting grid',rendered)
        self.assertIsNone(ui.render(None) or None)


if __name__ == '__main__':
    unittest.main()
