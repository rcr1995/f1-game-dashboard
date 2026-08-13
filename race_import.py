"""Pure race-result import logic.

The Streamlit UI and OCR adapter intentionally depend on this module, rather
than the other way around, so matching, scoring, and reconciliation remain
fully testable without loading Streamlit or an OCR model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from typing import Iterable, Mapping, Sequence

import pandas as pd


RACE_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
SPRINT_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

# These are deliberately narrow, championship-specific OCR aliases. Targets
# are ignored unless they exist in the selected championship roster.
DEFAULT_DRIVER_ALIASES = {
    "tomas rodri 21": "TomasRodri21",
    "tomas rodri2l": "TomasRodri21",
    "tomas rodri2i": "TomasRodri21",
    "poli ngua": "Polingua",
    "fata cuida": "Fatacuida",
}

POSITION_RE = re.compile(r"^(?:p\s*)?(\d{1,2})(?:st|nd|rd|th)?[.):\-]?$", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")


class RaceImportError(ValueError):
    """Base class for a staged race import error."""


class RosterError(RaceImportError):
    """Raised when a controlled roster cannot be derived safely."""


class ScoringProfileError(RaceImportError):
    """Raised when the selected championship has no position-only scoring profile."""


@dataclass(frozen=True)
class DriverEntry:
    driver: str
    team: str


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    source: str

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2

    @property
    def height(self) -> float:
        return max(self.y_max - self.y_min, 1.0)


@dataclass(frozen=True)
class DriverMatch:
    raw_text: str
    canonical: str | None
    suggestion: str | None
    score: float
    runner_up_score: float
    method: str
    needs_review: bool
    reason: str = ""


@dataclass
class ExtractedResult:
    position: int | None
    raw_text: str
    driver: str | None
    suggested_driver: str | None
    confidence: float
    sources: list[str] = field(default_factory=list)
    match_method: str = "unresolved"
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewValidation:
    rows: list[dict]
    blockers: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.blockers


def normalize_name(value: object) -> str:
    """Normalize OCR/player text while retaining useful token boundaries."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(TOKEN_RE.findall(text.casefold()))


def _phrase_similarity(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack):
        return 1.0

    needle_tokens = needle.split()
    haystack_tokens = haystack.split()
    candidates = [haystack]
    for width in range(max(1, len(needle_tokens) - 1), min(len(haystack_tokens), len(needle_tokens) + 1) + 1):
        candidates.extend(" ".join(haystack_tokens[start : start + width]) for start in range(len(haystack_tokens) - width + 1))
    return max(SequenceMatcher(None, needle, candidate).ratio() for candidate in candidates)


def match_driver(
    raw_text: str,
    roster: Sequence[DriverEntry] | Sequence[str],
    *,
    ocr_confidence: float = 1.0,
    aliases: Mapping[str, str] | None = None,
    fuzzy_threshold: float = 0.84,
    fuzzy_margin: float = 0.08,
    minimum_ocr_confidence: float = 0.72,
) -> DriverMatch:
    """Match OCR text only against the selected championship roster.

    Exact canonical names and controlled aliases may be accepted when OCR
    confidence is healthy. Fuzzy matches are suggestions that require an
    explicit user selection in the review screen.
    """
    roster_names = [entry.driver if isinstance(entry, DriverEntry) else str(entry) for entry in roster]
    normalized_roster = {normalize_name(name): name for name in roster_names}
    raw_normalized = normalize_name(raw_text)
    low_confidence = float(ocr_confidence) < minimum_ocr_confidence

    exact = [name for normalized, name in normalized_roster.items() if _phrase_similarity(normalized, raw_normalized) == 1.0]
    if len(exact) == 1:
        canonical = exact[0]
        return DriverMatch(
            raw_text,
            None if low_confidence else canonical,
            canonical,
            1.0,
            0.0,
            "exact",
            low_confidence,
            "Low OCR confidence; confirm the driver." if low_confidence else "",
        )

    controlled_aliases = dict(DEFAULT_DRIVER_ALIASES)
    if aliases:
        controlled_aliases.update(aliases)
    alias_hits: list[str] = []
    for alias, target in controlled_aliases.items():
        if target not in roster_names:
            continue
        normalized_alias = normalize_name(alias)
        if _phrase_similarity(normalized_alias, raw_normalized) == 1.0:
            alias_hits.append(target)
    alias_hits = sorted(set(alias_hits))
    if len(alias_hits) == 1:
        canonical = alias_hits[0]
        return DriverMatch(
            raw_text,
            None if low_confidence else canonical,
            canonical,
            1.0,
            0.0,
            "alias",
            low_confidence,
            "Low OCR confidence; confirm the driver." if low_confidence else "",
        )

    scored = sorted(
        ((_phrase_similarity(normalized, raw_normalized), name) for normalized, name in normalized_roster.items()),
        reverse=True,
    )
    best_score, best_name = scored[0] if scored else (0.0, None)
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    clear_match = best_name is not None and best_score >= fuzzy_threshold and best_score - runner_up >= fuzzy_margin
    if clear_match:
        return DriverMatch(
            raw_text,
            None,
            best_name,
            best_score,
            runner_up,
            "fuzzy",
            True,
            "OCR name is an imperfect match; confirm the suggested driver.",
        )
    return DriverMatch(
        raw_text,
        None,
        best_name if best_score >= 0.55 else None,
        best_score,
        runner_up,
        "unresolved",
        True,
        "Driver name is ambiguous or was not recognized.",
    )


