"""Streamlit review workflow for protected local and hosted race imports."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

import pandas as pd
import streamlit as st

import admin_auth
import dashboard_core as core
import league_config as league_cfg
import league_runtime
import race_github as ghstore
import race_import as ri
import race_metadata
import race_ocr
import race_workbook as rw
import secure_image_upload


class HostedPublisher(Protocol):
    def __call__(
        self,
        metadata: rw.RaceMetadata,
        rows: list[dict],
        scoring_profile: dict[int, float],
        expected_source_version: str,
        approved: bool,
    ) -> object: ...


_TEXT = {
    "en": {
        "tab": "📥 Import event",
        "title": "Import one event",
        "intro": "Upload 2 to 4 PlayStation screenshots from one Race or Sprint, review every result field, then approve one safe workbook update.",
        "local": "This protected tool never writes during extraction or review. Direct Excel editing remains available as a fallback.",
        "championship": "Championship",
        "round": "Round",
        "gp": "Grand Prix",
        "custom_gp": "Grand Prix name",
        "event_type": "Session",
        "race": "Race",
        "sprint": "Sprint",
        "roster": "Controlled roster",
        "scoring": "Verified scoring",
        "screenshots": "Event result screenshots",
        "screenshots_help": "Upload 2 to 4 screenshots from one selected Race or Sprint results tab, with repeated rows between adjacent images. Do not mix events or use the Weekend summary.",
        "needs_two": "Upload between 2 and 4 screenshots from this event only.",
        "extract": "Extract standings",
        "manual_review": "Start blank review",
        "manual_help": "OCR is optional. Remove all attached screenshots to start a blank controlled review.",
        "review": "Review and correct",
        "review_help": "Review every driver, Time, and Fastest Lap. Only confident readings are prefilled; points are calculated from position.",
        "final": "Result preview",
        "ready": "All positions and roster drivers are valid. The workbook has not been changed.",
        "blockers": "Resolve these items before approval",
        "approve": "I reviewed every row and approve updating the local Excel workbook.",
        "commit": "Update workbook",
        "changed": "The workbook changed since extraction. Re-extract before approving.",
        "stale": "Event details or screenshots changed. Extract again to create a matching review.",
        "existing": "This race or sprint already exists in the workbook.",
        "safety": "What happens on approval",
        "success": "Event imported safely",
        "ocr_none": "OCR found no standings rows. Remove the screenshots and use a blank review, or try clearer screenshots.",
        "hosted_intro": "Upload 2 to 4 PlayStation screenshots from one Race or Sprint, review every result field, then publish one verified event.",
        "hosted_safety": "You are in the private updater. Screenshots are processed for this review and are never saved to GitHub.",
        "hosted_approve": "I reviewed every row and approve publishing these event results.",
        "hosted_commit": "Publish event results",
        "hosted_ready": "All positions and roster drivers are valid. Nothing has been published yet.",
        "hosted_success": "Saved to GitHub. The public dashboard is refreshing now.",
        "open_dashboard": "Open public dashboard",
        "commit_link": "View GitHub commit",
        "github_auth": "Publishing credentials need attention. No data was changed.",
        "github_conflict": "The workbook changed while you reviewed. Reload it and review this event again.",
        "github_unavailable": "GitHub could not confirm the update. No automatic retry was made.",
        "writer_unavailable": "The managed race writer could not be refreshed safely. No data was changed.",
        "ocr_details": "OCR details and warnings",
        "view_screenshots": "View screenshots ({count})",
        "publishing": "Publishing the approved event…",
        "publish_validate": "Validating the latest workbook and the complete review",
        "publish_commit": "Saving one protected GitHub commit",
        "time_help": "Exact result-screen value, for example 82:50.787, +0.946, +1 Lap, or DNF.",
        "fastest_lap_help": "Exact BEST value, for example 1:33.122. Use N/A only when the result screen has no value.",
        "timing_required": "Every row needs a confirmed Time and Fastest Lap before publication.",
        "one_event": "One upload set = one event. On Sprint weekends, publish Sprint and Race separately.",
        "event_details": "Expected event details",
        "event_details_help": "These values are selected automatically from the active championship and Calendar. Expand only if you need to correct them.",
        "defaults_uncertain": "The workbook could not identify one expected event safely. Check these editable details before uploading.",
        "auto_selected": "Pre-selected: {season} · {league} · Round {round} · {gp} · {session}{date}",
        "detected_session": "The screenshots show {session}; the Session filter was updated automatically.",
    },
    "pt": {
        "tab": "📥 Importar evento",
        "title": "Importar um evento",
        "intro": "Carrega 2 a 4 capturas da PlayStation de uma única Corrida ou Sprint, revê todos os campos e só depois aprova uma atualização segura do Excel.",
        "local": "Esta ferramenta protegida não escreve durante a extração ou revisão. A edição direta no Excel continua disponível como alternativa.",
        "championship": "Campeonato",
        "round": "Ronda",
        "gp": "Grande Prémio",
        "custom_gp": "Nome do Grande Prémio",
        "event_type": "Sessão",
        "race": "Corrida",
        "sprint": "Sprint",
        "roster": "Grelha controlada",
        "scoring": "Pontuação verificada",
        "screenshots": "Capturas dos resultados",
        "screenshots_help": "Carrega 2 a 4 capturas de um único separador de resultados Corrida ou Sprint, com linhas repetidas entre imagens adjacentes. Não mistures eventos nem uses o resumo Weekend.",
        "needs_two": "Carrega entre 2 e 4 capturas apenas deste evento.",
        "extract": "Extrair classificação",
        "manual_review": "Iniciar revisão vazia",
        "manual_help": "O OCR é opcional. Remove todas as capturas para iniciar uma revisão vazia controlada.",
        "review": "Rever e corrigir",
        "review_help": "Revê todos os pilotos, tempos e voltas mais rápidas. Só leituras confiantes são preenchidas; os pontos vêm da posição.",
        "final": "Pré-visualização do resultado",
        "ready": "Todas as posições e todos os pilotos são válidos. O Excel ainda não foi alterado.",
        "blockers": "Resolve estes pontos antes de aprovar",
        "approve": "Revisei todas as linhas e aprovo a atualização do ficheiro Excel local.",
        "commit": "Atualizar Excel",
        "changed": "O Excel mudou desde a extração. Faz uma nova extração antes de aprovar.",
        "stale": "Os dados do evento ou as capturas mudaram. Faz uma nova extração.",
        "existing": "Esta corrida ou sprint já existe no Excel.",
        "safety": "O que acontece ao aprovar",
        "success": "Evento importado com segurança",
        "ocr_none": "O OCR não encontrou linhas. Remove as capturas e usa a revisão vazia, ou tenta imagens mais nítidas.",
        "hosted_intro": "Carrega 2 a 4 capturas da PlayStation de uma única Corrida ou Sprint, revê todos os campos e publica um evento verificado.",
        "hosted_safety": "Estás no atualizador privado. As capturas são processadas nesta revisão e nunca são guardadas no GitHub.",
        "hosted_approve": "Revisei todas as linhas e aprovo a publicação destes resultados.",
        "hosted_commit": "Publicar resultados",
        "hosted_ready": "Todas as posições e todos os pilotos são válidos. Ainda nada foi publicado.",
        "hosted_success": "Guardado no GitHub. O dashboard público está agora a atualizar.",
        "open_dashboard": "Abrir dashboard público",
        "commit_link": "Ver commit no GitHub",
        "github_auth": "As credenciais de publicação precisam de atenção. Nenhum dado foi alterado.",
        "github_conflict": "O Excel mudou durante a revisão. Atualiza a página e revê novamente este evento.",
        "github_unavailable": "O GitHub não confirmou a atualização. Não foi feita nenhuma repetição automática.",
        "writer_unavailable": "Não foi possível atualizar com segurança o sistema de escrita das corridas. Nenhum dado foi alterado.",
        "ocr_details": "Detalhes e avisos do OCR",
        "view_screenshots": "Ver capturas ({count})",
        "publishing": "A publicar o evento aprovado…",
        "publish_validate": "A validar o Excel mais recente e a revisão completa",
        "publish_commit": "A guardar um único commit protegido no GitHub",
        "time_help": "Valor exato do ecrã de resultados, por exemplo 82:50.787, +0.946, +1 Lap ou DNF.",
        "fastest_lap_help": "Valor exato de BEST, por exemplo 1:33.122. Usa N/A apenas quando o ecrã não tem valor.",
        "timing_required": "Cada linha precisa de Time e Fastest Lap confirmados antes da publicação.",
        "one_event": "Um conjunto de capturas = um evento. Em fins de semana Sprint, publica Sprint e Corrida separadamente.",
        "event_details": "Detalhes esperados do evento",
        "event_details_help": "Estes valores são selecionados automaticamente a partir do campeonato ativo e do Calendário. Expande apenas se precisares de os corrigir.",
        "defaults_uncertain": "O Excel não conseguiu identificar um único evento esperado com segurança. Confirma estes dados editáveis antes de carregar.",
        "auto_selected": "Pré-selecionado: {season} · {league} · Ronda {round} · {gp} · {session}{date}",
        "detected_session": "As capturas mostram {session}; o filtro Sessão foi atualizado automaticamente.",
    },
}


def text(lang: str, key: str) -> str:
    return _TEXT.get(lang, _TEXT["en"]).get(key, _TEXT["en"].get(key, key))


def _summarize_blockers(blockers: list[str], lang: str) -> list[str]:
    """Keep a full validation gate while rendering repeated row issues compactly."""
    driver_rows = sum(
        "needs a driver from the controlled championship roster" in blocker
        for blocker in blockers
    )
    timing_rows = sum(
        "needs a confirmed result time" in blocker
        or "needs a confirmed fastest lap" in blocker
        for blocker in blockers
    )
    summarized = [
        blocker
        for blocker in blockers
        if "needs a driver from the controlled championship roster" not in blocker
        and "needs a confirmed result time" not in blocker
        and "needs a confirmed fastest lap" not in blocker
        and not (driver_rows and blocker.startswith("Missing roster driver(s):"))
    ]
    if driver_rows:
        summarized.insert(
            0,
            (
                f"{driver_rows} review rows still need a controlled roster driver."
                if lang == "en"
                else f"{driver_rows} linhas ainda precisam de um piloto da grelha controlada."
            ),
        )
    if timing_rows and text(lang, "timing_required") not in summarized:
        summarized.insert(0, text(lang, "timing_required"))
    return list(dict.fromkeys(summarized))


def import_tab_label(lang: str) -> str:
    return text(lang, "tab")


def race_import_enabled() -> bool:
    """Return whether the protected local importer was explicitly enabled."""
    try:
        secrets: object = st.secrets
    except Exception:
        secrets = None
    return admin_auth.race_import_enabled(environ=os.environ, secrets=secrets)


def valid_screenshot_count(count: int) -> bool:
    """Return whether one event submission has an allowed screenshot count."""
    return 2 <= count <= 4


def blank_review_allowed(upload_count: int) -> bool:
    """The manual fallback is available only when no screenshots are attached."""
    return upload_count == 0


def validate_screenshot_set(upload_bytes: list[bytes]) -> list[str]:
    """Validate the complete upload set before preview or OCR."""
    errors: list[str] = []
    if not valid_screenshot_count(len(upload_bytes)):
        errors.append("An event upload requires between 2 and 4 screenshots.")
    digests = [_sha256_bytes(value) for value in upload_bytes]
    if len(set(digests)) != len(digests):
        errors.append("The upload set contains an identical duplicate screenshot.")
    for index, value in enumerate(upload_bytes, start=1):
        try:
            race_ocr.validate_image_upload(value, f"Screenshot {index}")
        except race_ocr.InvalidScreenshotError as exc:
            errors.append(str(exc))
    return errors


def validate_screenshot_bytes(image_bytes: bytes) -> None:
    """Compatibility wrapper for callers that validate one raster at a time."""
    race_ocr.validate_image_upload(image_bytes)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context_digest(context: dict) -> str:
    return ri.review_digest([], context)


def _upload_widget_key(
    source_token: str,
    context_key: str,
    round_number: int,
    gp_name: str,
    generation: int = 0,
) -> str:
    """Keep attached files stable when OCR synchronizes Race/Sprint."""
    return (
        f"race_import_uploads_v2_{source_token}_{context_key}_{round_number}_"
        f"{hashlib.sha1(str(gp_name).encode()).hexdigest()[:6]}_{int(generation)}"
    )


EXTRACTION_ERROR_KEY = "race_import_extraction_error"
_UPLOAD_WIDGET_PREFIX = "race_import_uploads_v2_"


def _clear_stale_upload_contexts(
    session_state: MutableMapping[object, object],
    *,
    current_upload_key: str,
) -> None:
    """Discard images from earlier event contexts, retaining the current picker."""

    current_prefix = f"{current_upload_key}:"
    for key in list(session_state):
        if not isinstance(key, str) or not key.startswith(_UPLOAD_WIDGET_PREFIX):
            continue
        if key == current_upload_key or key.startswith(current_prefix):
            continue
        del session_state[key]


def finalize_ocr_attempt(
    session_state: MutableMapping[object, object],
    *,
    upload_widget_key: str,
    upload_generation: int,
    error_message: str | None = None,
) -> None:
    """Discard attempted screenshots and rotate the uploader generation.

    The OCR review may retain only normalized review data and non-reversible
    screenshot hashes.  A failed attempt clears any older review so rotating
    the uploader cannot accidentally make that stale approval current again;
    only a text error survives for the next render.
    """

    for key in list(session_state):
        if isinstance(key, str) and (
            key == upload_widget_key or key.startswith(_UPLOAD_WIDGET_PREFIX)
        ):
            del session_state[key]
    session_state["race_import_upload_generation"] = int(upload_generation) + 1
    if error_message is None:
        session_state.pop(EXTRACTION_ERROR_KEY, None)
        return

    session_state.pop("race_import_draft", None)
    session_state.pop("race_import_detected_notice", None)
    message = str(error_message).strip()
    session_state[EXTRACTION_ERROR_KEY] = message or (
        "OCR could not finish reading these screenshots. Upload a fresh set and try again."
    )


def reset_import_state_after_success(
    session_state: MutableMapping[object, object],
    success: object,
) -> None:
    """Discard stale filters/uploads/drafts while preserving the result notice."""
    admin_auth.clear_race_import_state(session_state)
    session_state["race_import_success"] = success


def _championship_options(
    data: pd.DataFrame,
    config_tables: league_cfg.ConfigTables | None = None,
) -> list[tuple[str, str, str]]:
    if config_tables is not None:
        options = [tuple(row[:3]) for row in league_runtime.championship_options(data, config_tables)]
    else:
        pairs = data[["Game", "SeasonLabel", "League Name"]].drop_duplicates()
        options = [tuple(map(str, row)) for row in pairs.itertuples(index=False, name=None)]
    return sorted(
        options,
        key=lambda item: (
            core.season_sort_key(item[1]),
            ri.normalize_name(item[2]),
            ri.normalize_name(item[0]),
        ),
        reverse=True,
    )


def _format_championship(option: tuple[str, str, str]) -> str:
    game, season, league = option
    return f"{season} · {league} · {game}"


@dataclass(frozen=True)
class EventDefaults:
    """Editable event values inferred from one championship's calendar."""

    round_number: int
    gp_name: str
    event_type: str
    gp_options: tuple[str, ...]
    event_date: date | None = None
    confident: bool = False


