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
from statistics import median
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
FASTEST_LAP_RE = re.compile(r"^(\d):([0-5]\d)[.,](\d{3})$")
RACE_TOTAL_RE = re.compile(r"^(\d{1,3}):([0-5]\d)[.,](\d{3})$")
RACE_GAP_MINUTES_RE = re.compile(r"^\+(\d{1,2}):([0-5]\d)[.,](\d{3})$")
RACE_GAP_SECONDS_RE = re.compile(r"^\+(\d{1,3})[.,](\d{3})$")
RACE_LAPS_RE = re.compile(r"^\+(\d{1,2})\s*LAPS?$", re.IGNORECASE)
RACE_STATUS_RE = re.compile(r"^(?:DNF|DNS|DSQ|RET)$", re.IGNORECASE)
MINIMUM_TIMING_CONFIDENCE = 0.72


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


@dataclass(frozen=True)
class TimingColumns:
    """Credible BEST/TIME column bounds inferred from one OCR header row."""

    fastest_lap_x: float
    time_x: float
    fastest_lap_min_x: float
    split_x: float
    time_max_x: float
    header_y: float


@dataclass(frozen=True)
class TimingMatch:
    """One timing field staged for automatic use or explicit review."""

    value: str | None
    suggestion: str | None
    confidence: float
    issues: tuple[str, ...] = ()


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
    time: str | None = None
    suggested_time: str | None = None
    time_confidence: float = 0.0
    time_issues: list[str] = field(default_factory=list)
    fastest_lap: str | None = None
    suggested_fastest_lap: str | None = None
    fastest_lap_confidence: float = 0.0
    fastest_lap_issues: list[str] = field(default_factory=list)
    timing_expected: bool = False


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
    """Return a fail-closed position-only scoring map for one event type.

    Existing same-session history is authoritative. A first Sprint may use the
    fixed project scale only after completed Race history independently matches
    the companion project scale exactly.
    """
    season_column = "SeasonLabel" if "SeasonLabel" in standings.columns else "Season"
    selected = standings[
        standings["Game"].astype(str).eq(str(game))
        & standings[season_column].astype(str).eq(str(season))
        & standings["League Name"].astype(str).eq(str(league))
    ].copy()
    if "IsSeasonFinal" in selected.columns:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    selected_type = str(event_type).upper()
    event_types = (
        selected["Type"].fillna("R").astype(str).str.upper()
        if "Type" in selected.columns
        else pd.Series("R", index=selected.index)
    )
    selected_event = selected[event_types.eq(selected_type)].copy()
    if selected_event.empty:
        if selected_type != "SR":
            raise ScoringProfileError(
                f"No {selected_type} results exist to verify this championship's scoring."
            )

        # A championship's first Sprint has no same-session history to infer
        # from. Allow the project's fixed Sprint scale only when the completed
        # Race history independently proves that this championship uses the
        # matching verified project rules. Existing but incomplete Sprint data
        # deliberately does not take this path and therefore still fails closed.
        race_history = selected[event_types.eq("R")].copy()
        if race_history.empty:
            raise ScoringProfileError(
                "No Sprint results or completed Race scoring exist to verify this championship's Sprint points."
            )
        try:
            race_profile = _scoring_profile_from_history(race_history, grid_size)
        except ScoringProfileError as exc:
            raise ScoringProfileError(
                "No Sprint results exist, and the completed Race scoring is not complete enough to verify the first Sprint."
            ) from exc
        if race_profile != scoring_profile_from_project_rules("R", grid_size):
            raise ScoringProfileError(
                "No Sprint results exist, and this championship's Race scoring does not match the verified project rules."
            )
        return scoring_profile_from_project_rules("SR", grid_size)

    return _scoring_profile_from_history(selected_event, grid_size)


def _scoring_profile_from_history(
    selected: pd.DataFrame,
    grid_size: int,
) -> dict[int, float]:
    """Infer one complete, internally consistent position-only points map."""
    selected = selected.copy()
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


def _compact_token_text(value: object) -> str:
    return "".join(normalize_name(value).split())


