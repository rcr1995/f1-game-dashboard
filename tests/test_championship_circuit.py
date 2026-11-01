from dataclasses import replace
from io import BytesIO
import json
import unittest

import pandas as pd

import championship_circuit as circuit
import championship_circuit_ui as ui
import dashboard_core as core
import league_config as config
from tests.test_league_config import basic_setup, scoring_points


class ChampionshipCircuitTests(unittest.TestCase):
    def setUp(self):
        self.setup = basic_setup(status="Active")
        self.tables = config.config_tables_from_setup(self.setup)
        self.meta = {"Game": "F1 27", "SeasonLabel": "2027-T01", "League Name": "New League"}
        self.calendar = pd.DataFrame([
            {"League Name": "New League", "Round": 1, "GP Name": "Australian GP", "Date": pd.Timestamp("2027-01-10"), "Status": "Upcoming", "Has Sprint": False},
            {"League Name": "New League", "Round": 2, "GP Name": "Chinese GP", "Date": pd.Timestamp("2027-01-17"), "Status": "Upcoming", "Has Sprint": True},
        ])

    def result(self, driver="Alice", points=26, position=1, rnd=1, kind="R", **kwargs):
        return {**self.meta, "Season": self.meta["SeasonLabel"], "Driver": driver, "Team": "Red", "Round": rnd,
                "GP Name": "Australian GP" if rnd == 1 else "Chinese GP", "Type": kind,
                "Points": points, "Finish Pos": position, "IsSeasonFinal": False, **kwargs}

    def build(self, rows=(), **kwargs):
        return circuit.build_model(pd.DataFrame(rows) if rows else pd.DataFrame([self.result()]).iloc[:0],
                                   kwargs.get("calendar", self.calendar), kwargs.get("meta", self.meta),
                                   kwargs.get("tables", self.tables))

    def test_preseason_grid_uses_roster_and_all_scoring_opportunities(self):
        model = self.build()
        self.assertEqual([d["name"] for d in model["drivers"]], ["Alice", "Bob"])
        grid = model["frames"][0]
        self.assertEqual((grid["remaining"], grid["target"]), (60, 60))  # 2*(25+1) + 8
        self.assertEqual(grid["remainingTeam"],60)  # Configured teams each have one car.
        self.assertTrue(all(d["progress"] == 0 for d in grid["standings"]))
        self.assertEqual(model["defaultIndex"], 0)

    def test_every_checkpoint_has_its_own_target_and_exact_points(self):
        rows = [self.result(), self.result("Bob",18,2), self.result("Alice",18,2,2), self.result("Bob",26,1,2),
                self.result("Alice",7,2,2,"SR"),self.result("Bob",8,1,2,"SR")]
        model = self.build(rows)
        self.assertEqual(model["defaultIndex"], 2)
        first, last = model["frames"][1:]
        self.assertEqual((first["target"],first["remaining"]), (60,34))
        self.assertAlmostEqual(first["standings"][0]["progress"],26/60)
        self.assertEqual((last["target"],last["remaining"], last["completed"]), (52,0,2))
        self.assertEqual(last["standings"][0]["progress"],1)
        self.assertEqual(last["standings"][1]["points"],51)
        self.assertEqual(last["standings"][1]["gap"],1)
        self.assertAlmostEqual(last["standings"][1]["progress"],51/52)
        self.assertEqual(first["remainingSprints"],1)

    def test_tied_champions_reach_finish_using_existing_tiebreaks(self):
        self.calendar.loc[1,"Has Sprint"] = False
        rows = [self.result(points=25),self.result("Bob",25,2),self.result("Alice",18,2,2),self.result("Bob",18,3,2)]
        model = self.build(rows)
        final = model["frames"][-1]["standings"]
        self.assertEqual([d["progress"] for d in final],[1,1])
        expected = core.standings_table(pd.DataFrame(rows),"Drivers").Driver.tolist()
        names={d["id"]:d["name"] for d in model["drivers"]}
        self.assertEqual([names[d["id"]] for d in final], expected)

    def test_bonus_maximum_is_for_one_eligible_driver(self):
        profile=config.ResolvedScoringProfile("p","l","R",1,((1,10),(2,40)),5,1)
        self.assertEqual(circuit.event_maximum(profile),40)  # Not 45: P2 ineligible.
        self.assertEqual(circuit.event_maximum(replace(profile, fastest_lap_max_finish=None)),45)
        self.assertEqual(circuit.team_event_maximum(profile,2),55)  # Bonus is awarded once.

    def test_effective_scoring_changes_apply_to_their_calendar_rounds(self):
        setup=replace(self.setup,scoring_profiles=self.setup.scoring_profiles+(config.ScoringProfile("double",self.setup.key.league_id,"R",2),),
                      scoring_points=self.setup.scoring_points+scoring_points("double",[50,36]))
        model=self.build([self.result()], tables=config.config_tables_from_setup(setup))
        self.assertEqual(model["frames"][0]["target"],84)  # 26 + 50 + 8
        self.assertEqual(model["frames"][1]["remaining"],58)

    def test_postponed_rounds_follow_dates_and_only_completed_races_play(self):
        self.calendar.loc[0,"Date"] = pd.Timestamp("2027-02-01")
        rows=[self.result(rnd=2), self.result("Bob",18,2,2),self.result("Alice",8,1,2,"SR")]
        model=self.build(rows)
        self.assertEqual([f["round"] for f in model["frames"]],[0,2])
        self.assertEqual(model["frames"][-1]["remaining"],26)
        # A future Sprint is not a completed main-race checkpoint.
        rows.append(self.result("Bob",8,1,1,"SR"))
        self.assertEqual(len(self.build(rows)["frames"]),2)

    def test_cancelled_races_do_not_count_as_remaining_opportunities(self):
        self.calendar.loc[1,"Status"]="Cancelled"
        model=self.build([self.result()])
        self.assertEqual(model["totalRaces"],1)
        self.assertEqual(model["frames"][-1]["remaining"],0)
        self.assertEqual(model["frames"][-1]["standings"][0]["progress"],1)

    def test_revised_points_and_penalties_are_not_rescored(self):
        model=self.build([self.result(points=19.5),self.result("Bob",-3,2)])
        entries=model["frames"][-1]["standings"]
        self.assertEqual([e["points"] for e in entries],[19.5,-3])
        self.assertEqual(model["frames"][-1]["target"],53.5)
        self.assertAlmostEqual(entries[1]["progress"],-3/53.5)

    def test_sprint_before_a_cancelled_gp_still_counts_at_the_next_checkpoint(self):
        self.calendar.loc[0,"Status"]="Cancelled"
        self.calendar.loc[0,"Has Sprint"]=True
        rows=[self.result("Alice",8,1,1,"SR"),self.result("Bob",7,2,1,"SR"),
              self.result("Alice",26,1,2),self.result("Bob",18,2,2),
              self.result("Alice",8,1,2,"SR"),self.result("Bob",7,2,2,"SR")]
        model=self.build(rows)
        self.assertEqual(model["totalRaces"],1)
        final=model["frames"][-1]
        self.assertEqual(final["standings"][0]["points"],42)
        self.assertEqual(final["remaining"],0)
        self.assertEqual(final["standings"][0]["progress"],1)

    def test_zero_finish_score_is_finite_and_zero_point_drivers_remain(self):
        self.calendar.loc[1,"Status"]="Cancelled"
        model=self.build([self.result(points=0),self.result("Bob",0,2)])
        self.assertEqual(model["frames"][-1]["target"],0)
        self.assertEqual([e["progress"] for e in model["frames"][-1]["standings"]],[0,0])
        json.dumps(model,allow_nan=False)

    def test_summary_only_shows_current_points_without_fabricated_playback(self):
        self.calendar["Status"]="Done"
        rows=[self.result(points=100,IsSeasonFinal=True),self.result("Bob",75,2,IsSeasonFinal=True)]
        model=self.build(rows)
        self.assertFalse(model["playback"])
        self.assertEqual(len(model["frames"]),1)
        self.assertEqual(model["frames"][0]["standings"][0]["progress"],1)
        self.assertIn("history_unavailable",model["notes"])

    def test_missing_history_and_duplicate_results_disable_playback(self):
        self.calendar.loc[0,"Status"]="Done"
        for rows in ([self.result(rnd=2)], [self.result(),self.result()]):
            with self.subTest(rows=rows):
                self.assertFalse(self.build(rows)["playback"])

    def test_no_calendar_keeps_standings_and_explains_unavailable_target(self):
        model=self.build([self.result()],calendar=self.calendar.iloc[:0])
        self.assertFalse(model["playback"])
        self.assertIsNone(model["frames"][0]["target"])
        self.assertEqual(model["frames"][0]["standings"][0]["points"],26)

    def test_2026_sprint_fallback_uses_season_not_january_race_year(self):
        meta={**self.meta,"SeasonLabel":"2026-T02"}
        cal=self.calendar.copy()
        cal.loc[1,"GP Name"]="Miami GP"
        cal.attrs["has_explicit_sprint_schedule"]=False
        # Verify a complete, legacy position-based scale (no bonus guessed).
        rows=[{**self.result(points=25),"SeasonLabel":"2026-T02"},
              {**self.result("Bob",18,2),"SeasonLabel":"2026-T02"}]
        model=self.build(rows,calendar=cal,meta=meta,tables=config.empty_config_tables())
        self.assertEqual(model["frames"][-1]["remaining"],33)
        self.assertEqual(model["frames"][-1]["remainingTeam"],58)
        self.assertIn("sprint_2026",model["notes"])
        cal.attrs["has_explicit_sprint_schedule"]=True
        cal["Has Sprint"]=False
        model=self.build(rows,calendar=cal,meta=meta,tables=config.empty_config_tables())
        self.assertEqual(model["frames"][-1]["remaining"],25)

    def test_calendar_loader_preserves_presence_of_explicit_sprint_column(self):
        for explicit in [True,False]:
            book=BytesIO()
            with pd.ExcelWriter(book) as writer:
                cal=self.calendar if explicit else self.calendar.drop(columns="Has Sprint")
                cal.to_excel(writer,sheet_name="Calendar",index=False)
            book.seek(0)
            self.assertEqual(core.load_calendar_data(book).attrs["has_explicit_sprint_schedule"],explicit)

    def test_another_season_is_not_added_to_current_points(self):
        model=self.build([self.result(),self.result(points=900,SeasonLabel="2025-T01")])
        self.assertEqual(model["frames"][-1]["standings"][0]["points"],26)

    def test_labels_are_unique_colors_stable_and_names_escaped(self):
        drivers=circuit._drivers({"Charles", "Charlie", '<img onerror="bad">'})
        self.assertEqual(len({d["label"] for d in drivers}),3)
        self.assertEqual(drivers,circuit._drivers({d["name"] for d in drivers}))
        model=self.build([self.result()]);model['meta']['League Name']='<img src=x onerror=bad>'
        self.assertNotIn('<img src=x',ui.render(model))
        self.assertIn('&lt;img',ui.render(model))


if __name__ == "__main__":
    unittest.main()
