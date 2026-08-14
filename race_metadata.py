"""Mixed-version-safe construction of immutable race event metadata.

Streamlit can hot-reload an Admin page while retaining an older imported
``race_workbook.RaceMetadata`` class. This small factory avoids positional
signature crashes during that transition and keeps the managed League ID on
the compatibility instance.
"""

from __future__ import annotations

import inspect
import importlib
import math
import threading
from collections.abc import Mapping


REQUIRED_API_VERSION = 2
_RELOAD_LOCK = threading.Lock()


class RaceMetadataCompatibilityError(RuntimeError):
    """The managed metadata/writer module could not be made coherent."""


def _managed_api_available(module: object) -> bool:
    try:
        parameters = inspect.signature(
            getattr(module, "RaceMetadata")
        ).parameters
    except (AttributeError, TypeError, ValueError):
        return False
    return (
        getattr(module, "RACE_METADATA_API_VERSION", 0)
        >= REQUIRED_API_VERSION
        and "league_id" in parameters
    )


def ensure_current_race_workbook(module: object | None = None) -> object:
    """Reload one cached pre-managed writer or fail closed."""

    if module is None:
        import race_workbook as module
    if _managed_api_available(module):
        return module
    with _RELOAD_LOCK:
        if _managed_api_available(module):
            return module
        try:
            refreshed = importlib.reload(module)  # type: ignore[arg-type]
        except Exception as exc:
            raise RaceMetadataCompatibilityError(
                "The managed race writer could not be refreshed safely."
            ) from exc
        if not _managed_api_available(refreshed):
            raise RaceMetadataCompatibilityError(
                "The loaded race writer does not support managed League IDs."
            )
        return refreshed


def optional_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if type(value).__name__ in {"NAType", "NaTType"}:
        return ""
    return str(value).strip()


def make_race_metadata(
    *,
    game: object,
    season: object,
    league: object,
    round_number: object,
    event_type: object,
    gp_name: object,
    league_id: object = "",
    metadata_class: object | None = None,
) -> object:
    """Construct current or cached legacy RaceMetadata without guessing."""

    if metadata_class is None:
        race_workbook = ensure_current_race_workbook()
        metadata_class = race_workbook.RaceMetadata
    values = {
        "game": optional_text(game),
        "season": optional_text(season),
        "league": optional_text(league),
        "round_number": int(round_number),
        "event_type": optional_text(event_type),
        "gp_name": optional_text(gp_name),
        "league_id": optional_text(league_id),
    }
    parameters = inspect.signature(metadata_class).parameters
    required = {
        "game",
        "season",
        "league",
        "round_number",
        "event_type",
        "gp_name",
    }
    if not required.issubset(parameters):
        raise TypeError("The loaded race metadata type has an unsupported signature.")
    supported = {
        key: value for key, value in values.items() if key in parameters
    }
    metadata = metadata_class(**supported)  # type: ignore[operator]
    if "league_id" not in parameters:
        try:
            object.__setattr__(metadata, "league_id", values["league_id"])
        except (AttributeError, TypeError) as exc:
            raise TypeError(
                "The loaded race metadata type cannot preserve the managed League ID."
            ) from exc
    return metadata


def from_event_mapping(
    event: Mapping[str, object], *, metadata_class: object | None = None
) -> object:
    return make_race_metadata(
        game=event.get("game"),
        season=event.get("season"),
        league=event.get("league"),
        round_number=event.get("round", 0),
        event_type=event.get("type"),
        gp_name=event.get("gp"),
        league_id=event.get("league_id"),
        metadata_class=metadata_class,
    )
