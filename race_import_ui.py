"""Streamlit review workflow for local and securely hosted race imports."""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
from typing import Callable, Protocol

import pandas as pd
import streamlit as st
from PIL import Image, UnidentifiedImageError

import dashboard_core as core
import race_github as ghstore
import race_import as ri
import race_ocr
import race_workbook as rw


MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
MAX_SCREENSHOT_PIXELS = 25_000_000


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
        "hosted_intro": "Upload the two PlayStation result screenshots, review every position, then publish one verified race.",
        "hosted_safety": "You are in the private updater. Screenshots are processed for this review and are never saved to GitHub.",
        "hosted_approve": "I reviewed every row and approve publishing these race results.",
        "hosted_commit": "Publish race results",
        "hosted_ready": "All positions and roster drivers are valid. Nothing has been published yet.",
        "hosted_success": "Saved to GitHub. The public dashboard is refreshing now.",
        "open_dashboard": "Open public dashboard",
        "commit_link": "View GitHub commit",
        "github_auth": "Publishing credentials need attention. No data was changed.",
        "github_conflict": "The workbook changed while you reviewed. Reload it and review this race again.",
        "github_unavailable": "GitHub could not confirm the update. No automatic retry was made.",
        "image_invalid": "Each upload must be a valid PNG, JPEG, or WebP image under 10 MB and 25 megapixels.",
        "ocr_details": "OCR details and warnings",
        "view_screenshots": "View screenshots (2)",
        "publishing": "Publishing the approved race…",
        "publish_validate": "Validating the latest workbook and the complete review",
        "publish_commit": "Saving one protected GitHub commit",
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
        "hosted_intro": "Carrega as duas capturas dos resultados da PlayStation, revê todas as posições e publica uma corrida verificada.",
        "hosted_safety": "Estás no atualizador privado. As capturas são processadas nesta revisão e nunca são guardadas no GitHub.",
        "hosted_approve": "Revisei todas as linhas e aprovo a publicação destes resultados.",
        "hosted_commit": "Publicar resultados",
        "hosted_ready": "Todas as posições e todos os pilotos são válidos. Ainda nada foi publicado.",
        "hosted_success": "Guardado no GitHub. O dashboard público está agora a atualizar.",
        "open_dashboard": "Abrir dashboard público",
        "commit_link": "Ver commit no GitHub",
        "github_auth": "As credenciais de publicação precisam de atenção. Nenhum dado foi alterado.",
        "github_conflict": "O Excel mudou durante a revisão. Atualiza a página e revê novamente esta corrida.",
        "github_unavailable": "O GitHub não confirmou a atualização. Não foi feita nenhuma repetição automática.",
        "image_invalid": "Cada ficheiro deve ser uma imagem PNG, JPEG ou WebP válida, com menos de 10 MB e 25 megapíxeis.",
        "ocr_details": "Detalhes e avisos do OCR",
        "view_screenshots": "Ver capturas (2)",
        "publishing": "A publicar a corrida aprovada…",
        "publish_validate": "A validar o Excel mais recente e a revisão completa",
        "publish_commit": "A guardar um único commit protegido no GitHub",
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


def validate_screenshot_bytes(image_bytes: bytes) -> None:
    """Reject oversized or malformed uploads before any OCR model sees them."""
    if not image_bytes or len(image_bytes) > MAX_SCREENSHOT_BYTES:
        raise ValueError("invalid screenshot size")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if (image.format or "").upper() not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("unsupported screenshot format")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_SCREENSHOT_PIXELS:
                raise ValueError("invalid screenshot dimensions")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("invalid screenshot image") from exc


