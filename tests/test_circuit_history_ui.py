"""Winner details preserve source context and cannot execute workbook text."""
import unittest

import pandas as pd

import circuit_history_ui as ui


class CircuitHistoryUiTests(unittest.TestCase):
    def card(self, **overrides):
        card = {'key':'interlagos','gp_name':'São Paulo GP',
                'circuit_name':'Autódromo José Carlos Pace', 'venue_recorded':True,
                'winners':[{'driver':'Fatacuida','league':'Teikirise','season':'2026-T02',
                            'round':11,'date':'2026-11-08','game':'F1 25'}],
                'leaders':[{'driver':'Fatacuida','wins':1}], 'race_count':1}
        card.update(overrides)
        return card

    def test_every_card_has_a_native_button_and_complete_dialog_history(self):
        card=self.card()
        rendered=ui.render([card],pd.DataFrame())
        self.assertIn('data-history-id="ch-history-0"',rendered)
        self.assertIn('aria-haspopup="dialog"',rendered)
        self.assertIn('<dialog class="ch-dialog" id="ch-history-0"',rendered)
        for text in ('Teikirise','2026-T02','08 Nov 2026','Fatacuida','F1 25',
                     'Main races only. Sprints excluded.'):
            self.assertIn(text,rendered)

    def test_unrecorded_dates_and_venues_do_not_invent_metadata(self):
        winner={**self.card()['winners'][0], 'date':None}
        rendered=ui.render([self.card(gp_name='Spanish GP',circuit_name='',
                                      venue_recorded=False,winners=[winner])],pd.DataFrame())
        self.assertIn('Circuit not recorded',rendered)
        self.assertIn('data-label="Date">—</td>',rendered)
        self.assertNotIn('George Russell',rendered)
        self.assertNotIn('Madring',rendered)

    def test_workbook_text_is_escaped_and_all_winners_remain_in_dialog(self):
        winners=[{**self.card()['winners'][0], 'driver':f'Winner {i}',
                  'league':'<img src=x onerror=alert(1)>'} for i in range(8)]
        rendered=ui.render([self.card(winners=winners)],pd.DataFrame())
        self.assertNotIn('<img src=x',rendered)
        self.assertIn('&lt;img src=x',rendered)
        for i in range(8):
            self.assertIn(f'Winner {i}',rendered)
        self.assertIn('8 races',rendered)

    def test_portuguese_labels_and_date_format(self):
        rendered=ui.render([self.card()],pd.DataFrame(),lang='pt')
        for text in ('Vencedores do GP','Liga','Época','Data','08 nov 2026',
                     'Fechar histórico de vencedores'):
            self.assertIn(text,rendered)

    def test_scoped_history_labels_match_selection_and_escape_source_text(self):
        for lang, expected in (('en', 'selected league/season'), ('pt', 'liga/época selecionada')):
            rendered = ui.render([self.card()], pd.DataFrame(), lang=lang,
                                 scope_label='F1 25 · 2026-T02 · <League>')
            self.assertIn(expected, rendered)
            self.assertIn('F1 25 · 2026-T02 · &lt;League&gt;', rendered)
            self.assertNotIn('all leagues and seasons', rendered)
            self.assertNotIn('todas as ligas e épocas', rendered)
            self.assertNotIn('<League>', rendered)

    def comparison(self):
        return [
            {'driver':'TomasRodri21', 'starts':7, 'wins':3, 'podiums':5,
             'best_lap':'1:12.000', 'best_lap_ms':72000, 'best_lap_season':'2026-T01',
             'best_lap_type':'R', 'best_lap_league':'100 por cento', 'best_lap_game':'F1 25',
             'has_results':True, 'unresolved_results':0},
            {'driver':'Polingua', 'starts':8, 'wins':2, 'podiums':5,
             'best_lap':'1:11.200', 'best_lap_ms':71200, 'best_lap_season':'2026-T02',
             'best_lap_type':'SR', 'best_lap_league':'Teikirise', 'best_lap_game':'F1 25',
             'has_results':True, 'unresolved_results':0},
            {'driver':'Fatacuida', 'starts':0, 'wins':0, 'podiums':0,
             'best_lap':None, 'best_lap_ms':None, 'best_lap_season':None,
             'best_lap_type':None, 'has_results':False, 'unresolved_results':0},
        ]

    def test_head_to_head_is_discoverable_and_detailed_history_is_preserved(self):
        output = ui.render([self.card(head_to_head=self.comparison())], pd.DataFrame())
        self.assertIn('Winner history & head-to-head', output)
        self.assertIn('aria-describedby="ch-history-0-comparison-help"', output)
        self.assertIn('Includes head-to-head statistics for the three drivers.', output)
        self.assertEqual(output.count('class="ch-compare-preview"'), 1)
        self.assertEqual(output.count('class="ch-h2h-table"'), 1)
        preview, full = ui._head_to_head_html(self.comparison(), 'Interlagos', False)
        for row in self.comparison():
            self.assertEqual((preview + full).count('>' + row['driver'] + '<'), 2)
        self.assertIn('data-label="GP results"', output)
        self.assertIn('Best laps include Races and Sprints.', output)
        self.assertIn('2026-T02 · Sprint · Teikirise · F1 25', output)
        self.assertIn('2026-T01 · Race · 100 por cento · F1 25', output)
        self.assertIn('No saved results', output)
        self.assertIn('data-label="Best lap" class="">—</td>', output)
        self.assertLess(output.index('class="ch-comparison"'), output.index('class="ch-winner-history"'))
        self.assertIn('All GP winners', output)
        self.assertIn('data-label="Date">08 Nov 2026</td>', output)

    def test_ties_are_highlighted_accessibly_without_highlighting_zero_or_missing_values(self):
        rows = self.comparison()
        rows[1].update(wins=3, best_lap='1:12.000', best_lap_ms=72000)
        _, full = ui._head_to_head_html(rows, 'Interlagos', False)
        # Two drivers share each of wins, podiums and best lap.
        self.assertEqual(full.count('Best saved value among these three drivers (tied)'), 6)
        zero = [{**row, 'wins':0, 'podiums':0, 'best_lap':None, 'best_lap_ms':None}
                for row in rows]
        preview, full = ui._head_to_head_html(zero, 'Interlagos', False)
        self.assertNotIn('class="ch-best"', preview + full)

    def test_country_race_count_and_comparison_labels_are_localized(self):
        card = self.card(country_en='Brazil', country_pt='Brasil', race_count=2,
                         unresolved_events=1, head_to_head=self.comparison())
        for lang, metadata, title, results, explanation in (
            ('en', 'Brazil · 3 GP races', 'Head-to-head', 'GP results',
             'Values reflect saved results only;'),
            ('pt', 'Brasil · 3 corridas de GP', 'Frente a frente', 'Resultados GP',
             'Os valores refletem apenas os resultados guardados;'),
        ):
            output = ui.render([card], pd.DataFrame(), lang=lang)
            for expected in (metadata, title, results, explanation):
                self.assertIn(expected, output)

    def test_head_to_head_context_and_country_escape_untrusted_source_values(self):
        rows = self.comparison()
        rows[0].update(best_lap_season='<season>', best_lap_league='<script>alert(1)</script>',
                       best_lap_game='Game & Edition', unresolved_results=1)
        output = ui.render([self.card(country_en='<country>', head_to_head=rows)], pd.DataFrame())
        self.assertNotIn('<script>', output)
        for expected in ('&lt;season&gt;', '&lt;script&gt;alert(1)&lt;/script&gt;',
                         'Game &amp; Edition', '&lt;country&gt;',
                         '1 unresolved results · partial totals'):
            self.assertIn(expected, output)


if __name__ == '__main__':
    unittest.main()