def _looks_like_best_header(value: object) -> bool:
    compact = _compact_token_text(value)
    return (
        "best" in compact
        or "dest" in compact
        or compact.endswith("eest")
        or SequenceMatcher(None, compact, "stopsbest").ratio() >= 0.67
    )


def _looks_like_points_header(value: object) -> bool:
    compact = _compact_token_text(value)
    return compact in {"pts", "pis", "points"} or SequenceMatcher(None, compact, "pts").ratio() >= 0.66


def _looks_like_time_header(value: object) -> bool:
    compact = _compact_token_text(value)
    return "time" in compact or SequenceMatcher(None, compact, "time").ratio() >= 0.67


def detect_timing_columns(tokens: Sequence[OcrToken]) -> TimingColumns | None:
    """Return credible BEST/TIME column bounds, or ``None`` for summary tables.

    A header is accepted only when its tokens form the expected result-table
    sequence (GRID, BEST, TIME, PTS). This deliberately excludes weekend
    summary screens whose narrow numeric columns are SR, R, and PTS.
    """
    for cluster in _line_clusters(tokens):
        ordered = sorted(cluster, key=lambda item: item.x_center)
        compact_line = " ".join(_compact_token_text(token.text) for token in ordered)
        if "grid" not in compact_line or not ("driver" in compact_line or "pos" in compact_line):
            continue

        grid_tokens = [token for token in ordered if "grid" in _compact_token_text(token.text)]
        best_tokens = [token for token in ordered if _looks_like_best_header(token.text)]
        points_tokens = [token for token in ordered if _looks_like_points_header(token.text)]
        if not grid_tokens or not best_tokens or not points_tokens:
            continue

        for grid_token in grid_tokens:
            for best_token in best_tokens:
                points_after_best = [token for token in points_tokens if token.x_min > best_token.x_max]
                if grid_token.x_max >= best_token.x_max or not points_after_best:
                    continue
                points_token = min(points_after_best, key=lambda item: item.x_min)
                between = [
                    token
                    for token in ordered
                    if token.x_min >= best_token.x_max and token.x_max <= points_token.x_min
                ]
                explicit_time = [token for token in between if _looks_like_time_header(token.text)]
                if explicit_time:
                    time_token = min(explicit_time, key=lambda item: item.x_center)
                elif len(between) == 1:
                    # Some photographs turn TIME into unrelated letters. It is
                    # still credible when it is the sole header between a
                    # BEST-like token and a PTS-like token in a GRID header.
                    time_token = between[0]
                else:
                    continue

                best_width = max(best_token.x_max - best_token.x_min, 1.0)
                fastest_x = best_token.x_max - min(6.0, best_width * 0.1)
                time_x = time_token.x_center
                if not (grid_token.x_max < fastest_x < time_x < points_token.x_min):
                    continue
                spacing = time_x - fastest_x
                if spacing < 8.0:
                    continue
                return TimingColumns(
                    fastest_lap_x=fastest_x,
                    time_x=time_x,
                    fastest_lap_min_x=max(grid_token.x_max, fastest_x - spacing * 0.8),
                    split_x=(fastest_x + time_x) / 2,
                    time_max_x=(time_x + points_token.x_min) / 2,
                    header_y=sum(token.y_center for token in cluster) / len(cluster),
                )
    return None


@dataclass(frozen=True)
class _TimingCandidate:
    value: str
    confidence: float
    inferred: bool


def _canonical_fastest_lap(raw_value: object) -> tuple[str, bool] | None:
    compact = re.sub(r"\s+", "", str(raw_value or "")).upper()
    if compact in {"N/A", "NA", "NOTIME"}:
        return "N/A", False
    match = FASTEST_LAP_RE.fullmatch(compact)
    if match:
        return f"{match.group(1)}:{match.group(2)}.{match.group(3)}", False

    repair_patterns = (
        re.compile(r"^(\d)([0-5]\d)[.,](\d{3})$"),
        re.compile(r"^(\d)[.,]([0-5]\d)[.,](\d{3})$"),
        re.compile(r"^(\d):([0-5]\d)(\d{3})$"),
        re.compile(r"^(\d)([0-5]\d)(\d{3})$"),
    )
    for pattern in repair_patterns:
        match = pattern.fullmatch(compact)
        if match:
            return f"{match.group(1)}:{match.group(2)}.{match.group(3)}", True
    return None


