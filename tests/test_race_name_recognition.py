"""Complete-name OCR variants remain bounded by the controlled roster."""
import unittest

import race_import as race


class GivenNameOcrRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.roster = [race.DriverEntry('Valtteri Bottas', 'Cadillac'),
                       race.DriverEntry('Alexander Albon', 'Williams'),
                       race.DriverEntry('Polingua', 'Red Bull')]

    def test_bottas_first_name_letter_confusion_is_accepted(self):
        for raw in ('6T Valtterl BOTTAS I Cadillac Formula 10 Team',
                    'AIValtterl BOTTAS Cadillac', 'Valtterl BOTTAS',
                    'VALTTERL BOTTAS'):
            with self.subTest(raw=raw):
                match = race.match_driver(raw, self.roster, ocr_confidence=.856)
                self.assertEqual(match.canonical, 'Valtteri Bottas')
                self.assertEqual(match.method, 'ocr_variant')
                self.assertFalse(match.needs_review)

    def test_low_confidence_or_incomplete_name_requires_review(self):
        low = race.match_driver('Valtterl BOTTAS', self.roster, ocr_confidence=.4)
        self.assertIsNone(low.canonical)
        self.assertEqual(low.suggestion, 'Valtteri Bottas')
        self.assertTrue(low.needs_review)
        for raw in ('Valtterl', 'BOTTAS', 'Valtterl BOTTAC', 'Valtter1 BOTTAS',
                    'Valtterl Other BOTTAS', 'OtherValtterl BOTTAS'):
            with self.subTest(raw=raw):
                self.assertIsNone(race.match_driver(raw, self.roster).canonical)

    def test_variants_cannot_select_a_driver_outside_the_roster(self):
        match = race.match_driver('Valtterl BOTTAS', [race.DriverEntry('Alice', 'Team')])
        self.assertIsNone(match.canonical)

    def test_first_name_collisions_are_not_auto_accepted(self):
        roster = [race.DriverEntry('Bill Bottas', 'A'), race.DriverEntry('Blll Bottas', 'B')]
        match = race.match_driver('Bili BOTTAS', roster)
        self.assertIsNone(match.canonical)
        self.assertTrue(match.needs_review)

    def test_surnames_and_other_name_words_must_still_match_exactly(self):
        roster = [race.DriverEntry('Billy De Silva', 'Team')]
        match = race.match_driver('Biiiy De Silva', roster)
        self.assertEqual(match.canonical, 'Billy De Silva')
        self.assertIsNone(race.match_driver('Biiiy De Sllva', roster).canonical)
        self.assertIsNone(race.match_driver('Biiiy Silva', roster).canonical)

    def test_other_fuzzy_names_still_need_a_choice(self):
        match = race.match_driver('Polingla', self.roster)
        self.assertIsNone(match.canonical)
        self.assertEqual(match.suggestion, 'Polingua')
        self.assertEqual(match.method, 'fuzzy')


if __name__ == '__main__':
    unittest.main()
