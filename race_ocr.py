"""Lazy, optional offline OCR adapter for race-result screenshots."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from io import BytesIO
import re
from typing import Literal, Sequence
import warnings

from race_import import OcrToken


class OcrUnavailableError(RuntimeError):
    """Raised when the optional local OCR dependencies are unavailable."""


class InvalidScreenshotError(ValueError):
    """Raised before OCR when an upload is not a bounded raster image."""


MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}

ResultsTab = Literal["R", "SR", "WEEKEND"]


@dataclass(frozen=True)
class _TabLabel:
    """One OCR-backed results-tab label and its image bounds."""

    kind: ResultsTab
    x_min: float
    y_min: float
    x_max: float
    y_max: float


_TAB_WORDS: dict[str, ResultsTab] = {
    "RACE": "R",
    "SPRINT": "SR",
    "WEEKEND": "WEEKEND",
}
_MIN_SELECTED_RED_FRACTION = 0.12
_MIN_RED_FRACTION_MARGIN = 0.08
_MIN_TAB_OCR_CONFIDENCE = 0.55


def _words(value: object) -> set[str]:
    return set(re.findall(r"[A-Z]+", str(value or "").upper()))


def _session_word_kind(value: object) -> ResultsTab | None:
    words = _words(value)
    matches = {_TAB_WORDS[word] for word in words if word in _TAB_WORDS}
    if len(matches) == 1:
        return next(iter(matches))
    if matches:
        return None

    scored: list[tuple[float, ResultsTab]] = []
    for word in words:
        if word.startswith("RESULT") or len(word) < 4:
            continue
        for expected, kind in _TAB_WORDS.items():
            scored.append((SequenceMatcher(None, word, expected).ratio(), kind))
    scored.sort(reverse=True, key=lambda item: item[0])
    if not scored or scored[0][0] < 0.66:
        return None
    runner_up = max(
        (score for score, kind in scored[1:] if kind != scored[0][1]),
        default=0.0,
    )
    return scored[0][1] if scored[0][0] - runner_up >= 0.14 else None


def _has_results_word(value: object) -> bool:
    return any(word.startswith("RESULT") for word in _words(value))


def _union_label(kind: ResultsTab, *tokens: OcrToken) -> _TabLabel:
    return _TabLabel(
        kind,
        min(token.x_min for token in tokens),
        min(token.y_min for token in tokens),
        max(token.x_max for token in tokens),
        max(token.y_max for token in tokens),
    )


def _same_tab_label(left: OcrToken, right: OcrToken) -> bool:
    """Return whether two OCR boxes plausibly form one horizontal tab label."""
    if left.source != right.source or right.x_center <= left.x_center:
        return False
    vertical_overlap = min(left.y_max, right.y_max) - max(left.y_min, right.y_min)
    minimum_height = min(left.height, right.height)
    if vertical_overlap < minimum_height * 0.45:
        return False
    gap = right.x_min - left.x_max
    return -minimum_height * 0.4 <= gap <= max(left.height, right.height) * 2.5


def _tab_labels(tokens: Sequence[OcrToken]) -> list[_TabLabel]:
    """Find full or split ``RESULTS (SESSION)`` OCR labels."""
    labels: list[_TabLabel] = []
    result_tokens = [
        token
        for token in tokens
        if token.confidence >= _MIN_TAB_OCR_CONFIDENCE
        and _has_results_word(token.text)
        and _session_word_kind(token.text) is None
    ]
    for token in tokens:
        if token.confidence < _MIN_TAB_OCR_CONFIDENCE:
            continue
        kind = _session_word_kind(token.text)
        if kind is None:
            continue
        if _has_results_word(token.text):
            labels.append(_union_label(kind, token))
            continue
        for result_token in result_tokens:
            if (
                min(result_token.confidence, token.confidence)
                >= _MIN_TAB_OCR_CONFIDENCE
                and _same_tab_label(result_token, token)
            ):
                labels.append(_union_label(kind, result_token, token))
    return labels


def _red_fraction(image, label: _TabLabel) -> float:
    """Measure selected-tab red in and immediately around an OCR text box."""
    width, height = image.size
    label_width = max(label.x_max - label.x_min, 1.0)
    label_height = max(label.y_max - label.y_min, 1.0)
    pad_x = max(2.0, label_width * 0.06)
    pad_y = max(2.0, label_height * 0.35)
    left = max(0, int(label.x_min - pad_x))
    top = max(0, int(label.y_min - pad_y))
    right = min(width, int(label.x_max + pad_x + 0.999))
    bottom = min(height, int(label.y_max + pad_y + 0.999))
    if right <= left or bottom <= top:
        return 0.0

    crop = image.crop((left, top, right, bottom))
    if hasattr(crop, "get_flattened_data"):
        pixels = list(crop.get_flattened_data())
    else:
        pixels = list(crop.getdata())
    if not pixels:
        return 0.0
    red_pixels = sum(
        1
        for red, green, blue in pixels
        if red >= 70
        and red - green >= 28
        and red - blue >= 12
        and red >= green * 1.25
        and red >= blue * 1.08
    )
    return red_pixels / len(pixels)


def detect_selected_results_tab(
    image_bytes: bytes,
    tokens: Sequence[OcrToken],
) -> ResultsTab | None:
    """Identify the uniquely red ``RESULTS`` tab, or fail closed.

    The event title is intentionally ignored: the game can retain ``- RACE``
    while the Sprint results tab is selected, and ``- SPRINT`` while the
    Weekend summary tab is selected. OCR supplies the tab-label bounds; image
    pixels decide which of those labels has the red selected background.
    """
    validate_image_upload(image_bytes)
    labels = _tab_labels(tokens)
    if not labels:
        return None

    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as opened:
        image = opened.convert("RGB")
        scores: dict[ResultsTab, float] = {}
        for label in labels:
            scores[label.kind] = max(scores.get(label.kind, 0.0), _red_fraction(image, label))

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    selected_kind, selected_score = ranked[0]
    if selected_score < _MIN_SELECTED_RED_FRACTION:
        return None
    if len(ranked) > 1:
        runner_up_score = ranked[1][1]
        required_margin = max(_MIN_RED_FRACTION_MARGIN, selected_score * 0.30)
        if selected_score - runner_up_score < required_margin:
            return None
    return selected_kind


def validate_image_upload(image_bytes: bytes, source: str = "Screenshot") -> None:
    """Reject spoofed, empty, oversized, or decompression-bomb uploads."""
    if not image_bytes:
        raise InvalidScreenshotError(f"{source} is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidScreenshotError(f"{source} exceeds the 12 MB image limit.")
    try:
        from PIL import Image, UnidentifiedImageError

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = str(image.format or "").upper()
                width, height = image.size
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise InvalidScreenshotError(f"{source} must be PNG, JPEG, or WebP.")
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise InvalidScreenshotError(
                        f"{source} exceeds the 25-megapixel safety limit."
                    )
                image.verify()
            # ``verify`` checks container structure without decoding pixels and
            # Pillow's JPEG verifier can therefore accept a truncated stream.
            # Reopen and fully decode after the bounded format/dimension checks.
            # Valid phone JPEGs with vendor metadata after EOI remain decodable.
            with Image.open(BytesIO(image_bytes)) as decoded:
                decoded.load()
    except InvalidScreenshotError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidScreenshotError(
            f"{source} is not a valid PNG, JPEG, or WebP image."
        ) from exc


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr import LangRec, RapidOCR
    except ImportError as exc:
        raise OcrUnavailableError(
            "OCR is not installed. Install the importer dependencies, then restart the app."
        ) from exc
    return RapidOCR(params={"Rec.lang_type": LangRec.EN})


def extract_tokens(image_bytes: bytes, source: str) -> Sequence[OcrToken]:
    """Extract positioned text while retaining per-line model confidence."""
    validate_image_upload(image_bytes, source)
    try:
        result = _engine()(image_bytes)
    except OcrUnavailableError:
        raise
    except Exception as exc:
        raise RuntimeError(f"OCR could not read {source}: {exc}") from exc

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or texts is None or scores is None:
        return []

    tokens: list[OcrToken] = []
    for box, text, confidence in zip(boxes, texts, scores):
        points = list(box)
        x_values = [float(point[0]) for point in points]
        y_values = [float(point[1]) for point in points]
        tokens.append(
            OcrToken(
                text=str(text),
                confidence=float(confidence),
                x_min=min(x_values),
                y_min=min(y_values),
                x_max=max(x_values),
                y_max=max(y_values),
                source=source,
            )
        )
    return tokens