def normalize_fastest_lap(value: object) -> str | None:
    """Normalize an explicitly reviewed fastest-lap value.

    OCR-only punctuation repairs remain suggestions and are rejected here;
    the reviewer must enter a complete canonical value such as ``1:34.632``.
    """
    parsed = _canonical_fastest_lap(value)
    return parsed[0] if parsed is not None and not parsed[1] else None


def _canonical_race_time(raw_value: object) -> tuple[str, bool] | None:
    compact = re.sub(r"\s+", "", str(raw_value or "")).upper()
    for pattern, formatter in (
        (RACE_GAP_MINUTES_RE, lambda item: f"+{item.group(1)}:{item.group(2)}.{item.group(3)}"),
        (RACE_GAP_SECONDS_RE, lambda item: f"+{int(item.group(1))}.{item.group(2)}"),
        (RACE_LAPS_RE, lambda item: f"+{int(item.group(1))} {'Lap' if int(item.group(1)) == 1 else 'Laps'}"),
        (RACE_STATUS_RE, lambda item: item.group(0).upper()),
    ):
        match = pattern.fullmatch(compact)
        if match:
            return formatter(match), False
    match = RACE_TOTAL_RE.fullmatch(compact)
    if match and int(match.group(1)) >= 10:
        return f"{int(match.group(1))}:{match.group(2)}.{match.group(3)}", False

    # OCR repairs are suggestions only. They are never silently accepted,
    # even at high model confidence.
    match = re.fullmatch(r"(\d{1,3}):([0-5]\d)(\d{3})", compact)
    if match and int(match.group(1)) >= 10:
        return f"{int(match.group(1))}:{match.group(2)}.{match.group(3)}", True
    match = re.fullmatch(r"\+(\d{1,3})(\d{3})", compact)
    if match:
        leading = match.group(1)
        if int(leading) <= 59:
            return f"+{int(leading)}.{match.group(2)}", True
        if len(leading) == 3 and int(leading[1:]) <= 59:
            return f"+{int(leading[0])}:{leading[1:]}.{match.group(2)}", True
    match = re.fullmatch(r"[.,]?(\d{1,2})[.,](\d{3})", compact)
    if match and int(match.group(1)) <= 59:
        return f"+{int(match.group(1))}.{match.group(2)}", True
    match = re.fullmatch(r"(\d{1,2})(\d{3})", compact)
    if match and int(match.group(1)) <= 59:
        return f"+{int(match.group(1))}.{match.group(2)}", True
    match = re.fullmatch(r"(\d)([0-5]\d)(\d{3})", compact)
    if match:
        return f"+{int(match.group(1))}:{match.group(2)}.{match.group(3)}", True
    match = re.fullmatch(r"\+(\d{1,2})L[A-Z0-9]{0,3}", compact)
    if match:
        laps = int(match.group(1))
        return f"+{laps} {'Lap' if laps == 1 else 'Laps'}", True
    return None


def normalize_race_time(value: object) -> str | None:
    """Normalize an explicitly reviewed total, interval, lap gap, or status."""
    parsed = _canonical_race_time(value)
    return parsed[0] if parsed is not None and not parsed[1] else None


