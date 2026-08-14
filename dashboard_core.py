"""Pure data loading, validation, and standings calculations for the dashboard.

This module intentionally has no Streamlit dependency so its behavior can be
tested quickly and reused by other interfaces.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd


REQUIRED_STANDINGS_COLUMNS = {
    "Game",
    "Season",
    "League Name",
    "Round",
    "GP Name",
    "Driver",
    "Team",
    "Finish Pos",
    "Points",
}
CALENDAR_COLUMNS = [
    "League Name",
    "Round",
    "Date",
    "GP Name",
    "Circuit",
    "Status",
    "Time (Lisbon)",
    # Optional protected-Admin identity metadata. Legacy workbooks remain
    # valid because load_calendar_data supplies blank defaults.
    "Game",
    "Season",
    "Has Sprint",
    "League ID",
]
SEASON_TOTAL_MARKERS = {"all", "season total", "final", "season final"}


class WorkbookValidationError(ValueError):
    """Raised when an input workbook cannot safely power the dashboard."""


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [str(column).strip() for column in result.columns]
    return result.loc[:, ~result.columns.str.match(r"^Unnamed:")]


def _read_excel_sheet(source: str | Path | BinaryIO, sheet_name: str) -> pd.DataFrame:
    try:
        return pd.read_excel(source, sheet_name=sheet_name)
    except ValueError as exc:
        raise WorkbookValidationError(f"Required sheet '{sheet_name}' was not found.") from exc
    except Exception as exc:
        raise WorkbookValidationError(f"Could not read sheet '{sheet_name}': {exc}") from exc


def validate_workbook(source: str | Path | BinaryIO) -> list[str]:
    """Validate workbook structure and return non-blocking quality warnings."""
    try:
        workbook = pd.ExcelFile(source)
    except Exception as exc:
        raise WorkbookValidationError(f"Could not open the Excel workbook: {exc}") from exc
    try:
        if "Leagues" not in workbook.sheet_names:
            raise WorkbookValidationError("Required sheet 'Leagues' was not found.")

        warnings: list[str] = []
        if "Calendar" not in workbook.sheet_names:
            warnings.append("Optional sheet 'Calendar' is missing; schedule features will be unavailable.")

        standings = _clean_columns(pd.read_excel(workbook, sheet_name="Leagues"))
    finally:
        workbook.close()
    missing = sorted(REQUIRED_STANDINGS_COLUMNS - set(standings.columns))
    if missing:
        raise WorkbookValidationError(f"Sheet 'Leagues' is missing columns: {', '.join(missing)}")
    # Ignore rows that only belong to auxiliary tables placed beside the
    # standings grid. Partially populated standings rows are still validated.
    result_columns = list(REQUIRED_STANDINGS_COLUMNS)
    standings = standings.loc[standings[result_columns].notna().any(axis=1)].copy()
    if standings.empty:
        raise WorkbookValidationError("Sheet 'Leagues' contains no standings rows.")

    required_text = ["Game", "Season", "League Name", "Round", "GP Name", "Driver", "Team"]
    blank_counts = {
        column: int(standings[column].fillna("").astype(str).str.strip().eq("").sum())
        for column in required_text
    }
    blanks = [f"{column} ({count})" for column, count in blank_counts.items() if count]
    if blanks:
        raise WorkbookValidationError("Blank required values in 'Leagues': " + ", ".join(blanks))

    round_text = standings["Round"].astype(str).str.strip().str.lower()
    invalid_round = pd.to_numeric(standings["Round"], errors="coerce").isna() & ~round_text.isin(SEASON_TOTAL_MARKERS)
    if invalid_round.any():
        raise WorkbookValidationError(f"Sheet 'Leagues' has {int(invalid_round.sum())} invalid Round value(s).")

    for column in ["Finish Pos", "Points"]:
        invalid = pd.to_numeric(standings[column], errors="coerce").isna()
        if invalid.any():
            raise WorkbookValidationError(
                f"Sheet 'Leagues' has {int(invalid.sum())} non-numeric {column} value(s)."
            )

    duplicate_key = ["Game", "Season", "League Name", "Round", "GP Name", "Driver"]
    if "Type" in standings.columns:
        duplicate_key.insert(4, "Type")
    duplicate_count = int(standings.duplicated(duplicate_key, keep=False).sum())
    if duplicate_count:
        warnings.append(
            f"Sheet 'Leagues' contains {duplicate_count} potentially duplicated result row(s)."
        )

    return warnings


def load_standings_data(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Load and normalize the required ``Leagues`` worksheet."""
    df = _clean_columns(_read_excel_sheet(source, "Leagues"))
    missing = sorted(REQUIRED_STANDINGS_COLUMNS - set(df.columns))
    if missing:
        raise WorkbookValidationError(f"Sheet 'Leagues' is missing columns: {', '.join(missing)}")

    for column in ["Game", "Season", "League Name", "Round", "GP Name", "Driver", "Team"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    if "Type" not in df.columns:
        df["Type"] = "R"
    else:
        df["Type"] = df["Type"].fillna("R").astype(str).str.strip().str.upper()
        df.loc[~df["Type"].isin(["R", "SR"]), "Type"] = "R"

    df["SeasonLabel"] = df["Season"].astype(str).str.strip()
    season_num = df["SeasonLabel"].str.extract(r"(\d{4})", expand=False)
    df["SeasonNum"] = pd.to_numeric(season_num, errors="coerce")
    direct_season = pd.to_numeric(df["SeasonLabel"], errors="coerce")
    df.loc[direct_season.notna(), "SeasonNum"] = direct_season[direct_season.notna()]

    round_raw = df["Round"].astype(str).str.strip()
    gp_raw = df["GP Name"].astype(str).str.strip()
    df["IsSeasonFinal"] = (
        gp_raw.str.lower().isin(SEASON_TOTAL_MARKERS)
        | round_raw.str.lower().isin(SEASON_TOTAL_MARKERS)
    )

    df["Round"] = pd.to_numeric(df["Round"], errors="coerce")
    df.loc[df["IsSeasonFinal"] & df["Round"].isna(), "Round"] = 999
    df["Round"] = df["Round"].astype("Int64")
    df["Finish Pos"] = pd.to_numeric(df["Finish Pos"], errors="coerce").astype("Int64")
    df["Points"] = pd.to_numeric(df["Points"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["Round"]).copy()
    df.loc[df["IsSeasonFinal"], "GP Name"] = "Season Final"
    return df


def empty_calendar() -> pd.DataFrame:
    return pd.DataFrame(columns=CALENDAR_COLUMNS)


def _calendar_boolean(value: object, *, column: str = "Has Sprint") -> bool:
    """Parse one workbook boolean without Python's truthy-string coercion."""

    if value is None or pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        if int(value) in {0, 1}:
            return bool(int(value))
    if isinstance(value, (float, np.floating)) and np.isfinite(float(value)):
        if float(value) in {0.0, 1.0}:
            return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "y", "sim", "s", "1"}:
            return True
        if normalized in {"false", "no", "n", "não", "nao", "0", ""}:
            return False
    raise WorkbookValidationError(
        f"Calendar column '{column}' contains an invalid boolean value: {value!r}."
    )


def load_calendar_data(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Load the optional ``Calendar`` worksheet, normalizing missing columns."""
    try:
        df = _clean_columns(pd.read_excel(source, sheet_name="Calendar"))
    except ValueError:
        return empty_calendar()
    except Exception as exc:
        raise WorkbookValidationError(f"Could not read sheet 'Calendar': {exc}") from exc

    if df.empty:
        return empty_calendar()

    result = df[[column for column in CALENDAR_COLUMNS if column in df.columns]].copy()
    defaults = {
        "League Name": "",
        "Round": pd.NA,
        "Date": pd.NaT,
        "GP Name": "",
        "Circuit": "",
        "Status": "",
        "Time (Lisbon)": pd.NA,
        "Game": "",
        "Season": "",
        "Has Sprint": False,
        "League ID": "",
    }
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = default

    for column in ["League Name", "GP Name", "Circuit", "Status", "Game", "Season", "League ID"]:
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["Has Sprint"] = result["Has Sprint"].map(
        lambda value: _calendar_boolean(value, column="Has Sprint")
    )
    result["Round"] = pd.to_numeric(result["Round"], errors="coerce").astype("Int64")
    result["Date"] = pd.to_datetime(result["Date"], errors="coerce")
    result = result[~(result["GP Name"].eq("") & result["Date"].isna())].copy()
    return result.sort_values(["Round", "Date", "GP Name"], na_position="last").reset_index(drop=True)


def find_bundled_excel(base_dir: str | Path = ".") -> str | None:
    base = Path(base_dir)
    candidates = [
        "F1_Standings.xlsx",
        "data/F1_Standings.xlsx",
        "Data/F1_Standings.xlsx",
        "assets/F1_Standings.xlsx",
        "excel/F1_Standings.xlsx",
    ]
    for candidate in candidates:
        path = base / candidate
        if path.exists():
            return str(path)
    excluded = {".venv", ".git", "__pycache__", "venv"}
    for path in base.rglob("*.xlsx"):
        if not any(part in excluded for part in path.parts) and not path.name.startswith("~$"):
            return str(path)
    return None


def effective_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Prefer race-level rows over season-total rows within each league season."""
    if df.empty:
        return df.copy()
    group_columns = [column for column in ["Game", "Season", "League Name"] if column in df.columns]
    if not group_columns:
        group_columns = ["SeasonLabel"] if "SeasonLabel" in df.columns else ["Season"]

    groups = []
    for _, group in df.groupby(group_columns, sort=False, dropna=False):
        groups.append(group[~group["IsSeasonFinal"]] if (~group["IsSeasonFinal"]).any() else group)
    return pd.concat(groups).sort_index() if groups else df.iloc[0:0].copy()


def season_sort_key(season_label: str) -> int:
    text = str(season_label).strip()
    year_match = re.search(r"(\d{4})", text)
    split_match = re.search(r"[Tt]\s*-?\s*(\d+)", text)
    year = int(year_match.group(1)) if year_match else 0
    split = int(split_match.group(1)) if split_match else 0
    return year * 100 + split


def latest_league_slice(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if df.empty:
        return df.copy(), {"Game": "-", "SeasonLabel": "-", "League Name": "-"}
    labels = sorted(df["SeasonLabel"].dropna().unique().tolist(), key=season_sort_key)
    latest_label = labels[-1]
    latest = df[df["SeasonLabel"] == latest_label].copy()
    league = latest["League Name"].mode().iloc[0] if not latest.empty else "-"
    game = latest["Game"].mode().iloc[0] if not latest.empty else "-"
    latest = latest[(latest["League Name"] == league) & (latest["Game"] == game)].copy()
    return latest, {"Game": game, "SeasonLabel": latest_label, "League Name": league}


def standings_table(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    column = "Driver" if entity == "Drivers" else "Team"
    output_columns = ["Pos", column, "Points", "Races", "Wins", "Podiums", "Top5", "AvgFinish", "Consistency", "Pts/Race"]
    if df.empty:
        return pd.DataFrame(columns=output_columns)
    races = df[~df["IsSeasonFinal"]].copy()
    if races.empty:
        return pd.DataFrame(columns=output_columns)

    races["_RaceID"] = races[["Game", "SeasonLabel", "League Name", "Round", "GP Name"]].astype(str).agg("|".join, axis=1)
    totals = races.groupby(column, as_index=False)["Points"].sum()
    main_races = races[races["Type"] == "R"].copy()
    if main_races.empty:
        main_races = races
    stats = main_races.groupby(column, as_index=False).agg(
        Races=("_RaceID", "nunique"),
        Wins=("Finish Pos", lambda values: int((values == 1).sum())),
        Podiums=("Finish Pos", lambda values: int((values <= 3).sum())),
        Top5=("Finish Pos", lambda values: int((values <= 5).sum())),
        AvgFinish=("Finish Pos", lambda values: float(np.nanmean(values.astype(float)))),
        Consistency=("Finish Pos", lambda values: float(np.nanstd(values.astype(float)))),
    )
    result = totals.merge(stats, on=column, how="left")
    for metric in ["Races", "Wins", "Podiums", "Top5"]:
        result[metric] = result[metric].fillna(0).astype(int)
    result["AvgFinish"] = result["AvgFinish"].round(1)
    result["Consistency"] = result["Consistency"].round(2)
    result["Pts/Race"] = (result["Points"] / result["Races"].replace(0, np.nan)).fillna(0).round(2)
    result = result.sort_values(
        ["Points", "Wins", "Podiums", "AvgFinish", column],
        ascending=[False, False, False, True, True],
    )
    result.insert(0, "Pos", range(1, len(result) + 1))
    return result


def event_sort_cols(df: pd.DataFrame, all_time: bool) -> pd.DataFrame:
    result = df.copy()
    if all_time:
        result["_SeasonKey"] = result["SeasonLabel"].map(season_sort_key).astype(int)
        result["EventIdx"] = result["_SeasonKey"] * 1000 + result["Round"].astype(int)
        result["EventLabel"] = (
            result["SeasonLabel"].astype(str) + " • R" + result["Round"].astype(str) + " • " + result["GP Name"].astype(str)
        )
        return result.drop(columns="_SeasonKey")
    result["EventIdx"] = result["Round"].astype(int)
    result["EventLabel"] = "R" + result["Round"].astype(str) + " • " + result["GP Name"].astype(str)
    return result


def cumulative_points_wide(df: pd.DataFrame, entity_col: str, all_time: bool):
    data = event_sort_cols(df, all_time=all_time)
    grouped = data.groupby([entity_col, "EventIdx", "EventLabel"], as_index=False)["Points"].sum()
    grouped = grouped.sort_values(["EventIdx", entity_col])
    grouped["CumPoints"] = grouped.groupby(entity_col)["Points"].cumsum()
    long = grouped[[entity_col, "EventIdx", "EventLabel", "CumPoints"]].copy()
    wide = long.pivot_table(index="EventIdx", columns=entity_col, values="CumPoints", aggfunc="max").sort_index()
    return wide, long


def per_round_positions(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    data = event_sort_cols(df, all_time=False)
    grouped = data.groupby([entity_col, "EventIdx", "EventLabel"], as_index=False)["Points"].sum()
    grouped = grouped.sort_values(["EventIdx", entity_col])
    grouped["CumPoints"] = grouped.groupby(entity_col)["Points"].cumsum()
    result = grouped[[entity_col, "EventIdx", "EventLabel", "CumPoints"]].copy()
    result["Position"] = result.groupby("EventIdx")["CumPoints"].rank(method="min", ascending=False).astype(int)
    result = result.sort_values([entity_col, "EventIdx"])
    result["PrevPos"] = result.groupby(entity_col)["Position"].shift(1)
    result["PosChange"] = result["PrevPos"] - result["Position"]
    return result


def lead_swaps_count(leaders_series: pd.Series) -> int:
    if leaders_series.empty:
        return 0
    return int(max((leaders_series != leaders_series.shift(1)).sum() - 1, 0))


def form_table(df: pd.DataFrame, entity_col: str, n_list=(3, 5)) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    data = df.copy()
    last_round = int(data["Round"].max())
    positions = per_round_positions(data, entity_col=entity_col)
    last_position = positions[positions["EventIdx"] == last_round][[entity_col, "Position", "PosChange"]].copy()
    last_position["PosChange"] = last_position["PosChange"].fillna(0).astype(int)
    rows = []
    for entity, subset in data.groupby(entity_col):
        subset = subset.sort_values(["Round", "GP Name"])
        for count in n_list:
            recent = subset[subset["Round"] > last_round - count]
            main_races = recent[recent["Type"] == "R"]
            rows.append(
                {
                    entity_col: entity,
                    f"Pts L{count}": float(recent["Points"].sum()),
                    f"AvgFin L{count}": float(np.nanmean(main_races["Finish Pos"].astype(float))) if len(main_races) else np.nan,
                }
            )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output = output.groupby(entity_col, as_index=False).agg(
        {column: "first" for column in output.columns if column != entity_col}
    )
    output = output.merge(last_position, on=entity_col, how="left")
    output["Position"] = output["Position"].astype("Int64")
    return output.sort_values(["Position", entity_col], ascending=[True, True])


def season_champions(df: pd.DataFrame, entity_col: str, calendar_df: pd.DataFrame | None = None) -> pd.DataFrame:
    calendar = empty_calendar() if calendar_df is None else calendar_df
    ongoing_seasons: set[str] = set()
    if not calendar.empty:
        upcoming_leagues = calendar[calendar["Status"].astype(str).str.lower() == "upcoming"]["League Name"].dropna().unique()
        for label, league in df[["SeasonLabel", "League Name"]].drop_duplicates().itertuples(index=False, name=None):
            standing_gps = set(df[(df["SeasonLabel"] == label) & (df["League Name"] == league) & (~df["IsSeasonFinal"])]["GP Name"].dropna())
            for upcoming_league in upcoming_leagues:
                calendar_gps = set(calendar[calendar["League Name"] == upcoming_league]["GP Name"].dropna())
                same_league = str(upcoming_league).strip().lower() == str(league).strip().lower()
                if same_league or (calendar_gps and standing_gps and standing_gps.issubset(calendar_gps)):
                    ongoing_seasons.add(label)
                    break

    finished = effective_rows(df[~df["SeasonLabel"].isin(ongoing_seasons)].copy())
    totals = finished.groupby(["SeasonLabel", entity_col], as_index=False)["Points"].sum()
    totals = totals.sort_values(["SeasonLabel", "Points", entity_col], ascending=[True, False, True])
    champions = totals.groupby("SeasonLabel").head(1).rename(columns={entity_col: "Champion"})
    return champions[["SeasonLabel", "Champion", "Points"]].rename(columns={"SeasonLabel": "Season"}).sort_values("Season")


def titles_count(df: pd.DataFrame, entity_col: str, calendar_df: pd.DataFrame | None = None):
    champions = season_champions(df, entity_col, calendar_df=calendar_df)
    titles = champions.groupby("Champion", as_index=False).agg(Titles=("Season", "nunique"))
    titles = titles.sort_values(["Titles", "Champion"], ascending=[False, True]).reset_index(drop=True)
    titles.insert(0, "Rank", range(1, len(titles) + 1))
    return titles, champions


def circuits_top3(df: pd.DataFrame) -> pd.DataFrame:
    wins_only = df[(~df["IsSeasonFinal"]) & (df["Finish Pos"] == 1) & (df["Type"] == "R")].copy()
    if wins_only.empty:
        return pd.DataFrame(columns=["GP Name", "Top 1", "Top 2", "Top 3"])
    wins = wins_only.groupby(["GP Name", "Driver"], as_index=False).size().rename(columns={"size": "Wins"})
    wins = wins.sort_values(["GP Name", "Wins", "Driver"], ascending=[True, False, True])
    top = wins.groupby("GP Name").head(3).copy()
    top["Label"] = top["Driver"] + " (" + top["Wins"].astype(int).astype(str) + ")"
    top["Rank"] = top.groupby("GP Name").cumcount() + 1
    output = top.pivot(index="GP Name", columns="Rank", values="Label").reset_index()
    return output.rename(columns={1: "Top 1", 2: "Top 2", 3: "Top 3"}).fillna("-").sort_values("GP Name")


def championship_tension(df: pd.DataFrame, entity_col: str) -> tuple[dict, pd.DataFrame, pd.Series]:
    empty_metrics = {"lead_swaps": 0, "last_gap": np.nan, "last_top3_spread": np.nan}
    if df.empty:
        return empty_metrics, pd.DataFrame(), pd.Series(dtype="object")
    positions = per_round_positions(df, entity_col=entity_col)
    if positions.empty:
        return empty_metrics, pd.DataFrame(), pd.Series(dtype="object")
    leaders = positions.sort_values(["EventIdx", "Position", entity_col]).groupby("EventIdx", as_index=False).first().set_index("EventIdx")[entity_col]
    rows = []
    for event, subset in positions.groupby("EventIdx"):
        top = subset.sort_values("Position").head(3)
        p1 = top[top["Position"] == 1]["CumPoints"]
        p2 = top[top["Position"] == 2]["CumPoints"]
        rows.append(
            {
                "EventIdx": event,
                "GapP1P2": float(p1.iloc[0] - p2.iloc[0]) if len(p1) and len(p2) else np.nan,
                "Top3Spread": float(top["CumPoints"].max() - top["CumPoints"].min()) if len(top) >= 3 else np.nan,
            }
        )
    tension = pd.DataFrame(rows).sort_values("EventIdx")
    metrics = {
        "lead_swaps": lead_swaps_count(leaders),
        "last_gap": float(tension["GapP1P2"].dropna().iloc[-1]) if not tension["GapP1P2"].dropna().empty else np.nan,
        "last_top3_spread": float(tension["Top3Spread"].dropna().iloc[-1]) if not tension["Top3Spread"].dropna().empty else np.nan,
    }
    return metrics, tension, leaders


def position_delta_table(df: pd.DataFrame, entity_col: str, n_momentum: int = 3) -> pd.DataFrame:
    positions = per_round_positions(df, entity_col=entity_col)
    if positions.empty:
        return pd.DataFrame()
    last_event = positions["EventIdx"].max()
    latest = positions[positions["EventIdx"] == last_event][[entity_col, "Position", "PrevPos", "PosChange"]].copy()
    latest["PosChange"] = latest["PosChange"].fillna(0).astype(int)
    recent = positions.sort_values("EventIdx").groupby(entity_col).tail(n_momentum)
    momentum_column = f"MomentumL{n_momentum}"
    momentum = recent.groupby(entity_col, as_index=False)["PosChange"].sum().rename(columns={"PosChange": momentum_column})
    output = latest.merge(momentum, on=entity_col, how="left")
    output[momentum_column] = output[momentum_column].fillna(0).astype(int)
    output = output.rename(columns={"Position": "CurrentPos", "PosChange": "Delta"})
    return output.sort_values(["Delta", momentum_column, "CurrentPos"], ascending=[False, False, True]).reset_index(drop=True)