def derive_championship_roster(
    standings: pd.DataFrame,
    *,
    game: str,
    season: str,
    league: str,
) -> list[DriverEntry]:
    """Use the latest complete main race as the active controlled roster."""
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    selected = standings[
        standings["Game"].astype(str).eq(str(game))
        & standings[season_column].astype(str).eq(str(season))
        & standings["League Name"].astype(str).eq(str(league))
    ].copy()
    if "IsSeasonFinal" in selected.columns:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    if "Type" in selected.columns:
        selected = selected[selected["Type"].fillna("R").astype(str).str.upper().eq("R")]
    if selected.empty:
        raise RosterError("No completed main-race results are available for this championship.")

    group_columns = ["Round", "GP Name"]
    candidates: list[tuple[int, int, pd.DataFrame]] = []
    for (round_value, _), event in selected.groupby(group_columns, dropna=False, sort=False):
        clean = event.dropna(subset=["Driver", "Team", "Finish Pos"]).copy()
        positions = pd.to_numeric(clean["Finish Pos"], errors="coerce").dropna().astype(int)
        unique_drivers = clean["Driver"].astype(str).str.strip().nunique()
        if len(clean) and unique_drivers == len(clean) and positions.nunique() == len(clean) and set(positions) == set(range(1, len(clean) + 1)):
            candidates.append((len(clean), int(round_value), clean))
    if not candidates:
        raise RosterError("No complete main-race grid could be found for this championship.")

    maximum_grid = max(size for size, _, _ in candidates)
    _, _, latest = max((item for item in candidates if item[0] == maximum_grid), key=lambda item: item[1])
    latest = latest.sort_values("Finish Pos")
    entries = [DriverEntry(str(row.Driver).strip(), str(row.Team).strip()) for row in latest.itertuples(index=False)]
    if len({normalize_name(entry.driver) for entry in entries}) != len(entries):
        raise RosterError("The latest complete race contains duplicate driver names.")
    return entries


def infer_scoring_profile(
    standings: pd.DataFrame,
    *,
    game: str,
    season: str,
    league: str,
    event_type: str,
    grid_size: int,
) -> dict[int, float]:
    """Infer a verified position-only scoring map from the selected season."""
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    selected = standings[
        standings["Game"].astype(str).eq(str(game))
        & standings[season_column].astype(str).eq(str(season))
        & standings["League Name"].astype(str).eq(str(league))
    ].copy()
    if "IsSeasonFinal" in selected.columns:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    selected_type = str(event_type).upper()
    if "Type" in selected.columns:
        selected = selected[selected["Type"].fillna("R").astype(str).str.upper().eq(selected_type)]
    if selected.empty:
        raise ScoringProfileError(f"No {selected_type} results exist to verify this championship's scoring.")

    selected["_Position"] = pd.to_numeric(selected["Finish Pos"], errors="coerce")
    selected["_Points"] = pd.to_numeric(selected["Points"], errors="coerce")
    selected = selected.dropna(subset=["_Position", "_Points"])
    profile: dict[int, float] = {}
    inconsistent: list[int] = []
    for position in range(1, grid_size + 1):
        values = selected.loc[selected["_Position"].eq(position), "_Points"].astype(float).unique().tolist()
        if len(values) == 1:
            profile[position] = float(values[0])
        elif len(values) > 1:
            inconsistent.append(position)
    if inconsistent:
        joined = ", ".join(str(position) for position in inconsistent)
        raise ScoringProfileError(f"Points are not determined by position alone at position(s): {joined}.")
    missing = [position for position in range(1, grid_size + 1) if position not in profile]
    if missing:
        raise ScoringProfileError("The workbook does not contain enough results to verify every finishing position.")
    return profile


