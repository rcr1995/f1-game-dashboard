from __future__ import annotations

import io
import unittest

from PIL import Image, ImageDraw

from race_import import OcrToken
import race_ocr


TAB_BOXES = {
    "WEEKEND": (12, 18, 112, 42),
    "SR": (124, 18, 224, 42),
    "R": (236, 18, 336, 42),
}
TAB_TEXT = {
    "WEEKEND": "RESULTS (WEEKEND)",
    "SR": "RESULTS (SPRINT)",
    "R": "RESULTS (RACE)",
}


def token(text: str, box: tuple[int, int, int, int]) -> OcrToken:
    return OcrToken(text, 0.99, *box, "Screenshot 1")


def synthetic_tabs(*selected: str, split: str | None = None) -> tuple[bytes, list[OcrToken]]:
    image = Image.new("RGB", (350, 64), (24, 31, 47))
    draw = ImageDraw.Draw(image)
    tokens: list[OcrToken] = []
    for kind, box in TAB_BOXES.items():
        fill = (176, 25, 48) if kind in selected else (65, 70, 88)
        draw.rectangle(box, fill=fill)
        # White strokes model label glyphs without making tests font-dependent.
        draw.line((box[0] + 8, 27, box[2] - 8, 27), fill=(235, 235, 238), width=2)
        draw.line((box[0] + 8, 34, box[2] - 18, 34), fill=(235, 235, 238), width=2)
        if split == kind:
            midpoint = (box[0] + box[2]) // 2
            tokens.append(token("RESULTS", (box[0] + 4, box[1] + 4, midpoint, box[3] - 4)))
            tokens.append(
                token(
                    f"({'SPRINT' if kind == 'SR' else kind})",
                    (midpoint + 1, box[1] + 4, box[2] - 4, box[3] - 4),
                )
            )
        else:
            tokens.append(token(TAB_TEXT[kind], (box[0] + 4, box[1] + 4, box[2] - 4, box[3] - 4)))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), tokens


def replace_tab_text(tokens: list[OcrToken], kind: str, text: str) -> None:
    index = next(index for index, item in enumerate(tokens) if item.text == TAB_TEXT[kind])
    original = tokens[index]
    tokens[index] = OcrToken(
        text,
        original.confidence,
        original.x_min,
        original.y_min,
        original.x_max,
        original.y_max,
        original.source,
    )


class SelectedResultsTabTests(unittest.TestCase):
    def test_detects_each_unique_red_results_tab(self):
        for selected in ("R", "SR", "WEEKEND"):
            with self.subTest(selected=selected):
                image_bytes, tokens = synthetic_tabs(selected)
                self.assertEqual(
                    race_ocr.detect_selected_results_tab(image_bytes, tokens),
                    selected,
                )

    def test_supports_split_results_and_session_ocr_boxes(self):
        image_bytes, tokens = synthetic_tabs("SR", split="SR")
        self.assertEqual(race_ocr.detect_selected_results_tab(image_bytes, tokens), "SR")

    def test_tolerates_observed_tv_photo_ocr_misspellings(self):
        cases = [
            ("R", "RESULTS (RALES)"),
            ("SR", "RESULTS (SPDINT)"),
            ("WEEKEND", "RESULTS (WGEKEND)"),
            ("WEEKEND", "RESULTS (WEEKSNO)"),
        ]
        for selected, observed_text in cases:
            with self.subTest(observed_text=observed_text):
                image_bytes, tokens = synthetic_tabs(selected)
                replace_tab_text(tokens, selected, observed_text)
                self.assertEqual(
                    race_ocr.detect_selected_results_tab(image_bytes, tokens),
                    selected,
                )

    def test_does_not_join_adjacent_full_tab_labels(self):
        image_bytes, tokens = synthetic_tabs("SR")
        replace_tab_text(tokens, "WEEKEND", "RESULIS (WEEKENO)")
        replace_tab_text(tokens, "SR", "RESULTS (SPDINT)")
        replace_tab_text(tokens, "R", "PESULTS (RACE)")
        self.assertEqual(race_ocr.detect_selected_results_tab(image_bytes, tokens), "SR")

    def test_returns_none_when_two_tabs_look_selected(self):
        image_bytes, tokens = synthetic_tabs("R", "SR")
        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_returns_none_when_no_tab_is_red(self):
        image_bytes, tokens = synthetic_tabs()
        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_returns_none_without_a_results_tab_label(self):
        image_bytes, _ = synthetic_tabs("R")
        unrelated = [token("BRITISH GRAND PRIX - RACE", (20, 18, 220, 42))]
        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, unrelated))

    def test_returns_none_for_a_low_confidence_tab_label(self):
        image_bytes, _ = synthetic_tabs("R")
        box = TAB_BOXES["R"]
        low_confidence = [
            OcrToken(
                TAB_TEXT["R"],
                0.30,
                box[0] + 4,
                box[1] + 4,
                box[2] - 4,
                box[3] - 4,
                "Screenshot 1",
            )
        ]
        self.assertIsNone(
            race_ocr.detect_selected_results_tab(image_bytes, low_confidence)
        )


if __name__ == "__main__":
    unittest.main()
