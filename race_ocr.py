"""Lazy, optional offline OCR adapter for race-result screenshots."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from typing import Sequence
import warnings

from race_import import OcrToken


class OcrUnavailableError(RuntimeError):
    """Raised when the optional local OCR dependencies are unavailable."""


class InvalidScreenshotError(ValueError):
    """Raised before OCR when an upload is not a bounded raster image."""


MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}


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
