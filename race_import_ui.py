"""Streamlit review workflow for local two-screenshot race imports."""

from __future__ import annotations

import hashlib
import os
from typing import Callable

import pandas as pd
import streamlit as st

import dashboard_core as core
import race_import as ri
import race_ocr
import race_workbook as rw


_TEXT = {
    "en": {
        "tab": "📥 Import race", "title": "Import one race",
        "intro": "Upload the two PlayStation result screenshots, review every position, then approve one safe workbook update.",
        "local": "This local-only tool never writes during extraction or review. Direct Excel editing remains available as a fallback.",
        "championship": "Championship", "round": "Round", "gp": "Grand Prix", "custom_gp": "Grand Prix name",
        "event_type": "Session", "race": "Race", "sprint": "Sprint", "roster": "Controlled roster", "scoring": "Verified scoring",
        "screenshots": "Two result screenshots",
        "screenshots_help": "Upload both screenshots from the same result table. An overlapping row is fine and will be reconciled.",
        "needs_two": "Upload exactly two screenshots from this race.", "extract": "Extract standings", "manual_review": "Start blank review",
        "manual_help": "OCR is optional to the dashboard. A blank review lets you enter the same controlled result safely if OCR is unavailable.",
        "review": "Review and correct",
        "review_help": "Only exact, confident roster matches are prefilled. Choose a driver for every blank or uncertain row; points are calculated from position.",
        "final": "Result preview", "ready": "All positions and roster drivers are valid. The workbook has not been changed.",
        "blockers": "Resolve these items before approval",
        "approve": "I reviewed every row and approve updating the local Excel workbook.", "commit": "Update workbook",
        "changed": "The workbook changed since extraction. Re-extract before approving.",
        "stale": "Race details or screenshots changed. Extract again to create a matching review.",
        "existing": "This race or sprint already exists in the workbook.", "safety": "What happens on approval",
        "success": "Race imported safely", "ocr_none": "OCR found no standings rows. Use the blank review or try clearer screenshots.",
    },
    "pt": {
        "tab": "📥 Importar corrida", "title": "Importar uma corrida",
        "intro": "Carrega as duas capturas dos resultados da PlayStation, revê todas as posições e só depois aprova uma atualização segura do Excel.",
        "local": "Esta ferramenta local não escreve durante a extração ou revisão. A edição direta no Excel continua disponível como alternativa.",
        "championship": "Campeonato", "round": "Ronda", "gp": "Grande Prémio", "custom_gp": "Nome do Grande Prémio",
        "event_type": "Sessão", "race": "Corrida", "sprint": "Sprint", "roster": "Grelha controlada", "scoring": "Pontuação verificada",
        "screenshots": "Duas capturas dos resultados",
        "screenshots_help": "Carrega as duas capturas da mesma tabela. Uma linha repetida entre imagens será reconciliada.",
        "needs_two": "Carrega exatamente duas capturas desta corrida.", "extract": "Extrair classificação", "manual_review": "Iniciar revisão vazia",
        "manual_help": "O OCR é opcional para o dashboard. A revisão vazia permite inserir o mesmo resultado de forma controlada.",
        "review": "Rever e corrigir",
        "review_help": "Só correspondências exatas e confiantes são preenchidas. Escolhe um piloto para cada linha incerta; os pontos vêm da posição.",
        "final": "Pré-visualização do resultado", "ready": "Todas as posições e todos os pilotos são válidos. O Excel ainda não foi alterado.",
        "blockers": "Resolve estes pontos antes de aprovar",
        "approve": "Revisei todas as linhas e aprovo a atualização do ficheiro Excel local.", "commit": "Atualizar Excel",
        "changed": "O Excel mudou desde a extração. Faz uma nova extração antes de aprovar.",
        "stale": "Os dados da corrida ou as capturas mudaram. Faz uma nova extração.",
        "existing": "Esta corrida ou sprint já existe no Excel.", "safety": "O que acontece ao aprovar",
        "success": "Corrida importada com segurança", "ocr_none": "O OCR não encontrou linhas de classificação. Usa a revisão vazia ou capturas mais nítidas.",
    },
}


def text(lang: str, key: str) -> str:
    return _TEXT.get(lang, _TEXT["en"]).get(key, _TEXT["en"].get(key, key))


def import_tab_label(lang: str) -> str:
    return text(lang, "tab")


def race_import_enabled() -> bool:
    """Keep filesystem mutation out of hosted deployments unless opted in."""
    return os.environ.get("F1_ENABLE_RACE_IMPORT", "").strip().casefold() in {"1", "true", "yes", "on"}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context_digest(context: dict) -> str:
    return ri.review_digest([], context)