def scoring_profile_from_project_rules(event_type: str, grid_size: int) -> dict[int, float]:
    """Return the project's verified current F1 scales, including zeroes."""
    base = SPRINT_POINTS if str(event_type).upper() == "SR" else RACE_POINTS
    return {position: float(base.get(position, 0)) for position in range(1, grid_size + 1)}


def _line_clusters(tokens: Sequence[OcrToken]) -> list[list[OcrToken]]:
    clusters: list[list[OcrToken]] = []
    for token in sorted(tokens, key=lambda item: (item.y_center, item.x_min)):
        best_index = None
        best_distance = float("inf")
        for index, cluster in enumerate(clusters):
            center = sum(item.y_center for item in cluster) / len(cluster)
            height = max(sum(item.height for item in cluster) / len(cluster), token.height)
            distance = abs(token.y_center - center)
            if distance <= height * 0.65 and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None:
            clusters.append([token])
        else:
            clusters[best_index].append(token)
    return [sorted(cluster, key=lambda item: item.x_min) for cluster in clusters]


def _position_from_line(tokens: Sequence[OcrToken], grid_size: int) -> int | None:
    if not tokens:
        return None
    left = min(token.x_min for token in tokens)
    right = max(token.x_max for token in tokens)
    cutoff = left + max(right - left, 1) * 0.28
    for token in tokens:
        if token.x_center > cutoff and token is not tokens[0]:
            continue
        match = POSITION_RE.match(token.text.strip())
        if match and 1 <= int(match.group(1)) <= grid_size:
            return int(match.group(1))
    leading = re.match(r"^\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s|[.):\-])", " ".join(token.text for token in tokens), re.IGNORECASE)
    if leading and 1 <= int(leading.group(1)) <= grid_size:
        return int(leading.group(1))
    return None


def extract_results_from_tokens(
    tokens: Sequence[OcrToken],
    roster: Sequence[DriverEntry],
    *,
    source: str,
) -> list[ExtractedResult]:
    """Turn positioned OCR tokens into reviewable result-row candidates."""
    rows: list[ExtractedResult] = []
    for cluster in _line_clusters(tokens):
        line_text = " ".join(token.text.strip() for token in cluster if token.text.strip())
        if not line_text:
            continue
        position = _position_from_line(cluster, len(roster))
        line_words = set(normalize_name(line_text).split())
        if position is None and "driver" in line_words and ({"pos", "team"} & line_words):
            continue
        match = match_driver(line_text, roster, ocr_confidence=sum(token.confidence for token in cluster) / len(cluster))
        # Ignore obvious headings/noise. Keep a line whenever it has a valid
        # position or at least a plausible controlled-roster suggestion.
        if position is None and match.suggestion is None:
            continue
        issues: list[str] = []
        if position is None:
            issues.append("Finishing position was not recognized.")
        if match.needs_review:
            issues.append(match.reason)
        rows.append(
            ExtractedResult(
                position=position,
                raw_text=line_text,
                driver=match.canonical,
                suggested_driver=match.suggestion,
                confidence=round(sum(token.confidence for token in cluster) / len(cluster), 3),
                sources=[source],
                match_method=match.method,
                issues=issues,
            )
        )
    return rows


def merge_screenshot_results(result_sets: Sequence[Sequence[ExtractedResult]]) -> list[ExtractedResult]:
    """Merge exact overlap and surface every conflicting duplicate."""
    merged: list[ExtractedResult] = []
    for result in (item for result_set in result_sets for item in result_set):
        identity = result.driver or result.suggested_driver
        duplicate = next(
            (
                existing
                for existing in merged
                if existing.position == result.position
                and (existing.driver or existing.suggested_driver) == identity
                and identity is not None
            ),
            None,
        )
        if duplicate is not None:
            duplicate.sources = sorted(set(duplicate.sources + result.sources))
            if result.confidence > duplicate.confidence:
                duplicate.raw_text = result.raw_text
                duplicate.confidence = result.confidence
                duplicate.driver = result.driver
                duplicate.suggested_driver = result.suggested_driver
                duplicate.match_method = result.match_method
            duplicate.issues = sorted(set(duplicate.issues + result.issues))
            continue
        merged.append(
            ExtractedResult(
                position=result.position,
                raw_text=result.raw_text,
                driver=result.driver,
                suggested_driver=result.suggested_driver,
                confidence=result.confidence,
                sources=list(result.sources),
                match_method=result.match_method,
                issues=list(result.issues),
            )
        )

    for index, row in enumerate(merged):
        identity = row.driver or row.suggested_driver
        for other_index, other in enumerate(merged):
            if index == other_index:
                continue
            other_identity = other.driver or other.suggested_driver
            if identity and other_identity == identity and row.position != other.position:
                row.issues.append("Conflicting positions were read for this driver.")
            if row.position is not None and other.position == row.position and identity != other_identity:
                row.issues.append("Conflicting drivers were read for this position.")
        row.issues = sorted(set(row.issues))
    return sorted(merged, key=lambda row: (row.position is None, row.position or 999, row.raw_text))