@dataclass(frozen=True)
class AdminDefaults:
    """Safe initial Admin selection; ``confident`` means no identity guess."""

    championship: tuple[str, str, str]
    event: EventDefaults
    confident: bool


def _as_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _selected_championship_rows(
    data: pd.DataFrame,
    game: str,
    season: str,
    league: str,
) -> pd.DataFrame:
    return data[
        data["Game"].astype(str).eq(game)
        & data["SeasonLabel"].astype(str).eq(season)
        & data["League Name"].astype(str).eq(league)
        & ~data["IsSeasonFinal"].fillna(False)
    ].copy()


def _selected_event_rows(
    selected: pd.DataFrame,
    *,
    round_number: int,
    gp_name: str,
    event_type: str,
) -> pd.DataFrame:
    if selected.empty or not {"Round", "Type", "GP Name"}.issubset(selected.columns):
        return selected.iloc[0:0].copy()
    return selected[
        pd.to_numeric(selected["Round"], errors="coerce").eq(round_number)
        & selected["Type"].fillna("R").astype(str).str.strip().str.upper().eq(event_type)
        & selected["GP Name"].fillna("").astype(str).str.strip().eq(gp_name)
    ].copy()


def _configured_event_is_complete(
    selected: pd.DataFrame,
    tables: league_cfg.ConfigTables,
    *,
    league_id: str,
    round_number: int,
    gp_name: str,
    event_type: str,
) -> bool:
    """Verify one exact event against its effective configured roster."""

    try:
        roster = league_cfg.resolve_roster_snapshot(tables, league_id, round_number)
    except league_cfg.LeagueConfigError:
        return False
    event = _selected_event_rows(
        selected,
        round_number=round_number,
        gp_name=gp_name,
        event_type=event_type,
    )
    if event.empty or len(event) != len(roster):
        return False
    required = {"Driver", "Team", "Finish Pos", "Points"}
    if not required.issubset(event.columns):
        return False
    positions = pd.to_numeric(event["Finish Pos"], errors="coerce")
    points = pd.to_numeric(event["Points"], errors="coerce")
    if (
        positions.isna().any()
        or points.isna().any()
        or points.lt(0).any()
        or not positions.map(lambda value: float(value).is_integer()).all()
        or not points.map(lambda value: math.isfinite(float(value))).all()
        or set(positions.astype(int)) != set(range(1, len(roster) + 1))
    ):
        return False
    actual = {
        (
            league_cfg.normalize_identity(driver),
            league_cfg.normalize_identity(team),
        )
        for driver, team in event[["Driver", "Team"]]
        .fillna("")
        .itertuples(index=False, name=None)
    }
    expected = {
        (
            league_cfg.normalize_identity(row.driver_name),
            league_cfg.normalize_identity(row.team_name),
        )
        for row in roster
    }
    return (
        len(actual) == len(roster)
        and all(driver and team for driver, team in actual)
        and actual == expected
    )


