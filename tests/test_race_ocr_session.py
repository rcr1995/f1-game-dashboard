from __future__ import annotations

import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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


def synthetic_overall(
    heading: str,
    *,
    selected: bool = True,
    include_timing_detail: bool = True,
) -> tuple[bytes, list[OcrToken]]:
    """Model the photographed single-badge results layout used by newer games."""
    image = Image.new("RGB", (1080, 180), (24, 31, 47))
    draw = ImageDraw.Draw(image)
    overall_box = (12, 12, 172, 42)
    draw.rectangle(overall_box, fill=(176, 25, 48) if selected else (65, 70, 88))
    draw.line((20, 23, 162, 23), fill=(235, 235, 238), width=2)
    draw.line((20, 32, 150, 32), fill=(235, 235, 238), width=2)
    tokens = [token("RESULTS (OVERALL)", (18, 17, 166, 37))]
    tokens.append(token(heading, (20, 55, 390, 75)))
    if include_timing_detail:
        tokens.extend(
            [
                token("POS. DRIVER", (500, 100, 580, 115)),
                token("TEAM", (650, 100, 700, 115)),
                token("GRID", (735, 100, 775, 115)),
                token("STOPS BEST", (790, 100, 875, 115)),
                token("TIME", (900, 100, 940, 115)),
                token("PTS.", (1000, 100, 1035, 115)),
            ]
        )
    else:
        tokens.extend(
            [
                token("POS. DRIVER", (500, 100, 580, 115)),
                token("TEAM", (650, 100, 700, 115)),
                token("SR", (800, 100, 820, 115)),
                token("R", (880, 100, 890, 115)),
                token("PTS.", (1000, 100, 1035, 115)),
            ]
        )

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


def ocr_result(tokens: list[OcrToken]) -> SimpleNamespace:
    return SimpleNamespace(
        boxes=[
            [
                [item.x_min, item.y_min],
                [item.x_max, item.y_min],
                [item.x_max, item.y_max],
                [item.x_min, item.y_max],
            ]
            for item in tokens
        ],
        txts=[item.text for item in tokens],
        scores=[item.confidence for item in tokens],
    )


def large_detail_image() -> bytes:
    image = Image.new("RGB", (4000, 1800), (24, 31, 47))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def detail_pass_tokens(source: str = "Screenshot 1") -> list[OcrToken]:
    def item(text: str, box: tuple[int, int, int, int]) -> OcrToken:
        return OcrToken(text, 0.99, *box, source)

    return [
        item("RESULTS (OVERALL)", (900, 200, 1200, 240)),
        item("AUSTRALIAN GRAND PRIX - RACE", (950, 300, 1600, 340)),
        item("POS.", (1500, 490, 1570, 525)),
        item("DRIVER", (1600, 490, 1720, 525)),
        item("TEAM", (2000, 490, 2100, 525)),
        item("GRID", (2350, 490, 2430, 525)),
        item("STOPS BEST", (2470, 490, 2640, 525)),
        item("TIME", (2730, 490, 2810, 525)),
        item("PTS.", (2990, 490, 3060, 525)),
        item("9", (1500, 570, 1525, 602)),
        item("unreadable", (1650, 570, 1850, 602)),
        item("1:26.614", (2560, 570, 2670, 602)),
        item("+1 Lap", (2740, 570, 2830, 602)),
        item("View Super Licence", (2500, 900, 2830, 940)),
    ]