def _championship_options(data: pd.DataFrame) -> list[tuple[str, str, str]]:
    pairs = data[["Game", "SeasonLabel", "League Name"]].drop_duplicates()
    options = [tuple(map(str, row)) for row in pairs.itertuples(index=False, name=None)]
    return sorted(options, key=lambda item: (core.season_sort_key(item[1]), ri.normalize_name(item[2]), ri.normalize_name(item[0])), reverse=True)


def _format_championship(option: tuple[str, str, str]) -> str:
    game, season, league = option
    return f"{season} · {league} · {game}"


def _default_championship(options: list[tuple[str, str, str]], data: pd.DataFrame) -> int:
    _, latest = core.latest_league_slice(data)
    target = (str(latest["Game"]), str(latest["SeasonLabel"]), str(latest["League Name"]))
    return options.index(target) if target in options else 0


def _event_defaults(data: pd.DataFrame, calendar: pd.DataFrame, game: str, season: str, league: str) -> tuple[int, str, list[str]]:
    selected = data[
        data["Game"].astype(str).eq(game)
        & data["SeasonLabel"].astype(str).eq(season)
        & data["League Name"].astype(str).eq(league)
        & ~data["IsSeasonFinal"].fillna(False)
    ]
    latest_round = int(selected["Round"].max()) if not selected.empty else 0
    league_calendar = calendar[calendar["League Name"].astype(str).eq(league)].copy() if not calendar.empty else calendar
    upcoming = league_calendar[league_calendar["Status"].astype(str).str.casefold().eq("upcoming")] if not league_calendar.empty else league_calendar
    if not upcoming.empty:
        next_row = upcoming.sort_values(["Round", "Date"], na_position="last").iloc[0]
        default_round, default_gp = int(next_row["Round"]), str(next_row["GP Name"])
    else:
        default_round = latest_round + 1
        matching = league_calendar[pd.to_numeric(league_calendar["Round"], errors="coerce").eq(default_round)] if not league_calendar.empty else league_calendar
        default_gp = str(matching.iloc[0]["GP Name"]) if not matching.empty else ""
    gp_options = [str(value) for value in league_calendar["GP Name"].dropna().unique().tolist()] if not league_calendar.empty else []
    historical_gps = [str(value) for value in data["GP Name"].dropna().unique().tolist() if str(value) != "Season Final"]
    return default_round, default_gp, list(dict.fromkeys(([default_gp] if default_gp else []) + gp_options + sorted(historical_gps)))


def _display_points(profile: dict[int, float]) -> str:
    nonzero = [f"{points:g}" for _, points in profile.items() if points]
    zero_from = next((position for position, points in profile.items() if not points), None)
    nonzero_end = (zero_from - 1) if zero_from else len(nonzero)
    return "–".join(nonzero) + f" (P1–P{nonzero_end})" + (f" · P{zero_from}–P{len(profile)}: 0" if zero_from else "")


def _draft_from_ocr(upload_bytes: list[bytes], roster: list[ri.DriverEntry]) -> tuple[list[dict], int]:
    result_sets, token_count = [], 0
    for index, image_bytes in enumerate(upload_bytes, start=1):
        source = f"Screenshot {index}"
        tokens = race_ocr.extract_tokens(image_bytes, source)
        token_count += len(tokens)
        result_sets.append(ri.extract_results_from_tokens(tokens, roster, source=source))
    return ri.build_review_rows(ri.merge_screenshot_results(result_sets), len(roster)), token_count


def _render_safety_note(lang: str) -> None:
    with st.expander(text(lang, "safety")):
        copy = (
            "1. O resultado revisto é validado novamente.\n2. É criada uma cópia de recuperação local.\n"
            "3. Só as células desta corrida e o estado correspondente do calendário são alterados.\n"
            "4. Uma cópia temporária é validada antes de substituir o ficheiro original."
            if lang == "pt"
            else "1. The reviewed result is validated again.\n2. A local recovery copy is created.\n"
            "3. Only this race's cells and its matching calendar status are changed.\n"
            "4. A temporary candidate is validated before it replaces the original workbook."
        )
        st.markdown(copy)


