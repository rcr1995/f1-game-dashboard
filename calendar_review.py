"""Check uploaded Race and Sprint results against the calendar they will be published with."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import dashboard_core as core
from puskas_html import get_calendar_for_league, _calendar_race_standings


@dataclass(frozen=True)
class Finding:
    game: str
    season: str
    league: str
    round_number: int
    event: str
    problem: str
    uploaded: str
    expected: str
    # The same affected drivers remain an existing issue if rows move in Excel.
    drivers: tuple[str, ...]
    rows: tuple[int, ...] = field(compare=False)


def _round_findings(identity, number, rows, slots):
    def finding(event, problem, affected, uploaded="", expected=""):
        return Finding(*identity, int(number), event, problem, uploaded, expected,
                       tuple(sorted(affected["Driver"])), tuple(int(i) + 2 for i in affected.index))

    if len(slots) != 1 or not str(slots.iloc[0]["GP Name"]).strip():
        problem = "missing_round" if slots.empty else "ambiguous_round"
        for event, group in rows.groupby("Type"):
            yield finding(event, problem, group, ", ".join(sorted(set(group["GP Name"]))))
        return
    slot = slots.iloc[0]
    expected = slot["GP Name"]
    for (event, uploaded), group in rows.groupby(["Type", "GP Name"]):
        if uploaded.casefold() != expected.casefold():
            yield finding(event, "name", group, uploaded, expected)

    races = rows[rows["Type"].eq("R")]
    if slot["Status"].casefold() != "done":
        if not races.empty:
            yield finding("R", "status", races, expected=expected)
        return
    if races.empty:
        yield finding("R", "missing_race", races, expected=expected)
        return
    # A wrong GP name already explains a missing winner. Check the classification
    # independently once all Race rows actually belong to this calendar event.
    if not races["GP Name"].str.casefold().eq(expected.casefold()).all():
        return
    winners = races[races["Finish Pos"].eq(1)]
    if winners.empty:
        yield finding("R", "missing_winner", races, expected=expected)
    elif len(winners) > 1:
        yield finding("R", "multiple_winners", winners, expected=expected)
    elif _calendar_race_standings(races, number, expected).empty:
        yield finding("R", "invalid_classification", races, expected=expected)


def inspect_calendar(content: bytes):
    results = core.load_standings_data(BytesIO(content))
    calendar = core.load_calendar_data(BytesIO(content))
    results = results.loc[~results["IsSeasonFinal"]]
    identities = ["Game", "SeasonLabel", "League Name"]
    groups = {}
    league_counts = {}
    for key, group in results.groupby([results[col].str.casefold() for col in identities], sort=False):
        groups[key] = (tuple(group.iloc[0][identities]), group)
        league_counts[key[2]] = league_counts.get(key[2], 0) + 1
    # A completed calendar can outlive its last result row in an upload.
    empty = results.iloc[:0]
    for game, season, league in calendar[["Game", "Season", "League Name"]].drop_duplicates().itertuples(index=False, name=None):
        if (game and season) or league.casefold() not in league_counts:
            key = (game.casefold(), season.casefold(), league.casefold())
            groups.setdefault(key, ((game, season, league), empty))
    findings = []
    unchecked = []
    for identity, group in groups.values():
        meta = dict(zip(identities, identity))
        schedule = get_calendar_for_league(calendar, meta)
        legacy = not schedule.empty and schedule["League ID"].eq("").all()
        if schedule.empty or (legacy and league_counts.get(identity[2].casefold(), 0) > 1):
            unchecked.append(" · ".join(part for part in identity if part))
            continue
        # An upcoming round with no results needs no review. A Done round does,
        # even when the upload removed all results for that particular round.
        done = schedule.loc[schedule["Status"].str.casefold().eq("done"), "Round"].dropna()
        for number in sorted(set(group["Round"]) | set(done)):
            findings.extend(_round_findings(identity, number, group[group["Round"].eq(number)],
                                            schedule[schedule["Round"].eq(number)]))
    return findings, unchecked


def review_calendar(previous: bytes, candidate: bytes) -> dict:
    old, previously_unchecked = inspect_calendar(previous)
    current, unchecked = inspect_calendar(candidate)
    known = set(old)
    return {"new": [issue for issue in current if issue not in known],
            "existing": [issue for issue in current if issue in known],
            "unchecked": unchecked,
            "new_unchecked": sorted(set(unchecked) - set(previously_unchecked))}


def needs_acknowledgement(review: dict) -> bool:
    return bool(review["new"] or review["new_unchecked"])