def _calendar_candidates(
    selected: pd.DataFrame,
    calendar: pd.DataFrame,
    league: str,
    league_id: str = "",
    *,
    game: str = "",
    season: str = "",
    config_tables: league_cfg.ConfigTables | None = None,
) -> pd.DataFrame:
    """Return ordinary Race candidates plus safe missing-Sprint recovery."""
    required_columns = {"League Name", "Round", "GP Name", "Status"}
    if calendar.empty or not required_columns.issubset(calendar.columns):
        return calendar.iloc[0:0].copy()
    if league_id and "League ID" in calendar:
        league_calendar = calendar[
            calendar["League ID"].fillna("").astype(str).str.strip().eq(league_id)
        ].copy()
    else:
        league_calendar = (
            calendar[calendar["League Name"].astype(str).eq(league)].copy()
            if "League Name" in calendar
            else calendar.iloc[0:0].copy()
        )
    if league_calendar.empty:
        return league_calendar

    rounds = pd.to_numeric(league_calendar.get("Round"), errors="coerce")
    gp_names = league_calendar.get("GP Name", pd.Series("", index=league_calendar.index)).fillna("").astype(str).str.strip()
    statuses = league_calendar.get("Status", pd.Series("", index=league_calendar.index)).fillna("").astype(str).str.strip().str.casefold()
    upcoming = league_calendar[
        rounds.notna()
        & rounds.gt(0)
        & gp_names.ne("")
        & statuses.eq("upcoming")
    ].copy()
    if not upcoming.empty:
        upcoming["_Round"] = pd.to_numeric(upcoming["Round"], errors="coerce").astype(int)
        upcoming["_GPKey"] = upcoming["GP Name"].map(ri.normalize_name)
        upcoming["_Date"] = pd.to_datetime(upcoming.get("Date"), errors="coerce")
        upcoming["_EventType"] = "R"

    completed_races = selected[selected["Type"].astype(str).str.upper().eq("R")].copy()
    completed_keys = {
        (int(row_round), ri.normalize_name(gp_name))
        for row_round, gp_name in completed_races[["Round", "GP Name"]].itertuples(index=False, name=None)
        if not pd.isna(row_round)
    }
    if not upcoming.empty:
        upcoming = upcoming[
            ~upcoming.apply(
                lambda row: (int(row["_Round"]), str(row["_GPKey"])) in completed_keys,
                axis=1,
            )
        ].copy()

    recovery_rows: list[pd.Series] = []
    if league_id and config_tables is not None:
        configured_rows = config_tables.league_config[
            config_tables.league_config["League ID"].astype(str).str.strip().eq(league_id)
        ]
        configured_identity_ok = (
            len(configured_rows) == 1
            and str(configured_rows.iloc[0]["Status"]).strip().casefold() == "active"
            and (
                str(configured_rows.iloc[0]["Game"]).strip(),
                str(configured_rows.iloc[0]["Season"]).strip(),
                str(configured_rows.iloc[0]["League Name"]).strip(),
            )
            == (game, season, league)
        )
        if configured_identity_ok:
            for index, row in league_calendar.iterrows():
                numeric_round = pd.to_numeric(row.get("Round"), errors="coerce")
                gp_name = str(row.get("GP Name") or "").strip()
                try:
                    has_sprint = core._calendar_boolean(
                        row.get("Has Sprint", False), column="Has Sprint"
                    )
                except core.WorkbookValidationError:
                    continue
                exact_calendar_identity = (
                    str(row.get("Game") or "").strip(),
                    str(row.get("Season") or "").strip(),
                    str(row.get("League Name") or "").strip(),
                ) == (game, season, league)
                if (
                    pd.isna(numeric_round)
                    or not float(numeric_round).is_integer()
                    or int(numeric_round) < 1
                    or not gp_name
                    or str(row.get("Status") or "").strip().casefold() != "done"
                    or not has_sprint
                    or not exact_calendar_identity
                ):
                    continue
                round_number = int(numeric_round)
                sprint_rows = _selected_event_rows(
                    selected,
                    round_number=round_number,
                    gp_name=gp_name,
                    event_type="SR",
                )
                if not sprint_rows.empty or not _configured_event_is_complete(
                    selected,
                    config_tables,
                    league_id=league_id,
                    round_number=round_number,
                    gp_name=gp_name,
                    event_type="R",
                ):
                    continue
                candidate = row.copy()
                candidate["_Round"] = round_number
                candidate["_GPKey"] = ri.normalize_name(gp_name)
                candidate["_Date"] = pd.to_datetime(row.get("Date"), errors="coerce")
                candidate["_EventType"] = "SR"
                candidate.name = index
                recovery_rows.append(candidate)

    recovery = (
        pd.DataFrame(recovery_rows)
        if recovery_rows
        else league_calendar.iloc[0:0].assign(
            _Round=pd.Series(dtype=int),
            _GPKey=pd.Series(dtype=str),
            _Date=pd.Series(dtype="datetime64[ns]"),
            _EventType=pd.Series(dtype=str),
        )
    )
    if upcoming.empty:
        return recovery
    if recovery.empty:
        return upcoming
    return pd.concat([upcoming, recovery], ignore_index=False, sort=False)


def _gp_options(
    selected: pd.DataFrame,
    calendar: pd.DataFrame,
    league: str,
    default_gp: str,
    league_id: str = "",
) -> tuple[str, ...]:
    if league_id and not calendar.empty and "League ID" in calendar:
        league_calendar = calendar[
            calendar["League ID"].fillna("").astype(str).str.strip().eq(league_id)
        ]
    else:
        league_calendar = (
            calendar[calendar["League Name"].astype(str).eq(league)]
            if not calendar.empty and "League Name" in calendar
            else calendar.iloc[0:0]
        )
    calendar_gps = [
        str(value).strip()
        for value in league_calendar.get("GP Name", pd.Series(dtype=object)).dropna().tolist()
        if str(value).strip()
    ]
    historical_gps = [
        str(value).strip()
        for value in selected.get("GP Name", pd.Series(dtype=object)).dropna().tolist()
        if str(value).strip() and str(value).strip() != "Season Final"
    ]
    values = ([default_gp] if default_gp else []) + calendar_gps + historical_gps
    return tuple(dict.fromkeys(values))