def render_race_import(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    clear_data_cache: Callable[[], None],
) -> None:
    """Render the local-only staged import and approval flow."""
    if success := st.session_state.pop("race_import_success", None):
        st.success(success)
    st.header(text(lang, "title"))
    st.write(text(lang, "intro"))
    st.info(text(lang, "local"), icon="🔒")

    options = _championship_options(standings)
    if not options:
        st.error("No championship data is available.")
        return
    championship = st.selectbox(
        text(lang, "championship"), options, index=_default_championship(options, standings),
        format_func=_format_championship, key="race_import_championship",
    )
    game, season, league = championship
    context_key = hashlib.sha256("|".join(championship).encode("utf-8")).hexdigest()[:10]
    try:
        roster = ri.derive_championship_roster(standings, game=game, season=season, league=league)
    except ri.RosterError as exc:
        st.error(str(exc))
        return

    default_round, default_gp, gp_options = _event_defaults(standings, calendar, game, season, league)
    metadata_columns = st.columns([1, 2.4, 1.2])
    with metadata_columns[0]:
        round_number = int(st.number_input(text(lang, "round"), min_value=1, max_value=999, value=default_round, step=1, key=f"race_import_round_{context_key}"))
    matching_calendar = calendar[
        calendar["League Name"].astype(str).eq(league) & pd.to_numeric(calendar["Round"], errors="coerce").eq(round_number)
    ] if not calendar.empty else calendar
    round_gp = str(matching_calendar.iloc[0]["GP Name"]) if not matching_calendar.empty else default_gp
    with metadata_columns[1]:
        gp_name = (
            st.selectbox(text(lang, "gp"), gp_options, index=gp_options.index(round_gp) if round_gp in gp_options else 0, key=f"race_import_gp_{context_key}_{round_number}")
            if gp_options else st.text_input(text(lang, "custom_gp"), value=round_gp, key=f"race_import_gp_text_{context_key}_{round_number}")
        )
    with metadata_columns[2]:
        display_type = st.radio(text(lang, "event_type"), [text(lang, "race"), text(lang, "sprint")], horizontal=True, key=f"race_import_type_{context_key}_{round_number}")
    event_type = "SR" if display_type == text(lang, "sprint") else "R"

    try:
        scoring = ri.infer_scoring_profile(standings, game=game, season=season, league=league, event_type=event_type, grid_size=len(roster))
    except ri.ScoringProfileError as exc:
        st.error(str(exc))
        return
    info_columns = st.columns(2)
    info_columns[0].metric(text(lang, "roster"), f"{len(roster)} drivers")
    info_columns[1].caption(text(lang, "scoring"))
    info_columns[1].code(_display_points(scoring), language=None)

    workbook_sha = rw.workbook_fingerprint(workbook_path)
    metadata = rw.RaceMetadata(game, season, league, round_number, event_type, str(gp_name).strip())
    uploads = st.file_uploader(
        text(lang, "screenshots"), type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
        help=text(lang, "screenshots_help"),
        key=f"race_import_uploads_{context_key}_{round_number}_{event_type}_{hashlib.sha1(str(gp_name).encode()).hexdigest()[:6]}",
    )
    upload_bytes = [upload.getvalue() for upload in uploads] if uploads else []
    if uploads:
        preview_columns = st.columns(2)
        for index, (column, upload) in enumerate(zip(preview_columns, uploads[:2]), start=1):
            column.image(upload.getvalue(), caption=f"Screenshot {index} · {upload.name}", width="stretch")
    if len(upload_bytes) != 2:
        st.caption(text(lang, "needs_two"))

    context = {
        "game": game, "season": season, "league": league, "round": round_number, "type": event_type,
        "gp": str(gp_name).strip(), "workbook_sha256": workbook_sha,
        "screenshots": [_sha256_bytes(value) for value in upload_bytes],
    }
    current_context_digest = _context_digest(context)
    action_columns = st.columns([1, 1, 3])
    extract_clicked = action_columns[0].button(text(lang, "extract"), type="primary", disabled=len(upload_bytes) != 2 or not str(gp_name).strip(), key=f"race_import_extract_{current_context_digest[:12]}")
    manual_clicked = action_columns[1].button(text(lang, "manual_review"), disabled=not str(gp_name).strip(), key=f"race_import_manual_{current_context_digest[:12]}")
    action_columns[2].caption(text(lang, "manual_help"))
    if extract_clicked:
        try:
            with st.spinner("Reading screenshots locally…" if lang == "en" else "A ler as capturas localmente…"):
                review_rows, token_count = _draft_from_ocr(upload_bytes, roster)
            st.session_state["race_import_draft"] = {
                "context_digest": current_context_digest, "workbook_sha256": workbook_sha, "rows": review_rows,
                "token_count": token_count, "draft_id": hashlib.sha256((current_context_digest + str(token_count)).encode()).hexdigest()[:12],
            }
            if not any(row["OCR text"] for row in review_rows):
                st.warning(text(lang, "ocr_none"))
        except (race_ocr.OcrUnavailableError, RuntimeError) as exc:
            st.error(str(exc))
    if manual_clicked:
        st.session_state["race_import_draft"] = {
            "context_digest": current_context_digest, "workbook_sha256": workbook_sha,
            "rows": ri.build_review_rows([], len(roster)), "token_count": 0,
            "draft_id": hashlib.sha256((current_context_digest + "manual").encode()).hexdigest()[:12],
        }

    draft = st.session_state.get("race_import_draft")
    if not draft:
        _render_safety_note(lang)
        return
    if draft["context_digest"] != current_context_digest:
        st.warning(text(lang, "stale"))
        _render_safety_note(lang)
        return

    st.subheader(text(lang, "review"))
    st.caption(text(lang, "review_help"))
    unselected_driver = "— Selecionar piloto —" if lang == "pt" else "— Select driver —"
    editor_frame = pd.DataFrame(draft["rows"])
    editor_frame["Driver"] = editor_frame["Driver"].replace("", unselected_driver)
    edited = st.data_editor(
        editor_frame, width="stretch", hide_index=True, num_rows="dynamic",
        column_order=["Position", "Driver", "Suggested driver", "Confidence", "Seen in", "OCR text", "OCR notes"],
        column_config={
            "Position": st.column_config.NumberColumn("Pos.", min_value=1, max_value=len(roster), step=1, required=True, width="small"),
            "Driver": st.column_config.SelectboxColumn("Driver", options=[unselected_driver] + [entry.driver for entry in roster], required=True, width="medium"),
            "Suggested driver": st.column_config.TextColumn("Suggested driver", disabled=True, width="medium"),
            "Confidence": st.column_config.ProgressColumn("OCR confidence", min_value=0.0, max_value=1.0, format="%.0f%%", width="small"),
            "Seen in": st.column_config.TextColumn("Seen in", disabled=True, width="small"),
            "OCR text": st.column_config.TextColumn("OCR text", disabled=True, width="large"),
            "OCR notes": st.column_config.TextColumn("OCR notes", disabled=True, width="large"),
        },
        disabled=["Suggested driver", "Confidence", "Seen in", "OCR text", "OCR notes"], key=f"race_import_editor_{draft['draft_id']}",
    )
    edited_for_validation = edited.copy()
    edited_for_validation["Driver"] = edited_for_validation["Driver"].replace(unselected_driver, "")
    validation = ri.validate_review_rows(edited_for_validation.to_dict("records"), roster, scoring)
    blockers = list(validation.blockers)
    if rw.event_already_exists(standings, metadata):
        blockers.append(text(lang, "existing"))
    if rw.workbook_fingerprint(workbook_path) != draft["workbook_sha256"]:
        blockers.append(text(lang, "changed"))

    st.subheader(text(lang, "final"))
    final_frame = pd.DataFrame(validation.rows).sort_values("Position", na_position="last")
    if not final_frame.empty:
        display_frame = final_frame.copy()
        display_frame["Points"] = display_frame["Points"].map(lambda value: int(value) if float(value).is_integer() else value)
        st.dataframe(display_frame, width="stretch", hide_index=True)
    if blockers:
        st.error(text(lang, "blockers"))
        for blocker in blockers:
            st.markdown(f"- {blocker}")
    else:
        st.success(text(lang, "ready"))

    reviewed_digest = ri.review_digest(validation.rows, context)
    approved = st.checkbox(text(lang, "approve"), key=f"race_import_approval_{reviewed_digest[:16]}")
    commit_clicked = st.button(text(lang, "commit"), type="primary", disabled=bool(blockers) or not approved, key=f"race_import_commit_{reviewed_digest[:16]}")
    if commit_clicked:
        try:
            result = rw.commit_race_import(
                workbook_path, metadata=metadata, rows=validation.rows, scoring_profile=scoring,
                expected_sha256=draft["workbook_sha256"], approved=approved,
            )
        except rw.WorkbookUpdateError as exc:
            st.error(str(exc))
        else:
            calendar_note = (" Calendar marked Done." if lang == "en" else " Calendário marcado como concluído.") if result.calendar_updated else ""
            st.session_state["race_import_success"] = (
                f"{text(lang, 'success')}: {result.rows_added} rows added (Excel {result.first_excel_row}–{result.last_excel_row})."
                f"{calendar_note} Recovery copy: {result.backup_path}"
            )
            st.session_state.pop("race_import_draft", None)
            clear_data_cache()
            st.rerun()
    _render_safety_note(lang)