def _timing_match(
    tokens: Sequence[OcrToken],
    parser,
    *,
    label: str,
) -> TimingMatch:
    candidates: list[_TimingCandidate] = []
    for token in tokens:
        parsed = parser(token.text)
        if parsed is not None:
            value, inferred = parsed
            candidates.append(_TimingCandidate(value, float(token.confidence), inferred))
    if len(tokens) > 1:
        joined = "".join(token.text.strip() for token in sorted(tokens, key=lambda item: item.x_min))
        parsed = parser(joined)
        if parsed is not None:
            value, inferred = parsed
            candidates.append(
                _TimingCandidate(
                    value,
                    sum(float(token.confidence) for token in tokens) / len(tokens),
                    inferred,
                )
            )

    best_by_value: dict[str, _TimingCandidate] = {}
    for candidate in candidates:
        current = best_by_value.get(candidate.value)
        if current is None or (current.inferred, -current.confidence) > (candidate.inferred, -candidate.confidence):
            best_by_value[candidate.value] = candidate
    candidates = sorted(best_by_value.values(), key=lambda item: (item.inferred, -item.confidence, item.value))
    if not candidates:
        return TimingMatch(None, None, 0.0, (f"{label} was not recognized.",))
    selected = candidates[0]
    confidence = round(selected.confidence, 3)
    if len(candidates) > 1:
        return TimingMatch(
            None,
            selected.value,
            confidence,
            (f"Conflicting {label.casefold()} values were read; confirm it manually.",),
        )
    if selected.inferred:
        return TimingMatch(
            None,
            selected.value,
            confidence,
            (f"OCR punctuation in the {label.casefold()} was repaired; confirm it manually.",),
        )
    if selected.confidence < MINIMUM_TIMING_CONFIDENCE:
        return TimingMatch(
            None,
            selected.value,
            confidence,
            (f"Low OCR confidence; confirm the {label.casefold()}.",),
        )
    return TimingMatch(selected.value, selected.value, confidence)


def _extract_timing_from_cluster(
    cluster: Sequence[OcrToken],
    columns: TimingColumns,
) -> tuple[TimingMatch, TimingMatch]:
    fastest_tokens = [
        token
        for token in cluster
        if columns.fastest_lap_min_x <= token.x_center < columns.split_x
    ]
    time_tokens = [
        token
        for token in cluster
        if columns.split_x <= token.x_center <= columns.time_max_x
    ]
    return (
        _timing_match(fastest_tokens, _canonical_fastest_lap, label="Fastest lap"),
        _timing_match(time_tokens, _canonical_race_time, label="Result time"),
    )


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


def _cluster_y_center(cluster: Sequence[OcrToken]) -> float:
    return sum(token.y_center for token in cluster) / len(cluster)


def _is_detail_result_cluster(cluster: Sequence[OcrToken], columns: TimingColumns) -> bool:
    if not cluster or _cluster_y_center(cluster) <= columns.header_y:
        return False
    return any(
        columns.fastest_lap_min_x <= token.x_center <= columns.time_max_x
        for token in cluster
    )