def _event_default_for_championship(
    data: pd.DataFrame,
    calendar: pd.DataFrame,
    game: str,
    season: str,
    league: str,
    league_id: str = "",
    config_tables: league_cfg.ConfigTables | None = None,
) -> EventDefaults:
    selected = _selected_championship_rows(data, game, season, league)
    candidates = _calendar_candidates(
        selected,
        calendar,
        league,
        league_id,
        game=game,
        season=season,
        config_tables=config_tables,
    )

    confident = False
    event_date: date | None = None
    if not candidates.empty:
        # Duplicate calendar identities or two different events on the same
        # earliest date are not safe automatic choices.
        identity_duplicates = candidates.duplicated(["_Round", "_GPKey"], keep=False).any()
        ordered = candidates.sort_values(
            ["_Date", "_Round", "GP Name"],
            na_position="last",
        )
        next_row = ordered.iloc[0]
        default_round = int(next_row["_Round"])
        default_gp = str(next_row["GP Name"]).strip()
        event_date = _as_date(next_row.get("_Date"))
        if event_date is None:
            same_priority = ordered[ordered["_Date"].isna()]
        else:
            same_priority = ordered[ordered["_Date"].eq(pd.Timestamp(event_date))]
        confident = not identity_duplicates and len(same_priority) == 1
        default_event_type = str(next_row.get("_EventType") or "R").upper()
    else:
        latest_round = int(selected["Round"].max()) if not selected.empty else 0
        latest_rows = selected[pd.to_numeric(selected["Round"], errors="coerce").eq(latest_round)]
        latest_types = set(latest_rows["Type"].astype(str).str.upper())
        # A Sprint already imported without its Race means the same round is
        # still the expected event. Otherwise fall forward one round.
        default_round = latest_round if "SR" in latest_types and "R" not in latest_types else latest_round + 1
        default_round = max(1, default_round)
        calendar_identity = (
            calendar["League ID"].fillna("").astype(str).str.strip().eq(league_id)
            if league_id and "League ID" in calendar
            else calendar["League Name"].astype(str).eq(league)
        ) if not calendar.empty else pd.Series(False, index=calendar.index)
        matching = (
            calendar[
                calendar_identity
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(default_round)
            ]
            if not calendar.empty
            and {"League Name", "Round", "GP Name"}.issubset(calendar.columns)
            else calendar.iloc[0:0]
        )
        default_gp = str(matching.iloc[0]["GP Name"]).strip() if len(matching) == 1 else ""
        default_event_type = "R"

    # Every calendar event has a Race, while Sprint is optional. If Sprint is
    # already present and Race is absent, Race is still the only safe default.
    return EventDefaults(
        round_number=default_round,
        gp_name=default_gp,
        event_type=default_event_type if default_event_type in {"R", "SR"} else "R",
        gp_options=_gp_options(selected, calendar, league, default_gp, league_id),
        event_date=event_date,
        confident=confident,
    )


def infer_admin_defaults(
    data: pd.DataFrame,
    calendar: pd.DataFrame,
    config_tables: league_cfg.ConfigTables | None = None,
) -> AdminDefaults:
    """Infer one active championship/event, failing closed on ambiguity."""
    options = _championship_options(data, config_tables)
    if not options:
        raise ValueError("No championship data is available.")

    configured_ids: dict[tuple[str, str, str], str] = {}
    if config_tables is not None:
        configured_ids = {
            (key.game, key.season, key.league_name): key.league_id
            for key in league_cfg.configured_league_keys(config_tables)
        }
        active_rows = config_tables.league_config[
            config_tables.league_config["Status"].astype(str).str.casefold().eq("active")
        ]
        configured_active: list[tuple[tuple[str, str, str], EventDefaults]] = []
        for row in active_rows.to_dict("records"):
            option = (str(row["Game"]), str(row["Season"]), str(row["League Name"]))
            if option not in options:
                continue
            event = _event_default_for_championship(
                data,
                calendar,
                *option,
                str(row["League ID"]),
                config_tables,
            )
            if event.confident:
                configured_active.append((option, event))
        if len(configured_active) == 1:
            option, event = configured_active[0]
            return AdminDefaults(option, event, True)

    by_league: dict[str, list[tuple[str, str, str]]] = {}
    for option in options:
        by_league.setdefault(option[2], []).append(option)

    active: list[tuple[tuple[str, str, str], EventDefaults]] = []
    for league, league_options in by_league.items():
        # Calendar has no Game/Season columns. A reused league label therefore
        # cannot be mapped to a championship without guessing.
        if len(league_options) != 1:
            continue
        option = league_options[0]
        event = _event_default_for_championship(
            data,
            calendar,
            *option,
            configured_ids.get(option, ""),
            config_tables,
        )
        if event.confident:
            active.append((option, event))

    if len(active) == 1:
        option, event = active[0]
        return AdminDefaults(option, event, True)

    if data.empty:
        fallback = options[0]
    else:
        _, latest = core.latest_league_slice(data)
        fallback = (str(latest["Game"]), str(latest["SeasonLabel"]), str(latest["League Name"]))
    if fallback not in options:
        fallback = options[0]
    return AdminDefaults(
        fallback,
        _event_default_for_championship(
            data,
            calendar,
            *fallback,
            configured_ids.get(fallback, ""),
            config_tables,
        ),
        False,
    )


def _default_championship(
    options: list[tuple[str, str, str]],
    data: pd.DataFrame,
    calendar: pd.DataFrame | None = None,
) -> int:
    defaults = infer_admin_defaults(data, calendar if calendar is not None else core.empty_calendar())
    return options.index(defaults.championship) if defaults.championship in options else 0


def _event_defaults(
    data: pd.DataFrame,
    calendar: pd.DataFrame,
    game: str,
    season: str,
    league: str,
) -> tuple[int, str, list[str]]:
    """Compatibility tuple for existing callers and tests."""
    defaults = _event_default_for_championship(data, calendar, game, season, league)
    return defaults.round_number, defaults.gp_name, list(defaults.gp_options)


def _display_points(profile: dict[int, float]) -> str:
    nonzero = [f"{points:g}" for _, points in profile.items() if points]
    zero_from = next((position for position, points in profile.items() if not points), None)
    nonzero_end = (zero_from - 1) if zero_from else len(nonzero)
    return "–".join(nonzero) + f" (P1–P{nonzero_end})" + (
        f" · P{zero_from}–P{len(profile)}: 0" if zero_from else ""
    )


_GP_IDENTITY_STOP_WORDS = {
    "gp",
    "grand",
    "prix",
    "race",
    "sprint",
    "results",
    "result",
    "formula",
}


def _gp_identity_matches(tokens: list[ri.OcrToken], expected_gp: str) -> bool:
    expected_words = [
        word
        for word in ri.normalize_name(expected_gp).split()
        if word not in _GP_IDENTITY_STOP_WORDS
    ]
    if not expected_words:
        return False
    timing_columns = ri.detect_timing_columns(tokens)
    if timing_columns is None:
        return False
    observed_words = {
        word
        for token in tokens
        if token.confidence >= 0.65 and token.y_center < timing_columns.header_y
        for word in ri.normalize_name(token.text).split()
        if word not in _GP_IDENTITY_STOP_WORDS
    }
    return all(expected in observed_words for expected in expected_words)