def _render_safety_note(lang: str, *, hosted: bool = False) -> None:
    with st.expander(text(lang, "safety")):
        if hosted:
            copy = (
                "1. O resultado revisto é novamente validado com o Excel mais recente.\n"
                "2. O ficheiro é atualizado apenas se a versão do GitHub continuar igual.\n"
                "3. Só esta corrida e o respetivo estado no calendário são alterados.\n"
                "4. As capturas não são guardadas; o histórico do GitHub permite recuperar o Excel anterior."
                if lang == "pt"
                else "1. The reviewed result is checked again against the latest workbook.\n"
                "2. Publication proceeds only if the GitHub version is still unchanged.\n"
                "3. Only this race and its matching calendar status are changed.\n"
                "4. Screenshots are not stored; Git history preserves the prior workbook."
            )
        else:
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
    source_version: str | None = None,
    hosted_publisher: HostedPublisher | None = None,
    dashboard_url: str = "https://f1-game-dashboard.streamlit.app/",
) -> None:
    """Render a write-free review followed by a local or hosted commit."""
    hosted = hosted_publisher is not None
    if success := st.session_state.pop("race_import_success", None):
        if isinstance(success, dict):
            st.success(str(success.get("message", text(lang, "hosted_success"))))
            link_columns = st.columns(2)
            if success.get("commit_url"):
                link_columns[0].link_button(text(lang, "commit_link"), str(success["commit_url"]), use_container_width=True)
            link_columns[1].link_button(text(lang, "open_dashboard"), dashboard_url, type="primary", use_container_width=True)
        else:
            st.success(success)
    st.header(text(lang, "title"))
    st.write(text(lang, "hosted_intro" if hosted else "intro"))
    st.info(text(lang, "hosted_safety" if hosted else "local"), icon="🔒")

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
    reviewed_source_version = source_version or workbook_sha
    metadata = rw.RaceMetadata(game, season, league, round_number, event_type, str(gp_name).strip())
    st.subheader(text(lang, "screenshots"))
    st.caption(text(lang, "screenshots_help"))
    upload_key = f"{context_key}_{round_number}_{event_type}_{hashlib.sha1(str(gp_name).encode()).hexdigest()[:6]}"
    upload_columns = st.columns(2)
    first_upload = upload_columns[0].file_uploader(
        "Screenshot 1", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=False,
        key=f"race_import_upload_1_{upload_key}",
    )
    second_upload = upload_columns[1].file_uploader(
        "Screenshot 2", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=False,
        key=f"race_import_upload_2_{upload_key}",
    )
    uploads = [upload for upload in (first_upload, second_upload) if upload is not None]
    upload_bytes = [upload.getvalue() for upload in uploads]
    uploads_valid = len(upload_bytes) == 2
    if uploads_valid:
        try:
            for image_bytes in upload_bytes:
                validate_screenshot_bytes(image_bytes)
        except ValueError:
            uploads_valid = False
            st.error(text(lang, "image_invalid"))

    existing_draft = st.session_state.get("race_import_draft")
    if uploads_valid:
        preview_container = st.expander(text(lang, "view_screenshots"), expanded=not bool(existing_draft))
        with preview_container:
            preview_columns = st.columns(2)
            for index, (column, upload) in enumerate(zip(preview_columns, uploads[:2]), start=1):
                column.image(upload.getvalue(), caption=f"Screenshot {index} · {upload.name}", width="stretch")
    if len(upload_bytes) != 2:
        st.caption(text(lang, "needs_two"))

    context = {
        "game": game, "season": season, "league": league, "round": round_number, "type": event_type,
        "gp": str(gp_name).strip(), "workbook_sha256": workbook_sha,
        "source_version": reviewed_source_version,
        "screenshots": [_sha256_bytes(value) for value in upload_bytes],
    }
    current_context_digest = _context_digest(context)
    extract_clicked = st.button(
        text(lang, "extract"), type="primary", use_container_width=True,
        disabled=not uploads_valid or not str(gp_name).strip(), key=f"race_import_extract_{current_context_digest[:12]}",
    )
    manual_clicked = st.button(
        text(lang, "manual_review"), use_container_width=True,
        disabled=not str(gp_name).strip(), key=f"race_import_manual_{current_context_digest[:12]}",
    )
    st.caption(text(lang, "manual_help"))
    if extract_clicked:
        try:
            with st.spinner("Reading screenshots locally…" if lang == "en" else "A ler as capturas localmente…"):
                review_rows, token_count = _draft_from_ocr(upload_bytes, roster)
            st.session_state["race_import_draft"] = {
                "context_digest": current_context_digest, "workbook_sha256": workbook_sha,
                "source_version": reviewed_source_version, "rows": review_rows,
                "token_count": token_count, "draft_id": hashlib.sha256((current_context_digest + str(token_count)).encode()).hexdigest()[:12],
            }
            if not any(row["OCR text"] for row in review_rows):
                st.warning(text(lang, "ocr_none"))
        except (race_ocr.OcrUnavailableError, RuntimeError) as exc:
            st.error(
                ("OCR could not read these screenshots. Try clearer images or start a blank review."
                 if lang == "en" else
                 "O OCR não conseguiu ler estas capturas. Tenta imagens mais nítidas ou inicia uma revisão vazia.")
                if hosted else str(exc)
            )
    if manual_clicked:
        st.session_state["race_import_draft"] = {
            "context_digest": current_context_digest, "workbook_sha256": workbook_sha,
            "source_version": reviewed_source_version,
            "rows": ri.build_review_rows([], len(roster)), "token_count": 0,
            "draft_id": hashlib.sha256((current_context_digest + "manual").encode()).hexdigest()[:12],
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
    compact_editor = editor_frame[["Position", "Driver"]].copy()
    edited_compact = st.data_editor(
        compact_editor, width="stretch", hide_index=True, num_rows="fixed",
        column_order=["Position", "Driver"],
        column_config={
            "Position": st.column_config.NumberColumn("Pos.", min_value=1, max_value=len(roster), step=1, required=True, width="small"),
            "Driver": st.column_config.SelectboxColumn("Driver", options=[unselected_driver] + [entry.driver for entry in roster], required=True, width="medium"),
        },
        key=f"race_import_editor_{draft['draft_id']}",
    )
    unresolved_count = int(edited_compact["Driver"].eq(unselected_driver).sum())
    if unresolved_count:
        st.warning(
            f"{unresolved_count} rows need your driver choice."
            if lang == "en" else f"{unresolved_count} linhas precisam da tua escolha de piloto."
        )
    with st.expander(text(lang, "ocr_details")):
        detail_columns = ["Position", "Suggested driver", "Confidence", "Seen in", "OCR text", "OCR notes"]
        st.dataframe(editor_frame[[column for column in detail_columns if column in editor_frame]], width="stretch", hide_index=True)
    edited_for_validation = editor_frame.copy()
    edited_for_validation[["Position", "Driver"]] = edited_compact[["Position", "Driver"]]
    edited_for_validation["Driver"] = edited_for_validation["Driver"].replace(unselected_driver, "")
    validation = ri.validate_review_rows(edited_for_validation.to_dict("records"), roster, scoring)
    blockers = list(validation.blockers)
    if rw.event_already_exists(standings, metadata):
        blockers.append(text(lang, "existing"))
    if not hosted and rw.workbook_fingerprint(workbook_path) != draft["workbook_sha256"]:
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
        st.success(text(lang, "hosted_ready" if hosted else "ready"))

    reviewed_digest = ri.review_digest(validation.rows, context)
    approved = st.checkbox(text(lang, "hosted_approve" if hosted else "approve"), key=f"race_import_approval_{reviewed_digest[:16]}")
    commit_clicked = st.button(
        text(lang, "hosted_commit" if hosted else "commit"), type="primary", use_container_width=True,
        disabled=bool(blockers) or not approved, key=f"race_import_commit_{reviewed_digest[:16]}",
    )
    if commit_clicked:
        try:
            if hosted and hosted_publisher is not None:
                with st.status(text(lang, "publishing"), expanded=True) as publication_status:
                    st.write(text(lang, "publish_validate"))
                    result = hosted_publisher(
                        metadata,
                        validation.rows,
                        scoring,
                        str(draft["source_version"]),
                        approved,
                    )
                    st.write(text(lang, "publish_commit"))
                    publication_status.update(label=text(lang, "hosted_success"), state="complete", expanded=False)
            else:
                result = rw.commit_race_import(
                    workbook_path, metadata=metadata, rows=validation.rows, scoring_profile=scoring,
                    expected_sha256=draft["workbook_sha256"], approved=approved,
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
                st.session_state["race_import_success"] = {
                    "message": text(lang, "hosted_success"),
                    "commit_url": getattr(result, "commit_url", ""),
                }
            else:
                calendar_note = (" Calendar marked Done." if lang == "en" else " Calendário marcado como concluído.") if result.calendar_updated else ""
                st.session_state["race_import_success"] = (
                    f"{text(lang, 'success')}: {result.rows_added} rows added (Excel {result.first_excel_row}–{result.last_excel_row})."
                    f"{calendar_note} Recovery copy: {result.backup_path}"
                )
            st.session_state.pop("race_import_draft", None)
            clear_data_cache()
            st.rerun()
    _render_safety_note(lang, hosted=hosted)