def _recover_ordered_positions(
    clusters: Sequence[Sequence[OcrToken]],
    *,
    grid_size: int,
    columns: TimingColumns,
) -> dict[int, int]:
    """Infer only positions forced by contiguous detail rows and anchors."""
    slots: list[tuple[int, float, int | None]] = []
    for cluster_index, cluster in enumerate(clusters):
        if _is_detail_result_cluster(cluster, columns):
            slots.append(
                (
                    cluster_index,
                    _cluster_y_center(cluster),
                    _position_from_line(cluster, grid_size),
                )
            )
    anchors = [(slot_index, position) for slot_index, (_, _, position) in enumerate(slots) if position is not None]
    if len(slots) < 3 or not anchors:
        return {}

    gaps = [slots[index + 1][1] - slots[index][1] for index in range(len(slots) - 1)]
    positive_gaps = sorted(gap for gap in gaps if gap > 0)
    if not positive_gaps:
        return {}
    lower_half = positive_gaps[: max(1, (len(positive_gaps) + 1) // 2)]
    normal_gap = median(lower_half)
    minimum_gap = normal_gap * 0.45
    maximum_gap = normal_gap * 1.65

    used_positions = {position for _, position in anchors}
    recovered: dict[int, int] = {}
    boundaries = [(-1, 0), *anchors, (len(slots), grid_size + 1)]
    for (left_index, left_position), (right_index, right_position) in zip(boundaries, boundaries[1:]):
        if right_position <= left_position:
            continue
        # Equal index/position deltas make every intervening position
        # mathematically forced; any missing or extra OCR row breaks this.
        if right_index - left_index != right_position - left_position:
            continue
        real_start = max(left_index, 0)
        real_end = min(right_index, len(slots) - 1)
        segment_gaps = [
            slots[index + 1][1] - slots[index][1]
            for index in range(real_start, real_end)
        ]
        if any(gap < minimum_gap or gap > maximum_gap for gap in segment_gaps):
            continue
        proposed = {
            slots[slot_index][0]: left_position + (slot_index - left_index)
            for slot_index in range(left_index + 1, right_index)
            if slots[slot_index][2] is None
        }
        if not proposed or set(proposed.values()).intersection(used_positions):
            continue
        recovered.update(proposed)
        used_positions.update(proposed.values())

    # A pair of aligned anchors also establishes a local position/row offset.
    # This safely recovers the first row of a later screenshot page (for
    # example, position 9 immediately above recognized positions 10 and 11)
    # without assuming that every screenshot starts at position 1.
    for (left_index, left_position), (right_index, right_position) in zip(anchors, anchors[1:]):
        if right_position - left_position != right_index - left_index or right_position <= left_position:
            continue
        if any(
            gap < minimum_gap or gap > maximum_gap
            for gap in gaps[left_index:right_index]
        ):
            continue
        offset = left_position - left_index
        for direction, start_index in ((-1, left_index - 1), (1, right_index + 1)):
            slot_index = start_index
            while 0 <= slot_index < len(slots):
                neighbor_index = slot_index - direction
                gap = abs(slots[slot_index][1] - slots[neighbor_index][1])
                if gap < minimum_gap or gap > maximum_gap:
                    break
                expected_position = slot_index + offset
                if expected_position < 1 or expected_position > grid_size:
                    break
                recognized = slots[slot_index][2]
                if recognized is not None:
                    if recognized != expected_position:
                        break
                else:
                    cluster_index = slots[slot_index][0]
                    previous = recovered.get(cluster_index)
                    if previous is not None:
                        if previous != expected_position:
                            break
                    elif expected_position in used_positions:
                        break
                    else:
                        recovered[cluster_index] = expected_position
                        used_positions.add(expected_position)
                slot_index += direction
    return recovered


def extract_results_from_tokens(
    tokens: Sequence[OcrToken],
    roster: Sequence[DriverEntry],
    *,
    source: str,
) -> list[ExtractedResult]:
    """Turn positioned OCR tokens into reviewable result-row candidates."""
    rows: list[ExtractedResult] = []
    clusters = _line_clusters(tokens)
    timing_columns = detect_timing_columns(tokens)
    recovered_positions = (
        _recover_ordered_positions(clusters, grid_size=len(roster), columns=timing_columns)
        if timing_columns is not None
        else {}
    )
    for cluster_index, cluster in enumerate(clusters):
        # Once a credible detail header establishes the result grid, labels
        # above it (selected Results tabs, the Grand Prix title, countdowns,
        # and other menu chrome) cannot be finishing rows.  Excluding that
        # region also prevents a misspelled tab label from becoming a fuzzy
        # controlled-roster suggestion and contaminating the review.
        if (
            timing_columns is not None
            and _cluster_y_center(cluster) <= timing_columns.header_y
        ):
            continue
        line_text = " ".join(token.text.strip() for token in cluster if token.text.strip())
        if not line_text:
            continue
        recognized_position = _position_from_line(cluster, len(roster))
        position = recognized_position or recovered_positions.get(cluster_index)
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
        elif recognized_position is None:
            issues.append("Finishing position was inferred from contiguous detail rows; confirm it.")
        if match.needs_review:
            issues.append(match.reason)
        if timing_columns is not None:
            fastest_lap, race_time = _extract_timing_from_cluster(cluster, timing_columns)
        else:
            fastest_lap = TimingMatch(None, None, 0.0)
            race_time = TimingMatch(None, None, 0.0)
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
                time=race_time.value,
                suggested_time=race_time.suggestion,
                time_confidence=race_time.confidence,
                time_issues=list(race_time.issues),
                fastest_lap=fastest_lap.value,
                suggested_fastest_lap=fastest_lap.suggestion,
                fastest_lap_confidence=fastest_lap.confidence,
                fastest_lap_issues=list(fastest_lap.issues),
                timing_expected=timing_columns is not None,
            )
        )
    return rows