def validate_results_session_set(
    upload_bytes: list[bytes],
    token_sets: list[list[ri.OcrToken]],
    expected_event_type: str,
    expected_gp: str | None = None,
    selected_tabs: list[str | None] | None = None,
) -> list[str]:
    """Fail closed unless every image is the selected event's detail table."""
    if expected_event_type not in {"R", "SR"}:
        return ["The selected session must be Race or Sprint."]
    if len(upload_bytes) != len(token_sets):
        return ["Every screenshot must have a matching OCR result."]
    if selected_tabs is not None and len(selected_tabs) != len(upload_bytes):
        return ["Every screenshot must have a matching selected-tab result."]

    expected_label = "Race" if expected_event_type == "R" else "Sprint"
    errors: list[str] = []
    for index, (image_bytes, tokens) in enumerate(zip(upload_bytes, token_sets), start=1):
        source = f"Screenshot {index}"
        selected_tab = (
            selected_tabs[index - 1]
            if selected_tabs is not None
            else race_ocr.detect_selected_results_tab(image_bytes, tokens)
        )
        if selected_tab is None:
            errors.append(
                f"{source}: the selected red Results tab could not be verified. "
                f"Use a clear photo showing Results ({expected_label})."
            )
        elif selected_tab == "WEEKEND":
            errors.append(
                f"{source}: Results (Weekend) is a combined summary and has no BEST/TIME detail. "
                f"Open Results ({expected_label}) instead."
            )
        elif selected_tab != expected_event_type:
            actual_label = "Race" if selected_tab == "R" else "Sprint"
            errors.append(
                f"{source}: the selected tab is {actual_label}, but the Admin session is {expected_label}. "
                "Upload one event at a time."
            )

        if ri.detect_timing_columns(tokens) is None:
            errors.append(
                f"{source}: BEST and TIME columns were not recognized. "
                f"Use the detailed Results ({expected_label}) table, not the Weekend summary."
            )
        if expected_gp is not None and not _gp_identity_matches(tokens, expected_gp):
            errors.append(
                f"{source}: the Grand Prix heading does not safely match {expected_gp}. "
                "Check the selected Grand Prix and upload one event only."
            )
    return list(dict.fromkeys(errors))


def detect_results_event_type(
    upload_bytes: list[bytes],
    token_sets: list[list[ri.OcrToken]],
) -> tuple[str | None, list[str | None]]:
    """Return Race/Sprint only when every selected screenshot tab agrees."""
    if len(upload_bytes) != len(token_sets) or not upload_bytes:
        return None, []
    selected_tabs = [
        race_ocr.detect_selected_results_tab(image_bytes, tokens)
        for image_bytes, tokens in zip(upload_bytes, token_sets)
    ]
    unique_tabs = set(selected_tabs)
    if len(unique_tabs) == 1 and selected_tabs[0] in {"R", "SR"}:
        return selected_tabs[0], selected_tabs
    return None, selected_tabs


def validate_screenshot_overlap(
    result_sets: list[list[ri.ExtractedResult]],
) -> list[str]:
    """Require a trusted overlap chain so disjoint events cannot be combined."""
    if len(result_sets) < 2:
        return ["At least two overlapping result screenshots are required."]

    connected_pairs: set[tuple[int, int]] = set()
    conflicts: list[str] = []

    def precise_timing(value: str | None) -> bool:
        if not value:
            return False
        normalized = value.strip().upper()
        if normalized in {"DNF", "DNS", "DSQ", "RET", "N/A"}:
            return False
        if re.fullmatch(r"\+\d+\s+LAPS?", normalized):
            return False
        return bool(re.search(r"\d", normalized))

    for left_index, left_rows in enumerate(result_sets):
        for right_index in range(left_index + 1, len(result_sets)):
            right_rows = result_sets[right_index]
            matching_positions: set[int] = set()
            for left in left_rows:
                left_identity = left.driver
                if left.position is None or not left_identity:
                    continue
                for right in right_rows:
                    right_identity = right.driver
                    if right.position is None or not right_identity:
                        continue
                    if left.position == right.position and left_identity != right_identity:
                        conflicts.append(
                            f"Screenshots {left_index + 1} and {right_index + 1} disagree on "
                            f"the driver at position {left.position}."
                        )
                    if left_identity == right_identity and left.position != right.position:
                        conflicts.append(
                            f"Screenshots {left_index + 1} and {right_index + 1} place "
                            f"{left_identity} at different positions."
                        )
                    if left.position != right.position or left_identity != right_identity:
                        continue
                    left_time = left.time
                    right_time = right.time
                    left_fastest = left.fastest_lap
                    right_fastest = right.fastest_lap
                    if left_time and right_time and left_time != right_time:
                        conflicts.append(
                            f"Screenshots {left_index + 1} and {right_index + 1} disagree on "
                            f"Time at position {left.position}."
                        )
                    if left_fastest and right_fastest and left_fastest != right_fastest:
                        conflicts.append(
                            f"Screenshots {left_index + 1} and {right_index + 1} disagree on "
                            f"Fastest Lap at position {left.position}."
                        )
                    if (
                        precise_timing(left_time) and left_time == right_time
                    ) or (
                        precise_timing(left_fastest) and left_fastest == right_fastest
                    ):
                        matching_positions.add(left.position)
            if len(matching_positions) >= 2:
                connected_pairs.add((left_index, right_index))

    if conflicts:
        return list(dict.fromkeys(conflicts))

    reached = {0}
    changed = True
    while changed:
        changed = False
        for left_index, right_index in connected_pairs:
            if left_index in reached and right_index not in reached:
                reached.add(right_index)
                changed = True
            elif right_index in reached and left_index not in reached:
                reached.add(left_index)
                changed = True
    if len(reached) == len(result_sets):
        return []
    missing = ", ".join(f"Screenshot {index + 1}" for index in range(len(result_sets)) if index not in reached)
    return [
        f"The screenshots do not form one trusted overlapping result set ({missing} is disconnected). "
        "Include repeated rows between adjacent screenshots and upload one event only."
    ]


@dataclass(frozen=True)
class OcrDraft:
    rows: list[dict]
    token_count: int
    event_type: str | None


def _prepare_ocr_draft(
    upload_bytes: list[bytes],
    roster: list[ri.DriverEntry],
    *,
    require_timing_detail: bool = False,
    expected_event_type: str | None = None,
    expected_gp: str | None = None,
    auto_detect_event_type: bool = False,
) -> OcrDraft:
    token_sets: list[list[ri.OcrToken]] = []
    token_count = 0
    for index, image_bytes in enumerate(upload_bytes, start=1):
        source = f"Screenshot {index}"
        tokens = race_ocr.extract_tokens(image_bytes, source)
        token_count += len(tokens)
        token_sets.append(tokens)
    detected_event_type: str | None = None
    selected_tabs: list[str | None] | None = None
    if require_timing_detail:
        detected_event_type, selected_tabs = detect_results_event_type(upload_bytes, token_sets)
        effective_event_type = (
            detected_event_type
            if auto_detect_event_type and detected_event_type in {"R", "SR"}
            else expected_event_type
        )
        session_errors = validate_results_session_set(
            upload_bytes,
            token_sets,
            effective_event_type or "",
            expected_gp,
            selected_tabs,
        )
        if session_errors:
            raise race_ocr.InvalidScreenshotError("\n".join(session_errors))
    result_sets = [
        ri.extract_results_from_tokens(tokens, roster, source=f"Screenshot {index}")
        for index, tokens in enumerate(token_sets, start=1)
    ]
    if require_timing_detail:
        overlap_errors = validate_screenshot_overlap(result_sets)
        if overlap_errors:
            raise race_ocr.InvalidScreenshotError("\n".join(overlap_errors))
    return OcrDraft(
        rows=ri.build_review_rows(
            ri.merge_screenshot_results(result_sets),
            len(roster),
        ),
        token_count=token_count,
        event_type=detected_event_type,
    )


def _draft_from_ocr(
    upload_bytes: list[bytes],
    roster: list[ri.DriverEntry],
    *,
    require_timing_detail: bool = False,
    expected_event_type: str | None = None,
    expected_gp: str | None = None,
) -> tuple[list[dict], int]:
    """Compatibility wrapper; UI session synchronization uses ``OcrDraft``."""
    draft = _prepare_ocr_draft(
        upload_bytes,
        roster,
        require_timing_detail=require_timing_detail,
        expected_event_type=expected_event_type,
        expected_gp=expected_gp,
    )
    return draft.rows, draft.token_count


