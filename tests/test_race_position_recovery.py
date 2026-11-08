"""Only independently forced, plausible OCR digit mistakes are corrected."""
import unittest

import race_import as race


def token(text, x, y, width=45, confidence=.99):
    return race.OcrToken(text, confidence, x, y, x + width, y + 10, "Screenshot")


def detail_rows(positions, *, ys=None, header=True, position_confidences=None, combined_labels=False,
                extra_position_labels=None):
    tokens = ([token("POS.", 500, 170), token("DRIVER", 560, 170, 80),
               token("TEAM", 680, 170), token("GRID", 790, 170), token("BEST", 850, 170),
               token("TIME", 930, 170), token("PTS.", 1000, 170)] if header else [])
    ys = ys or [200 + index * 20 for index in range(len(positions))]
    roster = [race.DriverEntry(f"Pilot {index}", "Team") for index in range(22)]
    for index, (position, y) in enumerate(zip(positions, ys)):
        if position is not None:
            label = f"{position} Pilot {index}" if combined_labels else str(position)
            confidence = position_confidences[index] if position_confidences else .99
            tokens.append(token(label, 500, y, 20, confidence))
            if extra_position_labels:
                tokens.append(token(extra_position_labels[index], 525, y, 25))
        tokens.extend([token(roster[index].driver, 560, y, 100),
                       token("1:15.123", 850, y, 65), token("+1 Lap", 930, y, 60)])
    return race.extract_results_from_tokens(tokens, roster, source="Screenshot")


class PositionDigitRecoveryTests(unittest.TestCase):
    def test_isolated_six_in_place_of_nine_requires_bracketing_anchors(self):
        rows = detail_rows([7, 8, 6, 10, 11])
        self.assertEqual([row.position for row in rows], [7, 8, 9, 10, 11])
        self.assertIn("corrected from contiguous detail rows", " ".join(rows[2].issues))

    def test_later_page_recovers_edge_nine_and_dropped_one_without_adding_rows(self):
        # Models the real page's 9->6 and 15->5 mistakes, with unreadable
        # positions 11,18,19. The two anchors supporting row 9 are 10 and 12.
        rows = detail_rows([6, 10, None, 12, 13, 14, 5, 16, 17, None, None, 20, 21, 22])
        self.assertEqual(len(rows), 14)
        self.assertEqual([row.position for row in rows], list(range(9, 23)))
        self.assertTrue(all("corrected" in " ".join(rows[i].issues) for i in (0, 6)))
        self.assertTrue(all("inferred" in " ".join(rows[i].issues) for i in (2, 9, 10)))

    def test_missing_physical_row_or_extra_detail_row_prevents_correction(self):
        missing = detail_rows([13, 14, 5, 16, 17], ys=[200, 220, 260, 280, 300])
        self.assertEqual(missing[2].position, 5)
        extra = detail_rows([13, 14, 5, None, 16, 17])
        self.assertEqual(extra[2].position, 5)

    def test_arbitrary_numbers_and_insufficient_anchors_are_not_reordered(self):
        for positions in ([8, 4, 10], [6, 10], [6, None, 12]):
            with self.subTest(positions=positions):
                rows = detail_rows(positions)
                self.assertEqual([row.position for row in rows], positions)

    def test_summary_or_missing_header_does_not_gain_digit_corrections(self):
        rows = detail_rows([8, 6, 10], header=False)
        self.assertEqual([row.position for row in rows], [8, 6, 10])

    def test_supporting_digit_tokens_must_be_credible_even_when_row_text_is_clear(self):
        for combined in (False, True):
            for confidences in ([.01, .99, .01], [.649, .99, .99], [.99, .99, .649]):
                with self.subTest(combined=combined, confidences=confidences):
                    rows = detail_rows([8, 6, 10], position_confidences=confidences,
                                       combined_labels=combined)
                    self.assertEqual([row.position for row in rows], [8, 6, 10])
            rows = detail_rows([8, 6, 10], position_confidences=[.65, .99, .65],
                               combined_labels=combined)
            self.assertEqual([row.position for row in rows], [8, 9, 10])

    def test_legacy_missing_position_inference_remains_unchanged(self):
        rows = detail_rows([8, None, 10], position_confidences=[.01, .99, .01])
        self.assertEqual([row.position for row in rows], [8, 9, 10])

    def test_later_text_cannot_replace_the_recognized_low_confidence_digit(self):
        for labels in (["8", "6", "10"], ["8 Racer", "6 Racer", "10 Racer"]):
            with self.subTest(labels=labels):
                rows = detail_rows([8, 6, 10], position_confidences=[.01, .99, .01],
                                   extra_position_labels=labels)
                self.assertEqual([row.position for row in rows], [8, 6, 10])


if __name__ == "__main__":
    unittest.main()