def _merge_timing_field(
    target: ExtractedResult,
    incoming: ExtractedResult,
    *,
    value_attribute: str,
    suggestion_attribute: str,
    confidence_attribute: str,
    issues_attribute: str,
    label: str,
) -> None:
    target_value = getattr(target, value_attribute)
    incoming_value = getattr(incoming, value_attribute)
    target_suggestion = getattr(target, suggestion_attribute)
    incoming_suggestion = getattr(incoming, suggestion_attribute)
    target_candidate = target_value or target_suggestion
    incoming_candidate = incoming_value or incoming_suggestion
    target_confidence = float(getattr(target, confidence_attribute))
    incoming_confidence = float(getattr(incoming, confidence_attribute))
    combined_issues = sorted(
        set(getattr(target, issues_attribute) + getattr(incoming, issues_attribute))
    )

    if target_candidate is None and incoming_candidate is not None:
        setattr(target, value_attribute, incoming_value)
        setattr(target, suggestion_attribute, incoming_suggestion)
        setattr(target, confidence_attribute, incoming_confidence)
    elif target_candidate is not None and incoming_candidate is not None:
        if target_candidate == incoming_candidate:
            if incoming_value is not None and target_value is None:
                setattr(target, value_attribute, incoming_value)
            setattr(target, suggestion_attribute, target_candidate)
            setattr(target, confidence_attribute, max(target_confidence, incoming_confidence))
        else:
            preferred = incoming_candidate if incoming_confidence > target_confidence else target_candidate
            setattr(target, value_attribute, None)
            setattr(target, suggestion_attribute, preferred)
            setattr(target, confidence_attribute, max(target_confidence, incoming_confidence))
            combined_issues.append(f"Conflicting {label} values were read; confirm it manually.")
    setattr(target, issues_attribute, sorted(set(combined_issues)))


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
            _merge_timing_field(
                duplicate,
                result,
                value_attribute="time",
                suggestion_attribute="suggested_time",
                confidence_attribute="time_confidence",
                issues_attribute="time_issues",
                label="result time",
            )
            _merge_timing_field(
                duplicate,
                result,
                value_attribute="fastest_lap",
                suggestion_attribute="suggested_fastest_lap",
                confidence_attribute="fastest_lap_confidence",
                issues_attribute="fastest_lap_issues",
                label="fastest-lap",
            )
            duplicate.timing_expected = duplicate.timing_expected or result.timing_expected
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
                time=result.time,
                suggested_time=result.suggested_time,
                time_confidence=result.time_confidence,
                time_issues=list(result.time_issues),
                fastest_lap=result.fastest_lap,
                suggested_fastest_lap=result.suggested_fastest_lap,
                fastest_lap_confidence=result.fastest_lap_confidence,
                fastest_lap_issues=list(result.fastest_lap_issues),
                timing_expected=result.timing_expected,
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
    timing_expected = any(row.timing_expected for row in extracted)
    rows: list[dict] = []
    for row in extracted:
        review_row = {
            "Position": row.position,
            "Driver": row.driver or "",
            "OCR text": row.raw_text,
            "Suggested driver": row.suggested_driver or "",
            "Confidence": float(row.confidence),
            "Seen in": ", ".join(row.sources),
            "OCR notes": " ".join(row.issues),
        }
        if timing_expected:
            review_row.update(
                {
                    "Time": row.time or "",
                    "Suggested Time": row.suggested_time or "",
                    "Time Confidence": float(row.time_confidence),
                    "Time Notes": " ".join(row.time_issues),
                    "Fastest Lap": row.fastest_lap or "",
                    "Suggested Fastest Lap": row.suggested_fastest_lap or "",
                    "Fastest Lap Confidence": float(row.fastest_lap_confidence),
                    "Fastest Lap Notes": " ".join(row.fastest_lap_issues),
                    "Timing Expected": True,
                }
            )
        rows.append(review_row)
    present_positions = {row.position for row in extracted if row.position is not None}
    for position in range(1, grid_size + 1):
        if position not in present_positions:
            review_row = {
                    "Position": position,
                    "Driver": "",
                    "OCR text": "",
                    "Suggested driver": "",
                    "Confidence": 0.0,
                    "Seen in": "",
                    "OCR notes": "Missing from OCR; select the driver.",
                }
            if timing_expected:
                review_row.update(
                    {
                        "Time": "",
                        "Suggested Time": "",
                        "Time Confidence": 0.0,
                        "Time Notes": "Result time was not recognized.",
                        "Fastest Lap": "",
                        "Suggested Fastest Lap": "",
                        "Fastest Lap Confidence": 0.0,
                        "Fastest Lap Notes": "Fastest lap was not recognized.",
                        "Timing Expected": True,
                    }
                )
            rows.append(review_row)
    return sorted(rows, key=lambda row: (row["Position"] is None, row["Position"] or 999, row["OCR text"]))


