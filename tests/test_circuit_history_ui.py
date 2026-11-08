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


if __name__ == '__main__':
    unittest.main()