def build_review_rows(extracted: Sequence[ExtractedResult], grid_size: int) -> list[dict]:
    """Add placeholders for OCR omissions so every position is reviewable."""
    rows = [
        {
            "Position": row.position,
            "Driver": row.driver or "",
            "OCR text": row.raw_text,
            "Suggested driver": row.suggested_driver or "",
            "Confidence": float(row.confidence),
            "Seen in": ", ".join(row.sources),
            "OCR notes": " ".join(row.issues),
        }
        for row in extracted
    ]
    present_positions = {row.position for row in extracted if row.position is not None}
    for position in range(1, grid_size + 1):
        if position not in present_positions:
            rows.append(
                {
                    "Position": position,
                    "Driver": "",
                    "OCR text": "",
                    "Suggested driver": "",
                    "Confidence": 0.0,
                    "Seen in": "",
                    "OCR notes": "Missing from OCR; select the driver.",
                }
            )
    return sorted(rows, key=lambda row: (row["Position"] is None, row["Position"] or 999, row["OCR text"]))


def validate_review_rows(
    review_rows: Iterable[Mapping[str, object]],
    roster: Sequence[DriverEntry],
    scoring_profile: Mapping[int, float],
) -> ReviewValidation:
    """Validate reviewed rows and add canonical team/derived points."""
    roster_map = {entry.driver: entry.team for entry in roster}
    expected_positions = set(range(1, len(roster) + 1))
    rows: list[dict] = []
    blockers: list[str] = []
    for index, raw_row in enumerate(review_rows, start=1):
        position_value = pd.to_numeric(raw_row.get("Position"), errors="coerce")
        position = int(position_value) if pd.notna(position_value) and float(position_value).is_integer() else None
        driver = str(raw_row.get("Driver") or "").strip()
        if position is None or position not in expected_positions:
            blockers.append(f"Review row {index} needs a valid position from 1 to {len(roster)}.")
        if driver not in roster_map:
            blockers.append(f"Review row {index} needs a driver from the controlled championship roster.")
        rows.append(
            {
                "Position": position,
                "Driver": driver,
                "Team": roster_map.get(driver, ""),
                "Points": float(scoring_profile.get(position, 0)) if position is not None else 0.0,
            }
        )

    positions = [row["Position"] for row in rows if row["Position"] is not None]
    drivers = [row["Driver"] for row in rows if row["Driver"]]
    duplicate_positions = sorted({position for position in positions if positions.count(position) > 1})
    duplicate_drivers = sorted({driver for driver in drivers if drivers.count(driver) > 1})
    if duplicate_positions:
        blockers.append("Duplicate finishing position(s): " + ", ".join(map(str, duplicate_positions)) + ".")
    if duplicate_drivers:
        blockers.append("Duplicate driver(s): " + ", ".join(duplicate_drivers) + ".")
    missing_positions = sorted(expected_positions - set(positions))
    missing_drivers = sorted(set(roster_map) - set(drivers))
    if missing_positions:
        blockers.append("Missing finishing position(s): " + ", ".join(map(str, missing_positions)) + ".")
    if missing_drivers:
        blockers.append("Missing roster driver(s): " + ", ".join(missing_drivers) + ".")
    if len(rows) != len(roster):
        blockers.append(f"A complete result must contain exactly {len(roster)} rows; found {len(rows)}.")
    return ReviewValidation(rows, list(dict.fromkeys(blockers)))


def review_digest(rows: Iterable[Mapping[str, object]], context: Mapping[str, object]) -> str:
    payload = {
        "context": dict(context),
        "rows": [dict(row) for row in rows],
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