def validate_review_rows(
    review_rows: Iterable[Mapping[str, object]],
    roster: Sequence[DriverEntry],
    scoring_profile: Mapping[int, float],
) -> ReviewValidation:
    """Validate reviewed rows and add canonical team/derived points."""
    review_rows = list(review_rows)
    roster_map = {entry.driver: entry.team for entry in roster}
    expected_positions = set(range(1, len(roster) + 1))
    rows: list[dict] = []
    blockers: list[str] = []
    timing_keys = {
        "Time",
        "Suggested Time",
        "Fastest Lap",
        "Suggested Fastest Lap",
        "Timing Expected",
    }
    timing_mode = any(timing_keys.intersection(raw_row) for raw_row in review_rows)
    for index, raw_row in enumerate(review_rows, start=1):
        position_value = pd.to_numeric(raw_row.get("Position"), errors="coerce")
        position = int(position_value) if pd.notna(position_value) and float(position_value).is_integer() else None
        driver = str(raw_row.get("Driver") or "").strip()
        if position is None or position not in expected_positions:
            blockers.append(f"Review row {index} needs a valid position from 1 to {len(roster)}.")
        if driver not in roster_map:
            blockers.append(f"Review row {index} needs a driver from the controlled championship roster.")
        validated_row = {
                "Position": position,
                "Driver": driver,
                "Team": roster_map.get(driver, ""),
                "Points": float(scoring_profile.get(position, 0)) if position is not None else 0.0,
            }
        if timing_mode:
            raw_time = str(raw_row.get("Time") or "").strip()
            raw_fastest_lap = str(raw_row.get("Fastest Lap") or "").strip()
            time_value = normalize_race_time(raw_time) if raw_time else None
            fastest_lap_value = normalize_fastest_lap(raw_fastest_lap) if raw_fastest_lap else None
            timing_expected_value = raw_row.get("Timing Expected", False)
            if isinstance(timing_expected_value, str):
                timing_expected = timing_expected_value.strip().casefold() in {"1", "true", "yes"}
            else:
                timing_expected = not pd.isna(timing_expected_value) and bool(timing_expected_value)
            timing_expected = timing_expected or (
                "Time" in raw_row and "Fastest Lap" in raw_row
            ) or bool(
                str(raw_row.get("Suggested Time") or "").strip()
                or str(raw_row.get("Suggested Fastest Lap") or "").strip()
            )

            if raw_time and time_value is None:
                blockers.append(
                    f"Review row {index} has an invalid result time. Use a total time, +gap, +laps, or DNF/DNS/DSQ/RET."
                )
            elif timing_expected and time_value is None:
                blockers.append(f"Review row {index} needs a confirmed result time.")
            if raw_fastest_lap and fastest_lap_value is None:
                blockers.append(
                    f"Review row {index} has an invalid fastest lap. Use M:SS.mmm or N/A."
                )
            elif timing_expected and fastest_lap_value is None:
                blockers.append(f"Review row {index} needs a confirmed fastest lap.")
            validated_row.update(
                {
                    "Time": time_value or "",
                    "Fastest Lap": fastest_lap_value or "",
                }
            )
        rows.append(validated_row)

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