def _render_safety_note(lang: str, *, hosted: bool = False) -> None:
    with st.expander(text(lang, "safety")):
        if hosted:
            copy = (
                "1. O resultado revisto é novamente validado com o Excel mais recente.\n"
                "2. O ficheiro é atualizado apenas se a versão do GitHub continuar igual.\n"
                "3. Só este evento e o respetivo estado no calendário são alterados.\n"
                "4. As capturas não são guardadas; o histórico do GitHub permite recuperar o Excel anterior."
                if lang == "pt"
                else "1. The reviewed result is checked again against the latest workbook.\n"
                "2. Publication proceeds only if the GitHub version is still unchanged.\n"
                "3. Only this event and its matching calendar status are changed.\n"
                "4. Screenshots are not stored; Git history preserves the prior workbook."
            )
        else:
            copy = (
                "1. O resultado revisto é validado novamente.\n2. É criada uma cópia de recuperação local.\n"
                "3. Só as células deste evento e o estado correspondente do calendário são alterados.\n"
                "4. Uma cópia temporária é validada antes de substituir o ficheiro original."
                if lang == "pt"
                else "1. The reviewed result is validated again.\n2. A local recovery copy is created.\n"
                "3. Only this event's cells and its matching calendar status are changed.\n"
                "4. A temporary candidate is validated before it replaces the original workbook."
            )
        st.markdown(copy)


def _require_local_admin(*, hosted: bool, expired: bool = False) -> bool:
    """Recheck the exact OIDC administrator for every protected action.

    ``hosted`` is retained for call-site compatibility and UI wording only;
    hosting privacy is defense in depth and never replaces app authorization.
    """
    del hosted
    if admin_auth.is_current_admin():
        return True
    st.error("Admin authorization expired. Sign in again." if expired else "Admin authorization is required.")
    st.stop()
    return False


@dataclass(frozen=True)
class RenderedEventFilters:
    championship: tuple[str, str, str]
    league_id: str
    round_number: int
    gp_name: str
    event_type: str
    session_override_key: str


def _render_event_filters(
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    source_token: str,
    config_tables: league_cfg.ConfigTables | None = None,
) -> RenderedEventFilters:
    """Render pre-selected but editable event metadata controls."""
    options = _championship_options(standings, config_tables)
    if not options:
        raise ValueError("No championship data is available.")
    automatic = infer_admin_defaults(standings, calendar, config_tables)
    league_ids = (
        {
            (key.game, key.season, key.league_name): key.league_id
            for key in league_cfg.configured_league_keys(config_tables)
        }
        if config_tables is not None
        else {}
    )
    championship_index = (
        options.index(automatic.championship)
        if automatic.championship in options
        else 0
    )

    with st.expander(
        text(lang, "event_details"),
        expanded=not automatic.confident,
    ):
        st.caption(text(lang, "event_details_help"))
        championship = st.selectbox(
            text(lang, "championship"),
            options,
            index=championship_index,
            format_func=_format_championship,
            key=f"race_import_championship_v2_{source_token}",
        )
        game, season, league = championship
        league_id = league_ids.get(championship, "")
        context_key = hashlib.sha256("|".join(championship).encode("utf-8")).hexdigest()[:10]
        event_defaults = _event_default_for_championship(
            standings,
            calendar,
            game,
            season,
            league,
            league_id,
            config_tables,
        )

        metadata_columns = st.columns([1, 2.4, 1.2])
        with metadata_columns[0]:
            round_number = int(
                st.number_input(
                    text(lang, "round"),
                    min_value=1,
                    max_value=999,
                    value=event_defaults.round_number,
                    step=1,
                    key=f"race_import_round_v2_{source_token}_{context_key}",
                )
            )
        calendar_identity = (
            calendar["League ID"].fillna("").astype(str).str.strip().eq(league_id)
            if league_id and "League ID" in calendar
            else calendar["League Name"].astype(str).eq(league)
        ) if not calendar.empty else pd.Series(False, index=calendar.index)
        matching_calendar = (
            calendar[
                calendar_identity
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(round_number)
            ]
            if not calendar.empty
            and {"League Name", "Round", "GP Name"}.issubset(calendar.columns)
            else calendar.iloc[0:0]
        )
        round_gp = (
            str(matching_calendar.iloc[0]["GP Name"]).strip()
            if len(matching_calendar) == 1
            else event_defaults.gp_name
        )
        gp_options = list(event_defaults.gp_options)
        if round_gp and round_gp not in gp_options:
            gp_options.insert(0, round_gp)
        with metadata_columns[1]:
            gp_name = (
                st.selectbox(
                    text(lang, "gp"),
                    gp_options,
                    index=gp_options.index(round_gp) if round_gp in gp_options else 0,
                    key=f"race_import_gp_v2_{source_token}_{context_key}_{round_number}",
                )
                if gp_options
                else st.text_input(
                    text(lang, "custom_gp"),
                    value=round_gp,
                    key=f"race_import_gp_text_v2_{source_token}_{context_key}_{round_number}",
                )
            )

        event_identity = hashlib.sha256(
            f"{source_token}|{context_key}|{round_number}|{gp_name}".encode("utf-8")
        ).hexdigest()[:12]
        session_override_key = f"race_import_session_override_{event_identity}"
        session_default = st.session_state.get(
            session_override_key,
            event_defaults.event_type,
        )
        if session_default not in {"R", "SR"}:
            session_default = "R"
        session_labels = [text(lang, "race"), text(lang, "sprint")]
        with metadata_columns[2]:
            display_type = st.radio(
                text(lang, "event_type"),
                session_labels,
                index=1 if session_default == "SR" else 0,
                horizontal=True,
                key=(
                    f"race_import_type_v2_{event_identity}_{session_default}"
                ),
            )
        event_type = "SR" if display_type == text(lang, "sprint") else "R"

    if not automatic.confident and championship == automatic.championship:
        st.warning(text(lang, "defaults_uncertain"))
    event_date = (
        event_defaults.event_date
        if round_number == event_defaults.round_number
        and str(gp_name).strip() == event_defaults.gp_name
        else None
    )
    date_suffix = f" · {event_date:%d %b %Y}" if event_date else ""
    st.caption(
        text(lang, "auto_selected").format(
            season=season,
            league=league,
            round=round_number,
            gp=str(gp_name).strip(),
            session=text(lang, "sprint" if event_type == "SR" else "race"),
            date=date_suffix,
        )
    )
    return RenderedEventFilters(
        championship=championship,
        league_id=league_id,
        round_number=round_number,
        gp_name=str(gp_name).strip(),
        event_type=event_type,
        session_override_key=session_override_key,
    )