class NativeDetailCropTests(unittest.TestCase):
    def test_large_photo_replaces_table_at_native_detail_and_remaps_coordinates(self):
        base = detail_pass_tokens()
        geometry = race_ocr._detail_crop_geometry((4000, 1800), base)
        self.assertIsNotNone(geometry)
        (left, top, _, _), _, _ = geometry
        enhanced_global = detail_pass_tokens()[:-1]
        enhanced_global[10] = OcrToken("6", 0.99, 1500, 570, 1525, 602, "Screenshot 1")
        enhanced_global[11] = OcrToken(
            "AI Fernando ALONSO",
            0.99,
            1650,
            570,
            1950,
            602,
            "Screenshot 1",
        )
        enhanced_local = [
            OcrToken(
                item.text,
                item.confidence,
                item.x_min - left,
                item.y_min - top,
                item.x_max - left,
                item.y_max - top,
                item.source,
            )
            for item in enhanced_global[2:]
        ]

        class FakeEngine:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def __call__(self, image):
                self.calls.append(image)
                return ocr_result(base if len(self.calls) == 1 else enhanced_local)

        engine = FakeEngine()
        with patch("race_ocr._engine", return_value=engine):
            tokens = race_ocr.extract_tokens(
                large_detail_image(),
                "Screenshot 1",
                grid_size=22,
            )

        self.assertEqual(len(engine.calls), 2)
        self.assertLess(max(engine.calls[1].size), race_ocr._RAPIDOCR_MAX_SIDE)
        self.assertIn("AI Fernando ALONSO", [item.text for item in tokens])
        self.assertNotIn("unreadable", [item.text for item in tokens])
        self.assertNotIn("View Super Licence", [item.text for item in tokens])
        # The crop's conflicting 6 may not overwrite first-pass position 9.
        position_tokens = [
            item.text
            for item in tokens
            if item.y_center > 540 and item.x_center < 1600
        ]
        self.assertIn("9", position_tokens)
        self.assertNotIn("6", position_tokens)
        remapped = next(item for item in tokens if item.text == "AI Fernando ALONSO")
        self.assertEqual((remapped.x_min, remapped.y_min), (1650, 570))

    def test_small_image_uses_only_the_original_ocr_pass(self):
        image_bytes, base = synthetic_overall("AUSTRALIAN GRAND PRIX - RACE")

        class FakeEngine:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, _image):
                self.calls += 1
                return ocr_result(base)

        engine = FakeEngine()
        with patch("race_ocr._engine", return_value=engine):
            tokens = race_ocr.extract_tokens(
                image_bytes,
                "Screenshot 1",
                grid_size=22,
            )

        self.assertEqual(engine.calls, 1)
        self.assertEqual([item.text for item in tokens], [item.text for item in base])

    def test_large_image_without_a_verified_detail_header_is_not_cropped(self):
        base = [token("unrelated menu", (900, 200, 1200, 240))]

        class FakeEngine:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, _image):
                self.calls += 1
                return ocr_result(base)

        engine = FakeEngine()
        with patch("race_ocr._engine", return_value=engine):
            tokens = race_ocr.extract_tokens(
                large_detail_image(),
                "Screenshot 1",
                grid_size=22,
            )

        self.assertEqual(engine.calls, 1)
        self.assertEqual([item.text for item in tokens], ["unrelated menu"])


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

    def test_detects_race_from_selected_overall_badge_and_detail_heading(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRAND PRIX-RACE",
        )

        self.assertEqual(race_ocr.detect_selected_results_tab(image_bytes, tokens), "R")

    def test_detects_sprint_from_selected_overall_badge_and_detail_heading(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRANDPRIX-SPRINT",
        )

        self.assertEqual(race_ocr.detect_selected_results_tab(image_bytes, tokens), "SR")

    def test_overall_badge_requires_a_selected_red_background(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRAND PRIX-RACE",
            selected=False,
        )

        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_overall_badge_does_not_trust_an_ambiguous_heading(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRAND PRIX",
        )

        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_overall_badge_rejects_conflicting_heading_markers(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRAND PRIX-RACE-SPRINT",
        )

        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_overall_badge_does_not_trust_grand_prix_text_below_detail_header(self):
        image_bytes, tokens = synthetic_overall("TABLE DETAIL")
        tokens.append(
            token("AUSTRALIAN GRAND PRIX-RACE", (20, 130, 390, 150))
        )

        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_overall_badge_does_not_turn_a_weekend_summary_into_a_race(self):
        image_bytes, tokens = synthetic_overall(
            "AUSTRALIAN GRAND PRIX-RACE",
            include_timing_detail=False,
        )

        self.assertIsNone(race_ocr.detect_selected_results_tab(image_bytes, tokens))

    def test_legacy_selected_tab_remains_authoritative_over_the_heading(self):
        image_bytes, tokens = synthetic_tabs("WEEKEND")
        tokens.append(
            token("AUSTRALIAN GRAND PRIX-SPRINT", (12, 48, 260, 60))
        )

        self.assertEqual(
            race_ocr.detect_selected_results_tab(image_bytes, tokens),
            "WEEKEND",
        )

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
