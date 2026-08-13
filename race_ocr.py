"""Lazy, optional offline OCR adapter for race-result screenshots."""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from race_import import OcrToken


class OcrUnavailableError(RuntimeError):
    """Raised when the optional local OCR dependencies are unavailable."""


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr import LangRec, RapidOCR
    except ImportError as exc:
        raise OcrUnavailableError(
            "Local OCR is not installed. Install requirements-import.txt in your local environment, then restart the app."
        ) from exc
    return RapidOCR(params={"Rec.lang_type": LangRec.EN})


def extract_tokens(image_bytes: bytes, source: str) -> Sequence[OcrToken]:
    """Extract positioned text while retaining per-line model confidence."""
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