def render_race_import(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    clear_data_cache: Callable[[], None],
    source_version: str | None = None,
    hosted_publisher: HostedPublisher | None = None,
    dashboard_url: str = "https://f1-game-dashboard.streamlit.app/",
) -> None:
    """Render a write-free review followed by a protected local or hosted commit."""
    hosted = hosted_publisher is not None
    if not _require_local_admin(hosted=hosted):
        return

    if success := st.session_state.pop("race_import_success", None):
        if isinstance(success, dict):
            st.success(str(success.get("message", text(lang, "hosted_success"))))
            link_columns = st.columns(2)
            if success.get("commit_url"):
                link_columns[0].link_button(
                    text(lang, "commit_link"),
                    str(success["commit_url"]),
                    use_container_width=True,
                )
            link_columns[1].link_button(
                text(lang, "open_dashboard"),
                dashboard_url,
                type="primary",
                use_container_width=True,
            )
        else:
            st.success(success)

    st.header(text(lang, "title"))
    st.write(text(lang, "hosted_intro" if hosted else "intro"))
    st.info(text(lang, "hosted_safety" if hosted else "local"), icon="🔒")

    workbook_sha = rw.workbook_fingerprint(workbook_path)
    reviewed_source_version = source_version or workbook_sha
    source_token = hashlib.sha256(
        str(reviewed_source_version).encode("utf-8")
    ).hexdigest()[:10]
    try:
        config_tables = league_cfg.load_config_tables(workbook_path)
        filters = _render_event_filters(
            standings,
            calendar,
            lang=lang,
            source_token=source_token,
            config_tables=config_tables,
        )
    except (ValueError, league_cfg.LeagueConfigError):
        st.error("No championship data is available.")
        return
    championship = filters.championship
    game, season, league = championship
    league_id = filters.league_id
    context_key = hashlib.sha256("|".join(championship).encode("utf-8")).hexdigest()[:10]
    round_number = filters.round_number
    gp_name = filters.gp_name
    event_type = filters.event_type
    if detected_notice := st.session_state.pop("race_import_detected_notice", None):
        st.info(str(detected_notice))
    if extraction_error := st.session_state.pop(EXTRACTION_ERROR_KEY, None):
        st.error(str(extraction_error))
    st.caption(text(lang, "one_event"))
    try:
        metadata = race_metadata.make_race_metadata(
            game=game,
            season=season,
            league=league,
            round_number=round_number,
            event_type=event_type,
            gp_name=gp_name,
            league_id=league_id,
        )
    except race_metadata.RaceMetadataCompatibilityError:
        st.error(text(lang, "writer_unavailable"))
        return
    try:
        authority = league_runtime.resolve_event_authority(
            workbook_path,
            standings,
            metadata,
        )
        roster = list(authority.roster)
        scoring = authority.base_points
    except league_runtime.LeagueAuthorityError as exc:
        st.error(str(exc))
        return
    info_columns = st.columns(2)
    info_columns[0].metric(text(lang, "roster"), f"{len(roster)} drivers")
    info_columns[1].caption(text(lang, "scoring"))
    info_columns[1].code(_display_points(scoring), language=None)
    if authority.scoring.fastest_lap_bonus > 0:
        eligibility = authority.scoring.fastest_lap_max_finish
        eligible_text = (
            f"top {eligibility}"
            if eligibility is not None
            else "all classified drivers"
        )
        info_columns[1].caption(
            (
                f"Fastest lap: +{authority.scoring.fastest_lap_bonus:g} point(s), {eligible_text}."
                if lang == "en"
                else f"Volta mais rápida: +{authority.scoring.fastest_lap_bonus:g} ponto(s), elegível: {eligible_text}."
            )
        )

    upload_generation = int(st.session_state.get("race_import_upload_generation", 0))
    upload_widget_key = _upload_widget_key(
        source_token,
        context_key,
        round_number,
        str(gp_name),
        upload_generation,
    )
    _clear_stale_upload_contexts(
        st.session_state,
        current_upload_key=upload_widget_key,
    )
    secure_upload = hosted and secure_image_upload.enabled()
    if secure_upload:
        uploads, transport_errors = secure_image_upload.render_uploader(
            text(lang, "screenshots"),
            help_text=text(lang, "screenshots_help"),
            key=upload_widget_key,
            lang=lang,
        )
    else:
        uploads = st.file_uploader(
            text(lang, "screenshots"),
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help=text(lang, "screenshots_help"),
            key=upload_widget_key,
        )
        transport_errors = []
    upload_bytes = [upload.getvalue() for upload in uploads] if uploads else []
    upload_errors = list(transport_errors)
    if uploads:
        upload_errors.extend(validate_screenshot_set(upload_bytes))

    existing_draft = st.session_state.get("race_import_draft")
    if uploads and not upload_errors and not secure_upload:
        preview_container = st.expander(
            text(lang, "view_screenshots").format(count=len(uploads)),
            expanded=not bool(existing_draft),
        )
        with preview_container:
            preview_columns = st.columns(min(len(uploads), 2))
            for index, upload in enumerate(uploads, start=1):
                column = preview_columns[(index - 1) % len(preview_columns)]
                column.image(
                    upload.getvalue(),
                    caption=f"Screenshot {index} · {upload.name}",
                    width="stretch",
                )
    if not valid_screenshot_count(len(upload_bytes)) and not existing_draft:
        st.caption(text(lang, "needs_two"))
    for upload_error in upload_errors:
        st.error(upload_error)

    retained_screenshot_hashes = (
        list(existing_draft.get("screenshot_hashes", []))
        if isinstance(existing_draft, dict)
        else []
    )
    current_screenshot_hashes = (
        [_sha256_bytes(value) for value in upload_bytes]
        if upload_bytes
        else retained_screenshot_hashes
    )
    context = {
        "game": game,
        "season": season,
        "league": league,
        "league_id": league_id,
        "round": round_number,
        "type": event_type,
        "gp": str(gp_name).strip(),
        "mode": "hosted" if hosted else "local",
        "workbook_sha256": workbook_sha,
        "source_version": reviewed_source_version,
        "screenshots": current_screenshot_hashes,
    }
    current_context_digest = _context_digest(context)
    action_columns = st.columns(2)
    extract_clicked = action_columns[0].button(
        text(lang, "extract"),
        type="primary",
        use_container_width=True,
        disabled=(
            bool(upload_errors)
            or not valid_screenshot_count(len(upload_bytes))
            or not str(gp_name).strip()
        ),
        key=f"race_import_extract_{current_context_digest[:12]}",
    )
    manual_clicked = action_columns[1].button(
        text(lang, "manual_review"),
        use_container_width=True,
        disabled=not blank_review_allowed(len(upload_bytes)) or not str(gp_name).strip(),
        key=f"race_import_manual_{current_context_digest[:12]}",
    )
    st.caption(text(lang, "manual_help"))

    if extract_clicked:
        if not _require_local_admin(hosted=hosted, expired=True):
            return
        if not valid_screenshot_count(len(upload_bytes)):
            st.error(text(lang, "needs_two"))
            st.stop()
            return
        if upload_errors:
            st.error("The screenshot set did not pass validation.")
            st.stop()
            return
        extraction_error: str | None = None
        try:
            with st.spinner(
                "Reading screenshots locally…" if lang == "en" else "A ler as capturas localmente…"
            ):
                ocr_draft = _prepare_ocr_draft(
                    upload_bytes,
                    roster,
                    require_timing_detail=True,
                    expected_event_type=event_type,
                    expected_gp=str(gp_name),
                    auto_detect_event_type=True,
                )
            detected_type = ocr_draft.event_type
            session_changed = detected_type in {"R", "SR"} and detected_type != event_type
            if session_changed:
                event_type = str(detected_type)
                st.session_state[filters.session_override_key] = event_type
                metadata = race_metadata.make_race_metadata(
                    game=game,
                    season=season,
                    league=league,
                    round_number=round_number,
                    event_type=event_type,
                    gp_name=gp_name,
                    league_id=league_id,
                )
                authority = league_runtime.resolve_event_authority(
                    workbook_path,
                    standings,
                    metadata,
                )
                roster = list(authority.roster)
                scoring = authority.base_points
                context["type"] = event_type
                current_context_digest = _context_digest(context)
            st.session_state["race_import_draft"] = {
                "context_digest": current_context_digest,
                "workbook_sha256": workbook_sha,
                "source_version": reviewed_source_version,
                "rows": ocr_draft.rows,
                # Only non-reversible digests remain after successful OCR;
                # raw screenshots are removed from the uploader state.
                "screenshot_hashes": list(context["screenshots"]),
                "token_count": ocr_draft.token_count,
                "draft_id": ri.review_digest(ocr_draft.rows, context)[:12],
            }
            if not any(row["OCR text"] for row in ocr_draft.rows):
                st.warning(text(lang, "ocr_none"))
            if session_changed:
                st.session_state["race_import_detected_notice"] = text(
                    lang,
                    "detected_session",
                ).format(
                    session=text(lang, "sprint" if event_type == "SR" else "race")
                )
        except race_metadata.RaceMetadataCompatibilityError:
            extraction_error = text(lang, "writer_unavailable")
        except race_ocr.InvalidScreenshotError as exc:
            extraction_error = str(exc)
        except (ri.ScoringProfileError, league_runtime.LeagueAuthorityError) as exc:
            extraction_error = str(exc)
        except (race_ocr.OcrUnavailableError, RuntimeError) as exc:
            extraction_error = (
                (
                    "OCR could not read these screenshots. Upload a fresh, clearer set or start a blank review."
                    if lang == "en"
                    else "O OCR não conseguiu ler estas capturas. Carrega um novo conjunto mais nítido ou inicia uma revisão vazia."
                )
                if hosted
                else str(exc)
            )
        except Exception:
            extraction_error = (
                "OCR could not finish reading these screenshots. Upload a fresh set and try again."
                if lang == "en"
                else "O OCR não conseguiu terminar a leitura destas capturas. Carrega um novo conjunto e tenta novamente."
            )

        finalize_ocr_attempt(
            st.session_state,
            upload_widget_key=upload_widget_key,
            upload_generation=upload_generation,
            error_message=extraction_error,
        )
        # End every attempted extraction run so UploadedFile objects and local
        # byte lists leave scope immediately, including after OCR failures.
        st.rerun()

    if manual_clicked:
        if not _require_local_admin(hosted=hosted, expired=True):
            return
        if not blank_review_allowed(len(upload_bytes)):
            st.error("Remove the attached screenshots before starting a blank review.")
            st.stop()
            return
        st.session_state["race_import_draft"] = {
            "context_digest": current_context_digest,
            "workbook_sha256": workbook_sha,
            "source_version": reviewed_source_version,
            "rows": ri.build_review_rows([], len(roster)),
            "screenshot_hashes": [],
            "token_count": 0,
            "draft_id": ri.review_digest([], {**context, "manual": True})[:12],
        }

    draft = st.session_state.get("race_import_draft")
    if not draft:
        _render_safety_note(lang, hosted=hosted)
        return
    if draft["context_digest"] != current_context_digest:
        st.warning(text(lang, "stale"))
        _render_safety_note(lang, hosted=hosted)
        return

    st.subheader(text(lang, "review"))
    st.caption(text(lang, "review_help"))
    unselected_driver = "— Selecionar piloto —" if lang == "pt" else "— Select driver —"
    editor_frame = pd.DataFrame(draft["rows"])
    editor_frame["Driver"] = editor_frame["Driver"].replace("", unselected_driver)
    for timing_column in ("Time", "Fastest Lap"):
        if timing_column not in editor_frame:
            editor_frame[timing_column] = ""
        editor_frame[timing_column] = editor_frame[timing_column].fillna("").astype(str)
    compact_editor = editor_frame[["Position", "Driver", "Time", "Fastest Lap"]].copy()
    edited_compact = st.data_editor(
        compact_editor,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        column_order=["Position", "Driver", "Time", "Fastest Lap"],
        column_config={
            "Position": st.column_config.NumberColumn(
                "Pos.",
                min_value=1,
                max_value=len(roster),
                step=1,
                required=True,
                width="small",
            ),
            "Driver": st.column_config.SelectboxColumn(
                "Driver",
                options=[unselected_driver] + [entry.driver for entry in roster],
                required=True,
                width="medium",
            ),
            "Time": st.column_config.TextColumn(
                "Time",
                help=text(lang, "time_help"),
                width="small",
            ),
            "Fastest Lap": st.column_config.TextColumn(
                "Fastest Lap",
                help=text(lang, "fastest_lap_help"),
                width="small",
            ),
        },
        key=f"race_import_editor_{draft['draft_id']}",
    )
    unresolved_count = int(edited_compact["Driver"].eq(unselected_driver).sum())
    if unresolved_count:
        st.warning(
            f"{unresolved_count} rows need your driver choice."
            if lang == "en"
            else f"{unresolved_count} linhas precisam da tua escolha de piloto."
        )
    with st.expander(text(lang, "ocr_details")):
        detail_columns = [
            "Position",
            "Suggested driver",
            "Confidence",
            "Seen in",
            "OCR text",
            "OCR notes",
            "Suggested Time",
            "Time Confidence",
            "Time Notes",
            "Suggested Fastest Lap",
            "Fastest Lap Confidence",
            "Fastest Lap Notes",
        ]
        st.dataframe(
            editor_frame[[column for column in detail_columns if column in editor_frame]],
            width="stretch",
            hide_index=True,
        )

    edited_for_validation = edited_compact.copy()
    edited_for_validation["Driver"] = edited_for_validation["Driver"].replace(
        unselected_driver,
        "",
    )
    # Admin publications always carry the result detail fields. OCR suggestions
    # are advisory; every value must be confirmed in this controlled editor.
    edited_for_validation["Timing Expected"] = True
    validation = ri.validate_review_rows(
        edited_for_validation.to_dict("records"),
        roster,
        scoring,
    )
    blockers = list(validation.blockers)
    scored_rows = validation.rows
    fastest_lap_award = None
    if not blockers:
        try:
            scored_rows, fastest_lap_award = league_runtime.apply_configured_points(
                validation.rows,
                authority,
            )
        except league_runtime.LeagueAuthorityError as exc:
            blockers.append(str(exc))
    if edited_for_validation[["Time", "Fastest Lap"]].replace("", pd.NA).isna().any(axis=None):
        blockers.insert(0, text(lang, "timing_required"))
    if rw.event_already_exists(standings, metadata):
        blockers.append(text(lang, "existing"))
    if not hosted and rw.workbook_fingerprint(workbook_path) != draft["workbook_sha256"]:
        blockers.append(text(lang, "changed"))

    st.subheader(text(lang, "final"))
    final_frame = pd.DataFrame(scored_rows).sort_values("Position", na_position="last")
    if not final_frame.empty:
        display_frame = final_frame.copy()
        display_frame["Points"] = display_frame["Points"].map(
            lambda value: int(value) if float(value).is_integer() else value
        )
        st.dataframe(display_frame, width="stretch", hide_index=True)
    if blockers:
        st.error(text(lang, "blockers"))
        for blocker in _summarize_blockers(blockers, lang):
            st.markdown(f"- {blocker}")
    else:
        st.success(text(lang, "hosted_ready" if hosted else "ready"))

    reviewed_digest = ri.review_digest(scored_rows, context)
    approved = st.checkbox(
        text(lang, "hosted_approve" if hosted else "approve"),
        key=f"race_import_approval_{reviewed_digest[:16]}",
    )
    commit_clicked = st.button(
        text(lang, "hosted_commit" if hosted else "commit"),
        type="primary",
        use_container_width=True,
        disabled=bool(blockers) or not approved,
        key=f"race_import_commit_{reviewed_digest[:16]}",
    )
    if commit_clicked:
        if not _require_local_admin(hosted=hosted, expired=True):
            return
        try:
            if hosted and hosted_publisher is not None:
                with st.status(text(lang, "publishing"), expanded=True) as publication_status:
                    st.write(text(lang, "publish_validate"))
                    result = hosted_publisher(
                        metadata,
                        scored_rows,
                        scoring,
                        str(draft["source_version"]),
                        approved,
                    )
                    st.write(text(lang, "publish_commit"))
                    publication_status.update(
                        label=text(lang, "hosted_success"),
                        state="complete",
                        expanded=False,
                    )
            else:
                result = rw.commit_race_import(
                    workbook_path,
                    metadata=metadata,
                    rows=scored_rows,
                    scoring_profile=scoring,
                    expected_sha256=draft["workbook_sha256"],
                    approved=approved,
                    require_complete_timing=True,
                )
        except (ghstore.GitHubAuthError, ghstore.GitHubConfigurationError):
            st.error(text(lang, "github_auth"))
        except ghstore.GitHubConflictError:
            st.error(text(lang, "github_conflict"))
            st.session_state.pop("race_import_draft", None)
        except (ghstore.GitHubNetworkError, ghstore.GitHubAPIError):
            st.error(text(lang, "github_unavailable"))
        except rw.WorkbookUpdateError as exc:
            st.error(str(exc) if not hosted else text(lang, "github_conflict"))
        else:
            if hosted:
                success_payload: object = {
                    "message": text(lang, "hosted_success"),
                    "commit_url": getattr(result, "commit_url", ""),
                }
            else:
                calendar_note = (
                    " Calendar marked Done."
                    if lang == "en"
                    else " Calendário marcado como concluído."
                ) if result.calendar_updated else ""
                success_payload = (
                    f"{text(lang, 'success')}: {result.rows_added} rows added "
                    f"(Excel {result.first_excel_row}–{result.last_excel_row})."
                    f"{calendar_note} Recovery copy: {result.backup_path}"
                )
            clear_data_cache()
            reset_import_state_after_success(st.session_state, success_payload)
            st.rerun()
    _render_safety_note(lang, hosted=hosted)
