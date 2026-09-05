"""Protected Admin task switcher and reviewed management workflows.

This module is imported only after :mod:`admin_page` has established an
authorized server-side Admin session.  It deliberately receives publication
capabilities as callbacks; no public page can construct them.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from datetime import date, datetime, time, timezone
from typing import Any, Protocol

import pandas as pd
import streamlit as st


STATE_PREFIX = "race_import_"
SECTION_KEY = f"{STATE_PREFIX}admin_section"
SETUP_PREFIX = f"{STATE_PREFIX}league_setup_"
CORRECTION_PREFIX = f"{STATE_PREFIX}correction_"

IMPORT_SECTION = "import"
SETUP_SECTION = "setup"
CORRECTION_SECTION = "correction"
ADMIN_SECTIONS = (IMPORT_SECTION, SETUP_SECTION, CORRECTION_SECTION)


class SetupPublisher(Protocol):
    def __call__(
        self,
        draft: Mapping[str, object],
        expected_source_version: str,
        approved: bool,
    ) -> object: ...


class CorrectionPublisher(Protocol):
    def __call__(
        self,
        request: Mapping[str, object],
        expected_source_version: str,
        approved: bool,
    ) -> object: ...


_COPY = {
    "en": {
        "task": "Admin task",
        "import": "Import event",
        "setup": "League & roster setup",
        "correction": "Correct published event",
        "setup_title": "League & roster setup",
        "setup_intro": "Create the next league from a reviewed copy of an existing roster, rules, and calendar. Existing leagues and results are never replaced.",
        "setup_mode": "Setup task",
        "new_league": "Start new league",
        "roster_change": "Define future driver–team lineup",
        "roster_change_help": "Define the complete driver-to-team lineup that will apply from the selected future round. Earlier results and lineups stay unchanged.",
        "source": "Copy from",
        "identity": "League identity",
        "value": "Value",
        "game": "Game / version",
        "season": "Season code",
        "season_start": "Season start date",
        "season_auto_help": "Generated automatically from the season start year and the number of seasons already started in that year.",
        "season_code_error": "The next season code cannot be determined safely: {error}",
        "league": "Unique league name",
        "effective_round": "Effective from round",
        "round": "Round",
        "round_value": "Round {value}",
        "continue": "Continue",
        "back": "Back",
        "reset": "Start over",
        "roster": "Roster and teams",
        "roster_help": "Edit the complete lineup. Add or remove rows, replace drivers, change teams, and enter new team names directly.",
        "aliases": "Alternative screenshot names",
        "aliases_help": "Optional. Add abbreviations or other names shown in screenshots, separated with | or ;. Each alternative must belong to only this driver.",
        "driver": "Driver",
        "team": "Team",
        "position": "Position",
        "points": "Points",
        "scoring": "Scoring rules",
        "race_points": "Race points",
        "sprint_points": "Sprint points",
        "fastest_bonus": "Fastest-lap bonus",
        "bonus_enabled": "Award a fastest-lap bonus",
        "bonus_points": "Bonus points",
        "bonus_eligibility": "Highest eligible finishing position",
        "bonus_any": "Leave 0 to allow any classified driver.",
        "calendar": "Calendar",
        "calendar_help": "Create one ordered row per round. New rows are published as Upcoming.",
        "date": "Date",
        "grand_prix": "Grand Prix",
        "circuit": "Circuit",
        "lisbon_start": "Lisbon start",
        "sprint_weekend": "Sprint weekend",
        "status": "Status",
        "preview": "Review setup",
        "approval": "I reviewed this complete setup and approve publishing one workbook update.",
        "publish": "Publish league setup",
        "setup_ready": "The setup is valid. Nothing has been published yet.",
        "setup_success": "League setup saved to GitHub.",
        "resolve": "Resolve these items before approval",
        "correction_title": "Correct published event",
        "correction_intro": "Choose one published event. Replace its results from corrected screenshots or undo only that event in a new audit commit.",
        "event": "Published event",
        "operation": "Correction",
        "replace": "Replace results",
        "undo": "Undo publication",
        "undo_warning": "Undo removes only this event's result rows. A Race returns its exact Calendar row to Upcoming; a Sprint does not change Calendar status.",
        "undo_closed": "This managed league is no longer Active. You can replace this historical event, but undo is disabled because normal re-import is closed for completed history.",
        "replace_help": "Upload 2 to 4 corrected screenshots from this selected event only.",
        "extract": "Extract corrected standings",
        "old_results": "Currently published results",
        "new_results": "Corrected results",
        "comparison": "Old versus new",
        "correction_approval": "I reviewed this exact correction and approve publishing one workbook update.",
        "publish_correction": "Publish correction",
        "correction_ready": "The correction is valid. Nothing has been published yet.",
        "correction_success": "Correction saved to GitHub.",
        "no_events": "No complete published events are available for correction.",
        "stale": "The workbook or selected source changed. Start this review again.",
        "publisher_error": "The protected publisher could not confirm the update. No automatic retry was made.",
        "history_protected": "Every step is reviewed before one protected GitHub commit. Historical results are unchanged.",
        "step_progress": "Step {step} of 5",
        "no_source": "No source championship is available to copy.",
        "no_roster_round": "This active league has no managed, unpublished Calendar round available for a future lineup.",
        "identity_required": "Game, season code, and league name are required.",
        "identity_exists": "The new league identity already exists.",
        "league_name_unique": "League name must be unique across every current and historical league.",
        "configured_roster_error": "Configured roster data could not be loaded: {error}",
        "roster_active_only": "Future lineups are available only for the Active configuration-backed league. Legacy or completed leagues keep their historical/manual workflow.",
        "roster_minimum": "The lineup needs at least two drivers.",
        "roster_incomplete": "Every lineup row needs a driver and team.",
        "roster_duplicate": "The lineup contains a duplicate driver.",
        "alias_matches_driver": "Alternative name {alias!r} for {driver} matches driver {other_driver}.",
        "alias_duplicate": "Alternative name {alias!r} is assigned to more than one driver.",
        "scoring_positions": "{event_type} scoring must contain every lineup position in order.",
        "scoring_points_invalid": "{event_type} scoring contains an invalid points value.",
        "bonus_invalid": "{event_type} fastest-lap bonus must be greater than zero when enabled.",
        "calendar_round_invalid": "Calendar row {row} needs a numeric round.",
        "calendar_row_incomplete": "Calendar row {row} is incomplete.",
        "calendar_round_order": "Calendar rounds must be ordered and consecutive from 1.",
        "calendar_date_order": "Calendar dates must be in round order.",
        "season_recalculated": "The season code was updated to {season} from the earliest reviewed Calendar date.",
        "current_league_completed": "The current active league will be marked Completed in the same protected update: {leagues}",
        "view_commit": "View GitHub commit",
        "admin_success": "Admin update published.",
        "session": "Session",
        "enabled": "Enabled",
        "highest_eligible": "Highest eligible finish",
        "any_classified": "Any classified",
        "race": "Race",
        "sprint": "Sprint",
        "event_identity_error": "This event identity could not be loaded safely. Reload the latest workbook and try again.",
        "excel_row": "Excel row",
        "finish_position": "Finish position",
        "time": "Time",
        "fastest_lap": "Fastest lap",
        "corrected_uploads": "Corrected event screenshots",
        "view_screenshots": "View corrected screenshots ({count})",
        "upload_count": "Upload between 2 and 4 screenshots from this event only.",
        "reading_screenshots": "Reading corrected screenshots…",
        "no_rows_recognized": "No corrected result rows were recognized.",
        "select_driver": "— Select driver —",
        "driver_choices_needed": "{count} rows need your driver choice.",
        "ocr_details": "OCR confidence and source details",
        "suggested_driver": "Suggested driver",
        "confidence": "Confidence",
        "seen_in": "Seen in",
        "ocr_text": "OCR text",
        "ocr_notes": "OCR notes",
        "suggested_time": "Suggested time",
        "time_confidence": "Time confidence",
        "time_notes": "Time notes",
        "suggested_fastest_lap": "Suggested fastest lap",
        "fastest_lap_confidence": "Fastest-lap confidence",
        "fastest_lap_notes": "Fastest-lap notes",
        "fastest_bonus_award": "Fastest-lap bonus: {driver} +{bonus:g} points",
        "old_driver": "Old driver",
        "new_driver": "New driver",
        "old_team": "Old team",
        "new_team": "New team",
        "old_points": "Old points",
        "new_points": "New points",
        "old_time": "Old time",
        "new_time": "New time",
        "old_fastest_lap": "Old fastest lap",
        "new_fastest_lap": "New fastest lap",
    },
    "pt": {
        "task": "Tarefa de administração",
        "import": "Importar evento",
        "setup": "Configurar liga e grelha",
        "correction": "Corrigir evento publicado",
        "setup_title": "Configurar liga e grelha",
        "setup_intro": "Cria a próxima liga a partir de uma cópia revista da grelha, regras e calendário existentes. As ligas e resultados anteriores nunca são substituídos.",
        "setup_mode": "Tarefa de configuração",
        "new_league": "Iniciar nova liga",
        "roster_change": "Definir grelha futura de pilotos e equipas",
        "roster_change_help": "Define a grelha completa de pilotos e respetivas equipas que será aplicada a partir da ronda futura selecionada. Os resultados e grelhas anteriores não são alterados.",
        "source": "Copiar de",
        "identity": "Identidade da liga",
        "value": "Valor",
        "game": "Jogo / versão",
        "season": "Código da época",
        "season_start": "Data de início da época",
        "season_auto_help": "Gerado automaticamente a partir do ano de início da época e do número de épocas já iniciadas nesse ano.",
        "season_code_error": "Não foi possível determinar com segurança o próximo código da época: {error}",
        "league": "Nome único da liga",
        "effective_round": "Em vigor a partir da ronda",
        "round": "Ronda",
        "round_value": "Ronda {value}",
        "continue": "Continuar",
        "back": "Voltar",
        "reset": "Recomeçar",
        "roster": "Grelha e equipas",
        "roster_help": "Edita a grelha completa. Adiciona ou remove linhas, substitui pilotos, muda equipas e escreve diretamente novos nomes de equipas.",
        "aliases": "Nomes alternativos nas capturas",
        "aliases_help": "Opcional. Adiciona abreviações ou outros nomes vistos nas capturas, separados por | ou ;. Cada alternativa deve pertencer apenas a este piloto.",
        "driver": "Piloto",
        "team": "Equipa",
        "position": "Posição",
        "points": "Pontos",
        "scoring": "Regras de pontuação",
        "race_points": "Pontos da Corrida",
        "sprint_points": "Pontos da Sprint",
        "fastest_bonus": "Bónus de volta mais rápida",
        "bonus_enabled": "Atribuir bónus de volta mais rápida",
        "bonus_points": "Pontos de bónus",
        "bonus_eligibility": "Melhor posição de chegada elegível",
        "bonus_any": "Deixa 0 para permitir qualquer piloto classificado.",
        "calendar": "Calendário",
        "calendar_help": "Cria uma linha ordenada por ronda. As novas linhas são publicadas como Upcoming.",
        "date": "Data",
        "grand_prix": "Grande Prémio",
        "circuit": "Circuito",
        "lisbon_start": "Início em Lisboa",
        "sprint_weekend": "Fim de semana com Sprint",
        "status": "Estado",
        "preview": "Rever configuração",
        "approval": "Revisei toda esta configuração e aprovo a publicação de uma atualização do Excel.",
        "publish": "Publicar configuração da liga",
        "setup_ready": "A configuração é válida. Ainda nada foi publicado.",
        "setup_success": "Configuração da liga guardada no GitHub.",
        "resolve": "Resolve estes pontos antes da aprovação",
        "correction_title": "Corrigir evento publicado",
        "correction_intro": "Escolhe um evento publicado. Substitui os resultados com capturas corrigidas ou anula apenas esse evento num novo commit de auditoria.",
        "event": "Evento publicado",
        "operation": "Correção",
        "replace": "Substituir resultados",
        "undo": "Anular publicação",
        "undo_warning": "Anular remove apenas os resultados deste evento. Uma Corrida volta a colocar a linha exata do Calendário como Upcoming; uma Sprint não altera o Calendário.",
        "undo_closed": "Esta liga gerida já não está Ativa. Podes substituir este evento histórico, mas a anulação está desativada porque a importação normal está fechada para o histórico concluído.",
        "replace_help": "Carrega 2 a 4 capturas corrigidas apenas deste evento selecionado.",
        "extract": "Extrair classificação corrigida",
        "old_results": "Resultados atualmente publicados",
        "new_results": "Resultados corrigidos",
        "comparison": "Antes e depois",
        "correction_approval": "Revisei esta correção exata e aprovo a publicação de uma atualização do Excel.",
        "publish_correction": "Publicar correção",
        "correction_ready": "A correção é válida. Ainda nada foi publicado.",
        "correction_success": "Correção guardada no GitHub.",
        "no_events": "Não existem eventos publicados completos disponíveis para correção.",
        "stale": "O Excel ou a origem selecionada mudou. Recomeça esta revisão.",
        "publisher_error": "O publicador protegido não confirmou a atualização. Não foi feita uma repetição automática.",
        "history_protected": "Cada etapa é revista antes de um único commit protegido no GitHub. Os resultados históricos não são alterados.",
        "step_progress": "Etapa {step} de 5",
        "no_source": "Não existe uma competição de origem disponível para copiar.",
        "no_roster_round": "Esta liga ativa não tem uma ronda futura e não publicada no Calendário disponível para uma nova grelha.",
        "identity_required": "O jogo, o código da época e o nome da liga são obrigatórios.",
        "identity_exists": "A identidade da nova liga já existe.",
        "league_name_unique": "O nome da liga deve ser único entre todas as ligas atuais e históricas.",
        "configured_roster_error": "Não foi possível carregar a grelha configurada: {error}",
        "roster_active_only": "As grelhas futuras só estão disponíveis para a liga Ativa baseada na configuração. As ligas antigas ou concluídas mantêm o fluxo histórico/manual.",
        "roster_minimum": "A grelha precisa de pelo menos dois pilotos.",
        "roster_incomplete": "Todas as linhas da grelha precisam de um piloto e de uma equipa.",
        "roster_duplicate": "A grelha contém um piloto duplicado.",
        "alias_matches_driver": "O nome alternativo {alias!r} de {driver} corresponde ao piloto {other_driver}.",
        "alias_duplicate": "O nome alternativo {alias!r} está atribuído a mais do que um piloto.",
        "scoring_positions": "A pontuação de {event_type} deve conter todas as posições da grelha por ordem.",
        "scoring_points_invalid": "A pontuação de {event_type} contém um valor de pontos inválido.",
        "bonus_invalid": "O bónus de volta mais rápida de {event_type} deve ser superior a zero quando está ativo.",
        "calendar_round_invalid": "A linha {row} do Calendário precisa de uma ronda numérica.",
        "calendar_row_incomplete": "A linha {row} do Calendário está incompleta.",
        "calendar_round_order": "As rondas do Calendário devem estar ordenadas e ser consecutivas a partir de 1.",
        "calendar_date_order": "As datas do Calendário devem estar ordenadas por ronda.",
        "season_recalculated": "O código da época foi atualizado para {season} a partir da primeira data revista do Calendário.",
        "current_league_completed": "A liga ativa atual será marcada como Concluída na mesma atualização protegida: {leagues}",
        "view_commit": "Ver commit no GitHub",
        "admin_success": "Atualização de administração publicada.",
        "session": "Sessão",
        "enabled": "Ativo",
        "highest_eligible": "Melhor chegada elegível",
        "any_classified": "Qualquer piloto classificado",
        "race": "Corrida",
        "sprint": "Sprint",
        "event_identity_error": "Não foi possível carregar a identidade deste evento com segurança. Carrega o Excel mais recente e tenta novamente.",
        "excel_row": "Linha do Excel",
        "finish_position": "Posição final",
        "time": "Tempo",
        "fastest_lap": "Volta mais rápida",
        "corrected_uploads": "Capturas corrigidas do evento",
        "view_screenshots": "Ver capturas corrigidas ({count})",
        "upload_count": "Carrega entre 2 e 4 capturas apenas deste evento.",
        "reading_screenshots": "A ler as capturas corrigidas…",
        "no_rows_recognized": "Não foram reconhecidas linhas de resultados corrigidos.",
        "select_driver": "— Selecionar piloto —",
        "driver_choices_needed": "Falta escolher o piloto em {count} linhas.",
        "ocr_details": "Confiança do OCR e detalhes da origem",
        "suggested_driver": "Piloto sugerido",
        "confidence": "Confiança",
        "seen_in": "Visto em",
        "ocr_text": "Texto do OCR",
        "ocr_notes": "Notas do OCR",
        "suggested_time": "Tempo sugerido",
        "time_confidence": "Confiança do tempo",
        "time_notes": "Notas do tempo",
        "suggested_fastest_lap": "Volta mais rápida sugerida",
        "fastest_lap_confidence": "Confiança da volta mais rápida",
        "fastest_lap_notes": "Notas da volta mais rápida",
        "fastest_bonus_award": "Bónus de volta mais rápida: {driver} +{bonus:g} pontos",
        "old_driver": "Piloto anterior",
        "new_driver": "Novo piloto",
        "old_team": "Equipa anterior",
        "new_team": "Nova equipa",
        "old_points": "Pontos anteriores",
        "new_points": "Novos pontos",
        "old_time": "Tempo anterior",
        "new_time": "Novo tempo",
        "old_fastest_lap": "Volta mais rápida anterior",
        "new_fastest_lap": "Nova volta mais rápida",
    },
}


def _text(lang: str, key: str) -> str:
    return _COPY.get(lang, _COPY["en"]).get(key, _COPY["en"].get(key, key))


def _format_text(lang: str, key: str, **values: object) -> str:
    return _text(lang, key).format(**values)


_SEASON_CODE_PATTERN = re.compile(r"^(?P<year>\d{4})-T(?P<ordinal>\d{2})$")


def derive_next_season_code(
    start_date: date | datetime | pd.Timestamp,
    championships: Sequence[Sequence[object]],
) -> str:
    """Return the next unambiguous ``YYYY-TNN`` code for a start date.

    One code represents one season even when the same identity is present in
    both legacy standings and the managed configuration. The next value is
    one above the highest valid suffix, while malformed labels for the
    requested year are rejected instead of guessing.
    """

    if isinstance(start_date, datetime):
        normalized_date = start_date.date()
    elif isinstance(start_date, pd.Timestamp):
        normalized_date = start_date.date()
    elif isinstance(start_date, date):
        normalized_date = start_date
    else:
        raise ValueError("the season start date is invalid")
    year = normalized_date.year
    owners: dict[str, set[tuple[str, ...]]] = {}
    for championship in championships:
        if len(championship) < 2:
            continue
        label = str(championship[1]).strip()
        if not label:
            continue
        normalized_identity = tuple(
            " ".join(_optional_text(value).casefold().split())
            for value in championship
        )
        owners.setdefault(label, set()).add(normalized_identity)
    ordinals: set[int] = set()
    for label, identities in owners.items():
        match = _SEASON_CODE_PATTERN.fullmatch(label)
        if match is None:
            if label.startswith(str(year)):
                raise ValueError(
                    f"existing season label {label!r} does not use YYYY-TNN"
                )
            continue
        if int(match.group("year")) == year:
            if len(identities) > 1:
                raise ValueError(
                    f"season code {label!r} belongs to multiple championship identities"
                )
            ordinal = int(match.group("ordinal"))
            if ordinal < 1:
                raise ValueError(f"existing season label {label!r} has no ordinal")
            ordinals.add(ordinal)
    ordinal = max(ordinals, default=0) + 1
    if ordinal > 99:
        raise ValueError(f"the {year} season sequence is already full")
    return f"{year}-T{ordinal:02d}"


def _optional_text(value: object) -> str:
    """Normalize one scalar without evaluating ``pandas.NA`` as a boolean."""

    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return ""
    return str(value).strip()


def event_metadata_from_mapping(
    event: Mapping[str, object], *, metadata_class: object | None = None
) -> object:
    """Build correction metadata across Streamlit's hot-reload boundary.

    Streamlit can retain the pre-managed six-field ``RaceMetadata`` class in
    ``sys.modules`` while loading the new Admin page. In that production-only
    transition the seventh positional argument raised the reported TypeError.
    Keyword construction plus a compatibility attribute preserves the exact
    managed League ID until the process has fully restarted.
    """

    import race_metadata

    return race_metadata.from_event_mapping(
        event, metadata_class=metadata_class
    )


_COLUMN_COPY_KEYS = {
    "Excel Row": "excel_row",
    "Finish Pos": "finish_position",
    "Driver": "driver",
    "Team": "team",
    "Points": "points",
    "Position": "position",
    "Time": "time",
    "Fastest Lap": "fastest_lap",
    "OCR Aliases": "aliases",
    "Round": "round",
    "Date": "date",
    "GP Name": "grand_prix",
    "Circuit": "circuit",
    "Time (Lisbon)": "lisbon_start",
    "Has Sprint": "sprint_weekend",
    "Status": "status",
    "Session": "session",
    "Enabled": "enabled",
    "Bonus points": "bonus_points",
    "Highest eligible finish": "highest_eligible",
    "Old driver": "old_driver",
    "New driver": "new_driver",
    "Old team": "old_team",
    "New team": "new_team",
    "Old points": "old_points",
    "New points": "new_points",
    "Old time": "old_time",
    "New time": "new_time",
    "Old fastest lap": "old_fastest_lap",
    "New fastest lap": "new_fastest_lap",
    "Suggested driver": "suggested_driver",
    "Confidence": "confidence",
    "Seen in": "seen_in",
    "OCR text": "ocr_text",
    "OCR notes": "ocr_notes",
    "Suggested Time": "suggested_time",
    "Time Confidence": "time_confidence",
    "Time Notes": "time_notes",
    "Suggested Fastest Lap": "suggested_fastest_lap",
    "Fastest Lap Confidence": "fastest_lap_confidence",
    "Fastest Lap Notes": "fastest_lap_notes",
}


def _localized_frame(frame: pd.DataFrame, lang: str) -> pd.DataFrame:
    labels: dict[str, str] = {}
    for column in frame.columns:
        key = _COLUMN_COPY_KEYS.get(str(column))
        if key:
            labels[str(column)] = _text(lang, key)
    return frame.rename(columns=labels)


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_token(source_version: str) -> str:
    return hashlib.sha256(str(source_version).encode("utf-8")).hexdigest()[:12]


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    clean = frame.copy()
    clean = clean.where(pd.notna(clean), None)
    return [dict(row) for row in clean.to_dict("records")]


def _championships(standings: pd.DataFrame) -> list[tuple[str, str, str]]:
    season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
    required = {"Game", season_column, "League Name"}
    if standings.empty or not required.issubset(standings.columns):
        return []
    values = {
        (
            str(game).strip(),
            str(season).strip(),
            str(league).strip(),
        )
        for game, season, league in standings[
            ["Game", season_column, "League Name"]
        ].itertuples(index=False, name=None)
        if str(game).strip() and str(season).strip() and str(league).strip()
    }
    return sorted(values, key=lambda item: (item[1], item[2], item[0]), reverse=True)


def _setup_championships(
    workbook_path: str, standings: pd.DataFrame
) -> list[tuple[str, str, str]]:
    values = set(_championships(standings))
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        values.update(
            (key.game, key.season, key.league_name)
            for key in league_config.configured_league_keys(tables)
        )
    except Exception:
        # A malformed configuration is surfaced by the backend validator at
        # preview/publication; legacy standings remain available for recovery.
        pass
    return sorted(values, key=lambda item: (item[1], item[2], item[0]), reverse=True)


def _season_code_championships(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame | None,
) -> tuple[tuple[str, str, str], ...]:
    """Include configured, legacy, and exact Calendar-only season identities."""

    values = set(_setup_championships(workbook_path, standings))
    league_identities: dict[str, tuple[str, str, str]] = {}
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        league_identities = {
            key.league_id: (key.game, key.season, key.league_name)
            for key in league_config.configured_league_keys(tables)
        }
    except Exception:
        pass
    if calendar is None or calendar.empty or "Season" not in calendar:
        return tuple(sorted(values))
    for row in calendar.to_dict("records"):
        season = _optional_text(row.get("Season"))
        if not season:
            continue
        league_id = _optional_text(row.get("League ID"))
        configured_identity = league_identities.get(league_id)
        if configured_identity is not None:
            values.add(configured_identity)
            continue
        game = _optional_text(row.get("Game"))
        league = _optional_text(row.get("League Name"))
        exact_owner = f"id:{league_id}" if league_id else league
        if game and exact_owner:
            values.add((game, season, exact_owner))
    return tuple(sorted(values))


def _active_configured_championships(
    workbook_path: str,
) -> list[tuple[str, str, str]]:
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        active_ids = set(
            tables.league_config.loc[
                tables.league_config["Status"]
                .astype(str)
                .str.strip()
                .str.casefold()
                .eq("active"),
                "League ID",
            ]
            .astype(str)
            .str.strip()
        )
        values = [
            (key.game, key.season, key.league_name)
            for key in league_config.configured_league_keys(tables)
            if key.league_id in active_ids
        ]
    except Exception:
        return []
    return sorted(values, key=lambda item: (item[1], item[2], item[0]), reverse=True)


def _format_championship(value: tuple[str, str, str]) -> str:
    game, season, league = value
    return f"{season} · {league} · {game}"


def _clear_prefix(session_state: MutableMapping[object, object], prefix: str) -> None:
    for key in list(session_state):
        if isinstance(key, str) and key.startswith(prefix):
            del session_state[key]


def _reset_roster_dependents(
    session_state: MutableMapping[object, object],
    previous_roster: object,
    reviewed_roster: Sequence[Mapping[str, object]],
) -> bool:
    """Invalidate every downstream editor when the submitted roster changes."""

    previous = previous_roster if isinstance(previous_roster, list) else []
    current = [dict(row) for row in reviewed_roster]
    if _digest(previous) == _digest(current):
        return False
    exact_keys = {
        f"{SETUP_PREFIX}race_scoring",
        f"{SETUP_PREFIX}sprint_scoring",
        f"{SETUP_PREFIX}bonuses",
        f"{SETUP_PREFIX}calendar",
    }
    widget_prefixes = (
        f"{SETUP_PREFIX}race_scoring_editor",
        f"{SETUP_PREFIX}sprint_scoring_editor",
        f"{SETUP_PREFIX}bonus_enabled_",
        f"{SETUP_PREFIX}bonus_points_",
        f"{SETUP_PREFIX}bonus_eligibility_",
        f"{SETUP_PREFIX}calendar_editor",
    )
    for key in list(session_state):
        if isinstance(key, str) and (
            key in exact_keys or key.startswith(widget_prefixes)
        ):
            del session_state[key]
    return True


def _finalize_correction_ocr_attempt(
    session_state: MutableMapping[object, object],
    *,
    upload_key: str,
    upload_generation_key: str,
    upload_generation: int,
    draft_key: str,
    error_key: str,
    error_message: str | None,
) -> None:
    """Retain no correction screenshot bytes after an OCR attempt."""

    upload_prefix = f"{CORRECTION_PREFIX}uploads_"
    for key in list(session_state):
        if isinstance(key, str) and (
            key == upload_key or key.startswith(upload_prefix)
        ):
            del session_state[key]
    session_state[upload_generation_key] = int(upload_generation) + 1
    if error_message is None:
        session_state.pop(error_key, None)
        return

    # A failed fresh extraction invalidates an older review for the same
    # event. Only a non-sensitive, one-shot text error survives the rerun.
    session_state.pop(draft_key, None)
    message = str(error_message).strip()
    session_state[error_key] = message or (
        "OCR could not finish reading these screenshots. Upload a fresh set and try again."
    )


def _clear_stale_correction_uploads(
    session_state: MutableMapping[object, object],
    *,
    current_upload_key: str,
) -> None:
    """Discard old correction upload contexts while preserving the current one."""

    upload_prefix = f"{CORRECTION_PREFIX}uploads_"
    current_prefix = f"{current_upload_key}:"
    for key in list(session_state):
        if not isinstance(key, str) or not key.startswith(upload_prefix):
            continue
        if key == current_upload_key or key.startswith(current_prefix):
            continue
        del session_state[key]


def _canonical_alias_text(value: object) -> str:
    import league_config

    return league_config.serialize_ocr_aliases(
        league_config.parse_ocr_aliases(value)
    )


def _roster_alias_errors(
    records: Sequence[Mapping[str, object]],
    *,
    lang: str = "en",
) -> list[str]:
    """Return friendly alias collisions before the backend preview boundary."""

    import league_config

    canonical = {
        league_config.normalize_identity(row.get("Driver")): str(
            row.get("Driver") or ""
        ).strip()
        for row in records
        if league_config.normalize_identity(row.get("Driver"))
    }
    alias_owner: dict[str, str] = {}
    errors: list[str] = []
    for row in records:
        driver = str(row.get("Driver") or "").strip()
        driver_key = league_config.normalize_identity(driver)
        for alias in league_config.parse_ocr_aliases(row.get("OCR Aliases", "")):
            alias_key = league_config.normalize_identity(alias)
            other_driver = canonical.get(alias_key)
            if other_driver and alias_key != driver_key:
                errors.append(
                    _format_text(
                        lang,
                        "alias_matches_driver",
                        alias=alias,
                        driver=driver,
                        other_driver=other_driver,
                    )
                )
            previous = alias_owner.get(alias_key)
            if previous and previous != driver_key:
                errors.append(
                    _format_text(lang, "alias_duplicate", alias=alias)
                )
            alias_owner[alias_key] = driver_key
    return list(dict.fromkeys(errors))


def render_admin_management(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    clear_data_cache: Callable[[], None],
    source_version: str,
    import_publisher: Callable[..., object],
    setup_publisher: SetupPublisher | None = None,
    correction_publisher: CorrectionPublisher | None = None,
    dashboard_url: str,
    import_renderer: Callable[..., None] | None = None,
    setup_renderer: Callable[..., None] | None = None,
    correction_renderer: Callable[..., None] | None = None,
) -> None:
    """Render exactly one protected workflow for the authorized Admin."""

    success = st.session_state.pop(f"{STATE_PREFIX}management_success", None)
    if isinstance(success, Mapping):
        st.success(str(success.get("message") or _text(lang, "admin_success")))
        if success.get("commit_url"):
            st.link_button(
                _text(lang, "view_commit"),
                str(success["commit_url"]),
                use_container_width=True,
            )

    labels = {
        IMPORT_SECTION: _text(lang, "import"),
        SETUP_SECTION: _text(lang, "setup"),
        CORRECTION_SECTION: _text(lang, "correction"),
    }
    selected = st.radio(
        _text(lang, "task"),
        ADMIN_SECTIONS,
        horizontal=True,
        format_func=labels.__getitem__,
        key=SECTION_KEY,
    )

    if selected == IMPORT_SECTION:
        if import_renderer is None:
            import race_import_ui

            import_renderer = race_import_ui.render_race_import
        import_renderer(
            workbook_path,
            standings,
            calendar,
            lang=lang,
            clear_data_cache=clear_data_cache,
            source_version=source_version,
            hosted_publisher=import_publisher,
            dashboard_url=dashboard_url,
        )
        return

    if selected == SETUP_SECTION:
        renderer = setup_renderer or render_league_setup
        renderer(
            workbook_path,
            standings,
            calendar,
            lang=lang,
            clear_data_cache=clear_data_cache,
            source_version=source_version,
            hosted_publisher=setup_publisher,
        )
        return

    renderer = correction_renderer or render_event_correction
    renderer(
        workbook_path,
        standings,
        calendar,
        lang=lang,
        clear_data_cache=clear_data_cache,
        source_version=source_version,
        hosted_publisher=correction_publisher,
    )


def render_league_setup(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    clear_data_cache: Callable[[], None],
    source_version: str,
    hosted_publisher: SetupPublisher | None,
) -> None:
    """Render the submitted-step league setup wizard.

    Backend validation and publication are intentionally injected.  The UI
    stores only submitted, reviewable mappings under the protected state
    prefix; publication must validate them again against the remote workbook.
    """

    st.header(_text(lang, "setup_title"))
    st.write(_text(lang, "setup_intro"))
    st.info(
        _text(lang, "history_protected"),
        icon=":material/history:",
    )

    token = _source_token(source_version)
    token_key = f"{SETUP_PREFIX}source_token"
    if st.session_state.get(token_key) != token:
        _clear_prefix(st.session_state, SETUP_PREFIX)
        st.session_state[token_key] = token
    step_key = f"{SETUP_PREFIX}step"
    step = int(st.session_state.get(step_key, 1))
    st.progress(
        min(max(step, 1), 5) / 5,
        text=_format_text(lang, "step_progress", step=step),
    )

    options = _setup_championships(workbook_path, standings)
    if not options:
        st.error(_text(lang, "no_source"))
        return
    active_options = _active_configured_championships(workbook_path)

    if step == 1:
        _render_setup_identity(
            workbook_path,
            standings,
            calendar,
            options,
            active_options,
            lang=lang,
            source_version=source_version,
        )
    elif step == 2:
        _render_setup_roster(workbook_path, standings, lang=lang)
    elif step == 3:
        _render_setup_scoring(workbook_path, standings, lang=lang)
    elif step == 4:
        _render_setup_calendar(
            workbook_path, standings, calendar, lang=lang
        )
    else:
        _render_setup_preview(
            workbook_path=workbook_path,
            standings=standings,
            lang=lang,
            source_version=source_version,
            hosted_publisher=hosted_publisher,
            clear_data_cache=clear_data_cache,
        )


def _render_setup_identity(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    options: Sequence[tuple[str, str, str]],
    active_options: Sequence[tuple[str, str, str]],
    *,
    lang: str,
    source_version: str,
) -> None:
    saved = st.session_state.get(f"{SETUP_PREFIX}identity")
    saved = saved if isinstance(saved, Mapping) else {}
    saved_source = tuple(saved.get("source", options[0]))
    saved_mode = str(saved.get("mode") or "new")
    with st.form(f"{SETUP_PREFIX}identity_form_{_source_token(source_version)}"):
        mode = st.radio(
            _text(lang, "setup_mode"),
            ["new", "roster"],
            index=1 if saved_mode == "roster" else 0,
            format_func=lambda item: _text(
                lang, "new_league" if item == "new" else "roster_change"
            ),
            horizontal=True,
            key=f"{SETUP_PREFIX}identity_mode",
        )
        source_options = list(active_options if mode == "roster" else options)
        source_index = (
            source_options.index(saved_source)
            if saved_source in source_options
            else 0
        )
        source = st.selectbox(
            _text(lang, "source"),
            source_options,
            index=source_index,
            format_func=_format_championship,
            key=f"{SETUP_PREFIX}identity_source",
        )
        if source is None:
            source_game = source_season = source_league = ""
        else:
            source_game, source_season, source_league = source
        season_error = ""
        season_start_date: date | None = None
        if mode == "new":
            saved_start = pd.to_datetime(
                saved.get("season_start_date"), errors="coerce"
            )
            season_start_default = (
                saved_start.date() if not pd.isna(saved_start) else date.today()
            )
            first_row = st.columns(2)
            game = first_row[0].text_input(
                _text(lang, "game"),
                value=str(saved.get("game", source_game)),
                key=f"{SETUP_PREFIX}identity_game",
            )
            season_start_date = first_row[1].date_input(
                _text(lang, "season_start"),
                value=season_start_default,
                key=f"{SETUP_PREFIX}identity_season_start",
            )
            try:
                derived_season = derive_next_season_code(
                    season_start_date,
                    _season_code_championships(
                        workbook_path, standings, calendar
                    ),
                )
            except ValueError as exc:
                derived_season = ""
                season_error = _format_text(
                    lang, "season_code_error", error=exc
                )
            second_row = st.columns(2)
            second_row[0].text_input(
                _text(lang, "season"),
                value=derived_season,
                disabled=True,
                help=_text(lang, "season_auto_help"),
                key=f"{SETUP_PREFIX}identity_season_{derived_season or 'invalid'}",
            )
            season = derived_season
            league = second_row[1].text_input(
                _text(lang, "league"),
                value=str(saved.get("league", "")),
                key=f"{SETUP_PREFIX}identity_league",
            )
            if season_error:
                st.error(season_error)
            else:
                st.caption(_text(lang, "season_auto_help"))
            effective_round = 1
        else:
            game, season, league = source_game, source_season, source_league
            st.caption(_text(lang, "roster_change_help"))
            round_options = _managed_roster_rounds(
                workbook_path, standings, calendar, source
            )
            saved_effective = int(saved.get("effective_round", 0) or 0)
            round_index = (
                round_options.index(saved_effective)
                if saved_mode == "roster" and saved_effective in round_options
                else 0
            )
            effective_round = st.selectbox(
                _text(lang, "effective_round"),
                round_options,
                index=round_index,
                format_func=lambda value: _format_text(
                    lang, "round_value", value=value
                ),
                key=f"{SETUP_PREFIX}identity_effective_round",
            )
            if effective_round is None:
                st.warning(_text(lang, "no_roster_round"))
        submitted = st.form_submit_button(
            _text(lang, "continue"),
            type="primary",
            use_container_width=True,
            disabled=bool(season_error)
            or source is None
            or (mode == "roster" and effective_round is None),
        )
    if not submitted:
        return

    errors: list[str] = []
    identity = {
        "mode": mode,
        "source": list(source),
        "game": str(game).strip(),
        "season": str(season).strip(),
        "league": str(league).strip(),
        "effective_round": int(effective_round or 1),
        "season_start_date": (
            season_start_date.isoformat()
            if mode == "new" and season_start_date is not None
            else ""
        ),
        "created_utc": str(
            saved.get("created_utc")
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
    }
    if not identity["game"] or not identity["season"] or not identity["league"]:
        errors.append(_text(lang, "identity_required"))
    existing = {
        (str(game).strip().casefold(), str(season).strip().casefold(), str(league).strip().casefold())
        for game, season, league in _championships(standings)
    }
    candidate = (
        str(identity["game"]).casefold(),
        str(identity["season"]).casefold(),
        str(identity["league"]).casefold(),
    )
    if mode == "new" and candidate in existing:
        errors.append(_text(lang, "identity_exists"))
    if mode == "new":
        try:
            import league_config

            normalize_league = league_config.normalize_identity
        except Exception:
            normalize_league = lambda value: " ".join(
                str(value or "").casefold().split()
            )
        used_league_names = {
            normalize_league(existing_league)
            for _, _, existing_league in options
        }
        if normalize_league(identity["league"]) in used_league_names:
            errors.append(_text(lang, "league_name_unique"))
    if mode == "roster":
        try:
            import league_config

            tables = league_config.load_config_tables(workbook_path)
            active_ids = set(
                tables.league_config.loc[
                    tables.league_config["Status"]
                    .astype(str)
                    .str.strip()
                    .str.casefold()
                    .eq("active"),
                    "League ID",
                ].astype(str)
            )
            configured_identities = {
                (key.game, key.season, key.league_name)
                for key in league_config.configured_league_keys(tables)
                if key.league_id in active_ids
            }
        except Exception as exc:
            errors.append(
                _format_text(lang, "configured_roster_error", error=exc)
            )
        else:
            if tuple(source) not in configured_identities:
                errors.append(_text(lang, "roster_active_only"))
    if errors:
        for error in errors:
            st.error(error)
        return
    st.session_state[f"{SETUP_PREFIX}identity"] = identity
    for suffix in ("roster", "race_scoring", "sprint_scoring", "bonuses", "calendar"):
        st.session_state.pop(f"{SETUP_PREFIX}{suffix}", None)
    st.session_state[f"{SETUP_PREFIX}step"] = 2
    st.rerun()


def _matching_championship_rows(
    standings: pd.DataFrame, source: Sequence[object]
) -> pd.DataFrame:
    if len(source) != 3 or standings.empty:
        return standings.iloc[0:0].copy()
    game, season, league = map(str, source)
    season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
    selected = standings[
        standings["Game"].astype(str).eq(game)
        & standings[season_column].astype(str).eq(season)
        & standings["League Name"].astype(str).eq(league)
    ].copy()
    if "IsSeasonFinal" in selected:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    return selected


def _managed_roster_rounds(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    source: Sequence[object] | None,
) -> list[int]:
    """Return exact managed Upcoming rounds eligible for a future snapshot."""

    if source is None or len(source) != 3 or calendar.empty:
        return []
    game, season, league = map(str, source)
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        source_key = next(
            (
                key
                for key in league_config.configured_league_keys(tables)
                if (key.game, key.season, key.league_name)
                == (game, season, league)
            ),
            None,
        )
        if source_key is None:
            return []
        selected_config = tables.league_config[
            tables.league_config["League ID"]
            .astype(str)
            .str.strip()
            .eq(source_key.league_id)
        ]
        if len(selected_config) != 1 or (
            str(selected_config.iloc[0]["Status"]).strip().casefold() != "active"
        ):
            return []
        configured_rows = tables.roster_config[
            tables.roster_config["League ID"]
            .astype(str)
            .str.strip()
            .eq(source_key.league_id)
        ]
        configured_rounds = pd.to_numeric(
            configured_rows["Effective From Round"], errors="coerce"
        ).dropna()
    except Exception:
        return []
    published = _matching_championship_rows(standings, source)
    published_rounds = pd.to_numeric(
        published.get("Round", pd.Series(dtype=object)), errors="coerce"
    ).dropna()
    minimum = 1
    if not configured_rounds.empty:
        minimum = max(minimum, int(configured_rounds.max()) + 1)
    if not published_rounds.empty:
        minimum = max(minimum, int(published_rounds.max()) + 1)
    if "League ID" not in calendar:
        return []
    selected = calendar[
        calendar["League ID"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq(source_key.league_id)
        & pd.to_numeric(calendar["Round"], errors="coerce").ge(minimum)
    ].copy()
    if "Game" in selected:
        selected = selected[selected["Game"].astype(str).eq(game)]
    if "Season" in selected:
        selected = selected[selected["Season"].astype(str).eq(season)]
    if "League Name" in selected:
        selected = selected[selected["League Name"].astype(str).eq(league)]
    if "Status" not in selected:
        return []
    selected = selected[
        selected["Status"].astype(str).str.strip().str.casefold().eq("upcoming")
    ]
    return sorted(
        pd.to_numeric(selected["Round"], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )


def _next_unpublished_round(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    source: Sequence[object],
) -> int:
    published = _matching_championship_rows(standings, source)
    published_rounds = pd.to_numeric(
        published.get("Round", pd.Series(dtype=object)), errors="coerce"
    ).dropna()
    minimum = int(published_rounds.max()) + 1 if not published_rounds.empty else 1
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        source_key = next(
            (
                key
                for key in league_config.configured_league_keys(tables)
                if (key.game, key.season, key.league_name) == tuple(map(str, source))
            ),
            None,
        )
        if source_key is not None:
            configured = tables.roster_config[
                tables.roster_config["League ID"]
                .astype(str)
                .eq(source_key.league_id)
            ]
            configured_rounds = pd.to_numeric(
                configured["Effective From Round"], errors="coerce"
            ).dropna()
            if not configured_rounds.empty:
                minimum = max(minimum, int(configured_rounds.max()) + 1)
    except Exception:
        pass
    if calendar.empty or len(source) != 3:
        return minimum
    game, season, league = map(str, source)
    selected = calendar[
        calendar["League Name"].astype(str).eq(league)
        & pd.to_numeric(calendar["Round"], errors="coerce").ge(minimum)
    ].copy()
    if "Game" in selected and selected["Game"].astype(str).str.strip().ne("").any():
        selected = selected[selected["Game"].astype(str).eq(game)]
    if "Season" in selected and selected["Season"].astype(str).str.strip().ne("").any():
        selected = selected[selected["Season"].astype(str).eq(season)]
    if "Status" in selected:
        selected = selected[
            ~selected["Status"].astype(str).str.strip().str.casefold().eq("done")
        ]
    next_rounds = pd.to_numeric(selected.get("Round"), errors="coerce").dropna()
    return int(next_rounds.min()) if not next_rounds.empty else minimum


def _source_rows(
    workbook_path: str,
    standings: pd.DataFrame,
    identity: Mapping[str, object],
) -> pd.DataFrame:
    game, season, league = map(str, identity["source"])
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        source_key = next(
            (
                key
                for key in league_config.configured_league_keys(tables)
                if (key.game, key.season, key.league_name) == (game, season, league)
            ),
            None,
        )
        if source_key is not None:
            if identity.get("mode") == "new":
                source_rows = tables.roster_config[
                    tables.roster_config["League ID"]
                    .astype(str)
                    .eq(source_key.league_id)
                ]
                effective_round = int(
                    pd.to_numeric(
                        source_rows["Effective From Round"], errors="raise"
                    ).max()
                )
            else:
                effective_round = int(identity.get("effective_round", 1))
            configured = league_config.resolve_roster_snapshot(
                tables,
                source_key.league_id,
                max(1, effective_round),
            )
            return pd.DataFrame(
                [
                    {
                        "Driver": row.driver_name,
                        "Team": row.team_name,
                        "OCR Aliases": league_config.serialize_ocr_aliases(
                            row.ocr_aliases
                        ),
                    }
                    for row in configured
                ]
            )
    except Exception:
        pass
    season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
    selected = standings[
        standings["Game"].astype(str).eq(game)
        & standings[season_column].astype(str).eq(season)
        & standings["League Name"].astype(str).eq(league)
    ].copy()
    if "IsSeasonFinal" in selected:
        selected = selected[~selected["IsSeasonFinal"].fillna(False)]
    if "Type" in selected:
        races = selected[selected["Type"].fillna("R").astype(str).str.upper().eq("R")]
        if not races.empty:
            selected = races
    if selected.empty:
        return pd.DataFrame(columns=["Driver", "Team", "OCR Aliases"])
    latest_round = pd.to_numeric(selected["Round"], errors="coerce").max()
    latest = selected[pd.to_numeric(selected["Round"], errors="coerce").eq(latest_round)]
    legacy = (
        latest[["Driver", "Team"]]
        .dropna()
        .drop_duplicates("Driver", keep="last")
        .sort_values("Driver")
        .reset_index(drop=True)
    )
    legacy["OCR Aliases"] = ""
    return legacy


def _navigation(lang: str, step: int) -> tuple[bool, bool]:
    columns = st.columns(2)
    back = columns[0].button(
        _text(lang, "back"), key=f"{SETUP_PREFIX}back_{step}", use_container_width=True
    )
    forward = columns[1].button(
        _text(lang, "continue"),
        key=f"{SETUP_PREFIX}continue_{step}",
        type="primary",
        use_container_width=True,
    )
    return back, forward


def _render_setup_roster(
    workbook_path: str, standings: pd.DataFrame, *, lang: str
) -> None:
    identity = st.session_state.get(f"{SETUP_PREFIX}identity")
    if not isinstance(identity, Mapping):
        st.session_state[f"{SETUP_PREFIX}step"] = 1
        st.rerun()
        return
    default = st.session_state.get(f"{SETUP_PREFIX}roster")
    frame = (
        pd.DataFrame(default)
        if isinstance(default, list)
        else _source_rows(workbook_path, standings, identity)
    )
    st.subheader(_text(lang, "roster"))
    st.caption(_text(lang, "roster_help"))
    st.caption(_text(lang, "aliases_help"))
    editor_frame = frame.copy()
    for column in ("Driver", "Team", "OCR Aliases"):
        if column not in editor_frame:
            editor_frame[column] = ""
    edited = st.data_editor(
        editor_frame[["Driver", "Team", "OCR Aliases"]],
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Driver": st.column_config.TextColumn(
                _text(lang, "driver"), required=True
            ),
            "Team": st.column_config.TextColumn(
                _text(lang, "team"), required=True
            ),
            "OCR Aliases": st.column_config.TextColumn(
                _text(lang, "aliases"),
                help=_text(lang, "aliases_help"),
                required=False,
            ),
        },
        key=f"{SETUP_PREFIX}roster_editor",
    )
    back, forward = _navigation(lang, 2)
    if back:
        st.session_state[f"{SETUP_PREFIX}step"] = 1
        st.rerun()
    if not forward:
        return
    records = []
    for row in _frame_records(edited):
        driver = str(row.get("Driver") or "").strip()
        team = str(row.get("Team") or "").strip()
        aliases = _canonical_alias_text(row.get("OCR Aliases", ""))
        if driver or team or aliases:
            records.append(
                {
                    "Driver": driver,
                    "Team": team,
                    "OCR Aliases": aliases,
                }
            )
    drivers = [str(row["Driver"]) for row in records]
    errors = []
    if len(records) < 2:
        errors.append(_text(lang, "roster_minimum"))
    if any(not row["Driver"] or not row["Team"] for row in records):
        errors.append(_text(lang, "roster_incomplete"))
    normalized = [" ".join(name.casefold().split()) for name in drivers]
    if len(normalized) != len(set(normalized)):
        errors.append(_text(lang, "roster_duplicate"))
    errors.extend(_roster_alias_errors(records, lang=lang))
    if errors:
        for error in errors:
            st.error(error)
        return
    previous_roster = st.session_state.get(f"{SETUP_PREFIX}roster")
    _reset_roster_dependents(st.session_state, previous_roster, records)
    st.session_state[f"{SETUP_PREFIX}roster"] = records
    st.session_state[f"{SETUP_PREFIX}step"] = 3
    st.rerun()


def _default_scoring(event_type: str, grid_size: int) -> pd.DataFrame:
    base = (
        {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
        if event_type == "SR"
        else {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
    )
    return pd.DataFrame(
        {"Position": range(1, grid_size + 1), "Points": [float(base.get(position, 0)) for position in range(1, grid_size + 1)]}
    )


def _source_scoring_seed(
    workbook_path: str,
    identity: Mapping[str, object],
    event_type: str,
    grid_size: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Copy the latest configured rule as an editable, complete grid."""

    default = _default_scoring(event_type, grid_size)
    no_bonus: dict[str, object] = {
        "enabled": False,
        "points": 0.0,
        "eligibility_max_position": 0,
    }
    try:
        import league_config

        tables = league_config.load_config_tables(workbook_path)
        source = tuple(map(str, identity.get("source", ())))
        source_key = next(
            (
                key
                for key in league_config.configured_league_keys(tables)
                if (key.game, key.season, key.league_name) == source
            ),
            None,
        )
        if source_key is None:
            return default, no_bonus
        if identity.get("mode") == "roster":
            source_round = max(1, int(identity.get("effective_round", 1)))
        else:
            round_values = []
            for frame in (tables.roster_config, tables.scoring_profiles):
                selected = frame[
                    frame["League ID"].astype(str).eq(source_key.league_id)
                ]
                round_values.extend(
                    pd.to_numeric(
                        selected["Effective From Round"], errors="coerce"
                    )
                    .dropna()
                    .astype(int)
                    .tolist()
                )
            source_round = max(round_values, default=1)
        source_roster = league_config.resolve_roster_snapshot(
            tables, source_key.league_id, source_round
        )
        resolved = league_config.resolve_scoring_profile(
            tables,
            source_key.league_id,
            event_type,
            source_round,
            len(source_roster),
        )
    except Exception:
        return default, no_bonus
    points = resolved.points
    frame = pd.DataFrame(
        {
            "Position": range(1, grid_size + 1),
            "Points": [
                float(points.get(position, 0.0))
                for position in range(1, grid_size + 1)
            ],
        }
    )
    return frame, {
        "enabled": resolved.fastest_lap_bonus > 0,
        "points": float(resolved.fastest_lap_bonus),
        "eligibility_max_position": min(
            grid_size, int(resolved.fastest_lap_max_finish or 0)
        ),
    }


def _render_setup_scoring(
    workbook_path: str, standings: pd.DataFrame, *, lang: str
) -> None:
    del standings
    roster = st.session_state.get(f"{SETUP_PREFIX}roster")
    identity = st.session_state.get(f"{SETUP_PREFIX}identity")
    if not isinstance(roster, list):
        st.session_state[f"{SETUP_PREFIX}step"] = 2
        st.rerun()
        return
    if not isinstance(identity, Mapping):
        st.session_state[f"{SETUP_PREFIX}step"] = 1
        st.rerun()
        return
    st.subheader(_text(lang, "scoring"))
    roster_token = _digest(roster)[:10]
    columns = st.columns(2)
    saved_race = st.session_state.get(f"{SETUP_PREFIX}race_scoring")
    saved_sprint = st.session_state.get(f"{SETUP_PREFIX}sprint_scoring")
    race_seed, race_bonus_seed = _source_scoring_seed(
        workbook_path, identity, "R", len(roster)
    )
    sprint_seed, sprint_bonus_seed = _source_scoring_seed(
        workbook_path, identity, "SR", len(roster)
    )
    with columns[0]:
        st.caption(_text(lang, "race_points"))
        race_frame = (
            pd.DataFrame(saved_race) if isinstance(saved_race, list) else race_seed
        )
        race_edited = st.data_editor(
            race_frame,
            hide_index=True,
            width="stretch",
            disabled=["Position"],
            column_config={
                "Position": st.column_config.NumberColumn(
                    _text(lang, "position")
                ),
                "Points": st.column_config.NumberColumn(
                    _text(lang, "points"), min_value=0.0
                ),
            },
            key=f"{SETUP_PREFIX}race_scoring_editor_{roster_token}",
        )
    with columns[1]:
        st.caption(_text(lang, "sprint_points"))
        sprint_frame = (
            pd.DataFrame(saved_sprint)
            if isinstance(saved_sprint, list)
            else sprint_seed
        )
        sprint_edited = st.data_editor(
            sprint_frame,
            hide_index=True,
            width="stretch",
            disabled=["Position"],
            column_config={
                "Position": st.column_config.NumberColumn(
                    _text(lang, "position")
                ),
                "Points": st.column_config.NumberColumn(
                    _text(lang, "points"), min_value=0.0
                ),
            },
            key=f"{SETUP_PREFIX}sprint_scoring_editor_{roster_token}",
        )
    st.caption(_text(lang, "fastest_bonus"))
    bonus_columns = st.columns(2)
    saved_bonus = st.session_state.get(f"{SETUP_PREFIX}bonuses")
    saved_bonus = saved_bonus if isinstance(saved_bonus, Mapping) else {}
    bonuses: dict[str, dict[str, object]] = {}
    for column, event_type, label in zip(
        bonus_columns,
        ("R", "SR"),
        (_text(lang, "race_points"), _text(lang, "sprint_points")),
    ):
        with column:
            st.markdown(f"**{label}**")
            seed_bonus = race_bonus_seed if event_type == "R" else sprint_bonus_seed
            current = saved_bonus.get(event_type, seed_bonus)
            current = current if isinstance(current, Mapping) else {}
            enabled = st.checkbox(
                _text(lang, "bonus_enabled"),
                value=bool(current.get("enabled", False)),
                key=f"{SETUP_PREFIX}bonus_enabled_{event_type}_{roster_token}",
            )
            points = st.number_input(
                _text(lang, "bonus_points"),
                min_value=0.0,
                step=0.5,
                value=float(current.get("points", 0.0)),
                disabled=not enabled,
                key=f"{SETUP_PREFIX}bonus_points_{event_type}_{roster_token}",
            )
            eligible = st.number_input(
                _text(lang, "bonus_eligibility"),
                min_value=0,
                max_value=len(roster),
                step=1,
                value=int(current.get("eligibility_max_position", 0)),
                disabled=not enabled,
                help=_text(lang, "bonus_any"),
                key=f"{SETUP_PREFIX}bonus_eligibility_{event_type}_{roster_token}",
            )
            bonuses[event_type] = {
                "enabled": enabled,
                "points": float(points) if enabled else 0.0,
                "eligibility_max_position": int(eligible) if enabled else 0,
            }
    back, forward = _navigation(lang, 3)
    if back:
        st.session_state[f"{SETUP_PREFIX}step"] = 2
        st.rerun()
    if not forward:
        return
    errors: list[str] = []
    scoring: dict[str, list[dict[str, object]]] = {}
    for event_type, frame in (("R", race_edited), ("SR", sprint_edited)):
        records = _frame_records(frame)
        positions = [int(row.get("Position", 0) or 0) for row in records]
        points = [pd.to_numeric(row.get("Points"), errors="coerce") for row in records]
        if positions != list(range(1, len(roster) + 1)):
            errors.append(
                _format_text(
                    lang, "scoring_positions", event_type=event_type
                )
            )
        if any(pd.isna(value) or float(value) < 0 for value in points):
            errors.append(
                _format_text(
                    lang, "scoring_points_invalid", event_type=event_type
                )
            )
        scoring[event_type] = [
            {"Position": position, "Points": float(value)}
            for position, value in zip(positions, points)
            if not pd.isna(value)
        ]
    for event_type, rule in bonuses.items():
        if rule["enabled"] and float(rule["points"]) <= 0:
            errors.append(
                _format_text(lang, "bonus_invalid", event_type=event_type)
            )
    if errors:
        for error in errors:
            st.error(error)
        return
    st.session_state[f"{SETUP_PREFIX}race_scoring"] = scoring["R"]
    st.session_state[f"{SETUP_PREFIX}sprint_scoring"] = scoring["SR"]
    st.session_state[f"{SETUP_PREFIX}bonuses"] = bonuses
    st.session_state[f"{SETUP_PREFIX}step"] = (
        5 if identity.get("mode") == "roster" else 4
    )
    st.rerun()


def _calendar_seed(
    calendar: pd.DataFrame,
    identity: Mapping[str, object],
    *,
    championship_identities: Sequence[tuple[str, str, str]] = (),
    source_league_id: str = "",
) -> pd.DataFrame:
    source_game, source_season, source_league = map(str, identity["source"])
    selected = (
        calendar[calendar["League Name"].astype(str).eq(source_league)].copy()
        if not calendar.empty and "League Name" in calendar
        else pd.DataFrame()
    )
    same_name_identities = {
        (game, season, league)
        for game, season, league in championship_identities
        if " ".join(str(league).casefold().split())
        == " ".join(source_league.casefold().split())
    }
    if len(same_name_identities) > 1 and not selected.empty:
        unsafe_rows = []
        for row in selected.to_dict("records"):
            exact_config_id = bool(source_league_id) and (
                str(row.get("League ID") or "").strip() == source_league_id
            )
            exact_legacy_identity = (
                str(row.get("Game") or "").strip() == source_game
                and str(row.get("Season") or "").strip() == source_season
            )
            if not exact_config_id and not exact_legacy_identity:
                unsafe_rows.append(row)
        if unsafe_rows:
            raise ValueError(
                "This reused League Name has legacy Calendar rows without an exact Game/Season/League ID. "
                "Update those Calendar identities manually before cloning this league."
            )
    if (
        not selected.empty
        and source_league_id
        and "League ID" in selected
        and selected["League ID"].astype(str).str.strip().ne("").any()
    ):
        selected = selected[
            selected["League ID"].astype(str).str.strip().eq(source_league_id)
        ]
    if not selected.empty and "Game" in selected:
        identified = selected["Game"].astype(str).str.strip().ne("")
        if identified.any():
            selected = selected[selected["Game"].astype(str).eq(source_game)]
    if not selected.empty and "Season" in selected:
        identified = selected["Season"].astype(str).str.strip().ne("")
        if identified.any():
            selected = selected[selected["Season"].astype(str).eq(source_season)]
    if selected.empty:
        return pd.DataFrame(
            [
                {
                    "Round": 1,
                    "Date": date.today(),
                    "GP Name": "",
                    "Circuit": "",
                    "Time (Lisbon)": time(20, 0),
                    "Has Sprint": False,
                }
            ]
        )
    columns = [
        "Round",
        "Date",
        "GP Name",
        "Circuit",
        "Time (Lisbon)",
        "Has Sprint",
    ]
    for column in columns:
        if column not in selected:
            selected[column] = None
    selected = selected[columns].copy()
    selected["Date"] = pd.to_datetime(selected["Date"], errors="coerce").dt.date
    selected["Has Sprint"] = selected["Has Sprint"].fillna(False).astype(bool)
    return selected.reset_index(drop=True)


def _render_setup_calendar(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
) -> None:
    identity = st.session_state.get(f"{SETUP_PREFIX}identity")
    if not isinstance(identity, Mapping):
        st.session_state[f"{SETUP_PREFIX}step"] = 1
        st.rerun()
        return
    if identity.get("mode") == "roster":
        st.session_state[f"{SETUP_PREFIX}calendar"] = []
        st.session_state[f"{SETUP_PREFIX}step"] = 5
        st.rerun()
        return
    saved = st.session_state.get(f"{SETUP_PREFIX}calendar")
    if isinstance(saved, list):
        frame = pd.DataFrame(saved)
    else:
        source_league_id = ""
        try:
            import league_config

            tables = league_config.load_config_tables(workbook_path)
            source = tuple(map(str, identity.get("source", ())))
            source_key = next(
                (
                    key
                    for key in league_config.configured_league_keys(tables)
                    if (key.game, key.season, key.league_name) == source
                ),
                None,
            )
            source_league_id = source_key.league_id if source_key else ""
        except Exception:
            pass
        try:
            frame = _calendar_seed(
                calendar,
                identity,
                championship_identities=_setup_championships(
                    workbook_path, standings
                ),
                source_league_id=source_league_id,
            )
        except ValueError as exc:
            st.error(str(exc))
            if st.button(
                _text(lang, "back"),
                key=f"{SETUP_PREFIX}calendar_identity_back",
                use_container_width=True,
            ):
                st.session_state[f"{SETUP_PREFIX}step"] = 3
                st.rerun()
            return
    st.subheader(_text(lang, "calendar"))
    st.caption(_text(lang, "calendar_help"))
    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Round": st.column_config.NumberColumn(
                _text(lang, "round"), min_value=1, step=1, required=True
            ),
            "Date": st.column_config.DateColumn(
                _text(lang, "date"), required=True
            ),
            "GP Name": st.column_config.TextColumn(
                _text(lang, "grand_prix"), required=True
            ),
            "Circuit": st.column_config.TextColumn(
                _text(lang, "circuit"), required=True
            ),
            "Time (Lisbon)": st.column_config.TimeColumn(
                _text(lang, "lisbon_start"), required=True
            ),
            "Has Sprint": st.column_config.CheckboxColumn(
                _text(lang, "sprint_weekend"), default=False
            ),
        },
        key=f"{SETUP_PREFIX}calendar_editor",
    )
    back, forward = _navigation(lang, 4)
    if back:
        st.session_state[f"{SETUP_PREFIX}step"] = 3
        st.rerun()
    if not forward:
        return
    records = _frame_records(edited)
    errors: list[str] = []
    rounds: list[int] = []
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(records, start=1):
        round_value = pd.to_numeric(row.get("Round"), errors="coerce")
        if pd.isna(round_value) or not float(round_value).is_integer():
            errors.append(
                _format_text(lang, "calendar_round_invalid", row=index)
            )
            continue
        round_number = int(round_value)
        rounds.append(round_number)
        gp_name = str(row.get("GP Name") or "").strip()
        circuit = str(row.get("Circuit") or "").strip()
        event_date = pd.to_datetime(row.get("Date"), errors="coerce")
        start_time = row.get("Time (Lisbon)")
        if not gp_name or not circuit or pd.isna(event_date) or start_time in (None, ""):
            errors.append(
                _format_text(lang, "calendar_row_incomplete", row=index)
            )
        normalized.append(
            {
                "Round": round_number,
                "Date": event_date.date() if not pd.isna(event_date) else None,
                "GP Name": gp_name,
                "Circuit": circuit,
                "Status": "Upcoming",
                "Time (Lisbon)": start_time,
                "Has Sprint": bool(row.get("Has Sprint", False)),
            }
        )
    if rounds != list(range(1, len(rounds) + 1)):
        errors.append(_text(lang, "calendar_round_order"))
    dates = [row["Date"] for row in normalized if row["Date"] is not None]
    if dates != sorted(dates):
        errors.append(_text(lang, "calendar_date_order"))
    if errors:
        for error in errors:
            st.error(error)
        return
    if dates:
        try:
            reviewed_season = derive_next_season_code(
                min(dates),
                _season_code_championships(
                    workbook_path, standings, calendar
                ),
            )
        except ValueError as exc:
            st.error(_format_text(lang, "season_code_error", error=exc))
            return
        if reviewed_season != str(identity.get("season") or ""):
            st.session_state[f"{SETUP_PREFIX}season_notice"] = reviewed_season
        reviewed_identity = dict(identity)
        reviewed_identity["season"] = reviewed_season
        reviewed_identity["season_start_date"] = min(dates).isoformat()
        st.session_state[f"{SETUP_PREFIX}identity"] = reviewed_identity
    st.session_state[f"{SETUP_PREFIX}calendar"] = normalized
    st.session_state[f"{SETUP_PREFIX}step"] = 5
    st.rerun()


def _setup_draft(source_version: str) -> dict[str, object] | None:
    identity = st.session_state.get(f"{SETUP_PREFIX}identity")
    roster = st.session_state.get(f"{SETUP_PREFIX}roster")
    race_scoring = st.session_state.get(f"{SETUP_PREFIX}race_scoring")
    sprint_scoring = st.session_state.get(f"{SETUP_PREFIX}sprint_scoring")
    bonuses = st.session_state.get(f"{SETUP_PREFIX}bonuses")
    calendar = st.session_state.get(f"{SETUP_PREFIX}calendar")
    if not isinstance(identity, Mapping) or not isinstance(roster, list):
        return None
    roster_only = identity.get("mode") == "roster"
    if roster_only:
        calendar = []
    if not (
        isinstance(race_scoring, list)
        and isinstance(sprint_scoring, list)
        and isinstance(bonuses, Mapping)
    ):
        return None
    if not roster_only and not isinstance(calendar, list):
        return None
    return {
        "identity": dict(identity),
        "roster": roster,
        "scoring": {"R": race_scoring, "SR": sprint_scoring},
        "fastest_lap": dict(bonuses),
        "calendar": calendar,
        "source_version": source_version,
    }


def _render_setup_preview(
    *,
    workbook_path: str,
    standings: pd.DataFrame,
    lang: str,
    source_version: str,
    hosted_publisher: SetupPublisher | None,
    clear_data_cache: Callable[[], None],
) -> None:
    draft = _setup_draft(source_version)
    if draft is None:
        st.warning(_text(lang, "stale"))
        if st.button(_text(lang, "reset"), key=f"{SETUP_PREFIX}stale_reset"):
            _clear_prefix(st.session_state, SETUP_PREFIX)
            st.rerun()
        return
    st.subheader(_text(lang, "preview"))
    identity = draft["identity"]
    if season_notice := st.session_state.pop(
        f"{SETUP_PREFIX}season_notice", None
    ):
        st.info(
            _format_text(
                lang, "season_recalculated", season=season_notice
            )
        )
    identity_rows = [
        {_text(lang, "identity"): _text(lang, "game"), _text(lang, "value"): identity.get("game", "")},
        {_text(lang, "identity"): _text(lang, "season"), _text(lang, "value"): identity.get("season", "")},
        {_text(lang, "identity"): _text(lang, "season_start"), _text(lang, "value"): identity.get("season_start_date", "")},
        {_text(lang, "identity"): _text(lang, "league"), _text(lang, "value"): identity.get("league", "")},
    ]
    st.dataframe(pd.DataFrame(identity_rows), hide_index=True, width="stretch")
    st.caption(_text(lang, "roster"))
    st.dataframe(
        _localized_frame(pd.DataFrame(draft["roster"]), lang),
        hide_index=True,
        width="stretch",
    )
    scoring_columns = st.columns(2)
    scoring = draft["scoring"]
    scoring_columns[0].caption(_text(lang, "race_points"))
    scoring_columns[0].dataframe(
        _localized_frame(pd.DataFrame(scoring["R"]), lang),
        hide_index=True,
        width="stretch",
    )
    scoring_columns[1].caption(_text(lang, "sprint_points"))
    scoring_columns[1].dataframe(
        _localized_frame(pd.DataFrame(scoring["SR"]), lang),
        hide_index=True,
        width="stretch",
    )
    st.caption(_text(lang, "fastest_bonus"))
    bonus_rows = []
    for event_type in ("R", "SR"):
        rule = draft["fastest_lap"].get(event_type, {})
        rule = rule if isinstance(rule, Mapping) else {}
        bonus_rows.append(
            {
                "Session": _text(
                    lang, "race" if event_type == "R" else "sprint"
                ),
                "Enabled": rule.get("enabled", False),
                "Bonus points": rule.get("points", 0.0),
                "Highest eligible finish": (
                    rule.get("eligibility_max_position")
                    or _text(lang, "any_classified")
                ),
            }
        )
    st.dataframe(
        _localized_frame(pd.DataFrame(bonus_rows), lang),
        hide_index=True,
        width="stretch",
    )
    if draft["calendar"]:
        st.caption(_text(lang, "calendar"))
        st.dataframe(
            _localized_frame(pd.DataFrame(draft["calendar"]), lang),
            hide_index=True,
            width="stretch",
        )
    try:
        publication = build_setup_publication(draft, workbook_path, standings)
    except Exception as exc:
        st.error(_text(lang, "resolve"))
        st.markdown(f"- {exc}")
        publication = None
    else:
        st.success(_text(lang, "setup_ready"))
    if publication is not None:
        try:
            import league_workbook

            digest = league_workbook.mutation_digest(
                publication, source_version=source_version
            )
        except Exception:
            digest = _digest(draft)
        completing = tuple(getattr(publication, "complete_league_ids", ()))
        if completing:
            completion_labels = list(completing)
            try:
                import league_config

                configured = league_config.load_config_tables(workbook_path)
                names = {
                    str(row["League ID"]).strip(): str(row["League Name"]).strip()
                    for row in configured.league_config.to_dict("records")
                }
                completion_labels = [
                    f"{names.get(league_id, league_id)} ({league_id})"
                    for league_id in completing
                ]
            except Exception:
                pass
            st.info(
                _format_text(
                    lang,
                    "current_league_completed",
                    leagues=", ".join(completion_labels),
                ),
                icon=":material/check_circle:",
            )
    else:
        digest = _digest(draft)
    approved = st.checkbox(
        _text(lang, "approval"), key=f"{SETUP_PREFIX}approval_{digest[:16]}"
    )
    columns = st.columns(2)
    if columns[0].button(_text(lang, "back"), key=f"{SETUP_PREFIX}back_5", use_container_width=True):
        st.session_state[f"{SETUP_PREFIX}step"] = (
            4 if identity.get("mode") == "new" else 3
        )
        st.rerun()
    publish = columns[1].button(
        _text(lang, "publish"),
        type="primary",
        use_container_width=True,
        disabled=not approved or hosted_publisher is None or publication is None,
        key=f"{SETUP_PREFIX}publish_{digest[:16]}",
    )
    if not publish or hosted_publisher is None or publication is None:
        return
    try:
        # The callback receives only the reviewed mapping.  The protected
        # controller rebuilds and revalidates the backend mutation after its
        # fresh authorization check instead of trusting this preview object.
        result = hosted_publisher(draft, source_version, approved)
    except Exception:
        st.error(_text(lang, "publisher_error"))
        return
    clear_data_cache()
    _clear_prefix(st.session_state, SETUP_PREFIX)
    st.session_state[f"{STATE_PREFIX}management_success"] = {
        "message": _text(lang, "setup_success"),
        "commit_url": getattr(result, "commit_url", ""),
    }
    st.rerun()


def _league_id(game: str, season: str, league: str) -> str:
    normalized = "|".join(" ".join(value.casefold().split()) for value in (game, season, league))
    return "league-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _reviewed_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "y", "1"}:
            return True
        if normalized in {"false", "no", "n", "0"}:
            return False
    raise ValueError(f"{field_name} must be an explicit true/false value.")


def _calendar_dataclasses(records: Sequence[Mapping[str, object]]) -> tuple[object, ...]:
    import league_config

    output = []
    for row in records:
        parsed_date = pd.to_datetime(row.get("Date"), errors="raise").date()
        raw_time = row.get("Time (Lisbon)")
        if isinstance(raw_time, datetime):
            parsed_time = raw_time.time()
        elif isinstance(raw_time, time):
            parsed_time = raw_time
        elif raw_time in (None, ""):
            parsed_time = None
        else:
            parsed_time = time.fromisoformat(str(raw_time))
        output.append(
            league_config.CalendarRound(
                int(row["Round"]),
                parsed_date,
                str(row["GP Name"]).strip(),
                str(row["Circuit"]).strip(),
                str(row.get("Status") or "Upcoming").strip(),
                parsed_time,
                _reviewed_bool(
                    row.get("Has Sprint", False), field_name="Has Sprint"
                ),
            )
        )
    return tuple(output)


def _mutation_from_setup(
    setup: object,
    *,
    include_calendar: bool,
    complete_league_ids: Sequence[str] = (),
) -> object:
    import league_workbook

    mutation = league_workbook.mutation_from_setup(
        setup, complete_league_ids=complete_league_ids
    )
    if include_calendar:
        return mutation
    return league_workbook.LeagueWorkbookMutation(
        league_config=mutation.league_config,
        roster_config=mutation.roster_config,
        scoring_profiles=mutation.scoring_profiles,
        scoring_points=mutation.scoring_points,
        calendar=(),
        complete_league_ids=mutation.complete_league_ids,
    )


def _scoring_dataclasses(
    draft: Mapping[str, object],
    league_id: str,
    effective_round: int,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    import league_config

    scoring = draft.get("scoring")
    bonuses = draft.get("fastest_lap")
    if not isinstance(scoring, Mapping) or not isinstance(bonuses, Mapping):
        raise ValueError("Scoring review is missing.")
    profiles = []
    points = []
    for event_type in ("R", "SR"):
        profile_id = f"{league_id}:{event_type}:{effective_round}"
        rule = bonuses.get(event_type, {})
        rule = rule if isinstance(rule, Mapping) else {}
        enabled = _reviewed_bool(
            rule.get("enabled", False),
            field_name=f"{event_type} fastest-lap enabled",
        )
        try:
            bonus_points = float(rule.get("points", 0.0) or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{event_type} fastest-lap bonus points are invalid."
            ) from exc
        max_value = pd.to_numeric(
            rule.get("eligibility_max_position", 0), errors="coerce"
        )
        if pd.isna(max_value) or not float(max_value).is_integer() or max_value < 0:
            raise ValueError(
                f"{event_type} fastest-lap eligibility must be a whole position or 0."
            )
        max_position = int(max_value)
        if enabled and bonus_points <= 0:
            raise ValueError(
                f"{event_type} fastest-lap bonus must be positive when enabled."
            )
        if not enabled and (bonus_points != 0 or max_position != 0):
            raise ValueError(
                f"{event_type} fastest-lap values must be zero when the bonus is disabled."
            )
        max_finish = max_position or None
        profiles.append(
            league_config.ScoringProfile(
                profile_id,
                league_id,
                event_type,
                effective_round,
                bonus_points if enabled else 0.0,
                max_finish,
            )
        )
        event_points = scoring.get(event_type, [])
        if not isinstance(event_points, list):
            raise ValueError(f"{event_type} scoring review is missing.")
        points.extend(
            league_config.ScoringPoint(
                profile_id,
                int(row["Position"]),
                float(row["Points"]),
            )
            for row in event_points
        )
    return tuple(profiles), tuple(points)


def _require_completed_calendar(
    workbook_path: str,
    league_ids: Sequence[str],
    *,
    standings: pd.DataFrame | None = None,
) -> None:
    if not league_ids:
        return
    try:
        calendar = pd.read_excel(workbook_path, sheet_name="Calendar", dtype=object)
    except ValueError as exc:
        raise ValueError(
            "The current active league has no managed Calendar and cannot be completed yet."
        ) from exc
    if not {"League ID", "Status"}.issubset(calendar.columns):
        raise ValueError(
            "The current active league has no immutable Calendar identity and cannot be completed automatically."
        )
    if standings is not None:
        try:
            import league_config

            tables = league_config.load_config_tables(workbook_path)
            keys = {
                key.league_id: key
                for key in league_config.configured_league_keys(tables)
            }
        except Exception as exc:
            raise ValueError(
                "The current active league configuration could not be verified before completion."
            ) from exc
    else:
        tables = None
        keys = {}
    for league_id in league_ids:
        selected = calendar[
            calendar["League ID"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq(str(league_id).strip())
        ]
        if selected.empty:
            raise ValueError(
                f"Current active league {league_id!r} has no managed Calendar rows."
            )
        unfinished = selected[
            ~selected["Status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq("done")
        ]
        if not unfinished.empty:
            pending = ", ".join(
                f"R{int(value)}"
                for value in pd.to_numeric(
                    unfinished.get("Round", pd.Series(dtype=object)),
                    errors="coerce",
                )
                .dropna()
                .astype(int)
                .tolist()
            )
            detail = f" ({pending})" if pending else ""
            raise ValueError(
                f"Current active league {league_id!r} still has unfinished Calendar rounds{detail}. "
                "Finish or correct that league before starting its successor."
            )
        if standings is None:
            continue
        key = keys.get(league_id)
        if key is None or tables is None:
            raise ValueError(
                f"Current active league {league_id!r} has no unique managed identity."
            )
        missing_events: list[str] = []
        season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
        event_types = (
            standings["Type"]
            if "Type" in standings
            else pd.Series("R", index=standings.index)
        )
        for row in selected.to_dict("records"):
            try:
                round_number = int(row["Round"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Current active league {league_id!r} has an invalid Calendar round."
                ) from exc
            gp_name = str(row.get("GP Name") or "").strip()
            roster = league_config.resolve_roster_snapshot(
                tables, league_id, round_number
            )
            expected_drivers = {entry.driver_name for entry in roster}
            sprint_value = row.get("Has Sprint", False)
            if sprint_value is None or (
                not isinstance(sprint_value, bool) and pd.isna(sprint_value)
            ):
                has_sprint = False
            else:
                has_sprint = _reviewed_bool(
                    sprint_value, field_name="Calendar Has Sprint"
                )
            expected_types = ("R", "SR") if has_sprint else ("R",)
            for event_type in expected_types:
                result = standings[
                    standings["Game"].astype(str).eq(key.game)
                    & standings[season_column].astype(str).eq(key.season)
                    & standings["League Name"].astype(str).eq(key.league_name)
                    & pd.to_numeric(standings["Round"], errors="coerce").eq(
                        round_number
                    )
                    & standings["GP Name"].astype(str).eq(gp_name)
                    & event_types
                    .fillna("R")
                    .astype(str)
                    .str.upper()
                    .eq(event_type)
                ]
                positions = set(
                    pd.to_numeric(result.get("Finish Pos"), errors="coerce")
                    .dropna()
                    .astype(int)
                    .tolist()
                )
                drivers = set(
                    result.get("Driver", pd.Series(dtype=object))
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .tolist()
                )
                if (
                    len(result) != len(roster)
                    or positions != set(range(1, len(roster) + 1))
                    or drivers != expected_drivers
                ):
                    label = "Sprint" if event_type == "SR" else "Race"
                    missing_events.append(f"R{round_number} {label}")
        if missing_events:
            raise ValueError(
                f"Current active league {league_id!r} is missing complete published events: "
                + ", ".join(missing_events)
                + "."
            )


def build_setup_publication(
    draft: Mapping[str, object],
    workbook_path: str,
    standings: pd.DataFrame,
) -> object:
    """Convert the submitted UI draft into a backend-validated mutation."""

    import league_config
    import league_workbook

    identity = draft.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("League identity is missing from the submitted review.")
    game = str(identity.get("game") or "").strip()
    season = str(identity.get("season") or "").strip()
    league = str(identity.get("league") or "").strip()
    mode = str(identity.get("mode") or "new")
    source = tuple(map(str, identity.get("source", ())))
    if len(source) != 3:
        raise ValueError("Clone source is missing from the submitted review.")
    existing = league_config.load_config_tables(workbook_path)
    configured = league_config.configured_league_keys(existing)
    source_key = next(
        (
            item
            for item in configured
            if (item.game, item.season, item.league_name) == source
        ),
        None,
    )
    roster_records = draft.get("roster")
    if not isinstance(roster_records, list):
        raise ValueError("Roster review is missing.")

    if mode == "roster" and source_key is not None:
        effective = int(identity.get("effective_round", 1))
        configured_row = existing.league_config[
            existing.league_config["League ID"]
            .astype(str)
            .str.strip()
            .eq(source_key.league_id)
        ]
        if len(configured_row) != 1 or (
            str(configured_row.iloc[0]["Status"]).strip().casefold() != "active"
        ):
            raise ValueError(
                "Roster changes can target only the single Active managed league."
            )
        import dashboard_core

        managed_calendar = dashboard_core.load_calendar_data(workbook_path)
        eligible_rounds = _managed_roster_rounds(
            workbook_path, standings, managed_calendar, source
        )
        if effective not in eligible_rounds:
            raise ValueError(
                "The roster effective round must be one exact managed Upcoming Calendar round."
            )
        published = _matching_championship_rows(standings, source)
        conflicting = published[
            pd.to_numeric(published["Round"], errors="coerce").ge(effective)
        ]
        if not conflicting.empty:
            affected_rounds = ", ".join(
                f"R{value}"
                for value in sorted(
                    pd.to_numeric(conflicting["Round"], errors="coerce")
                    .dropna()
                    .astype(int)
                    .unique()
                    .tolist()
                )
            )
            raise ValueError(
                "A roster update cannot start at or before already published results"
                + (f" ({affected_rounds})" if affected_rounds else "")
                + ". Choose the next unpublished round."
            )
        complete_roster = tuple(
            league_config.RosterChange(
                source_key.league_id,
                effective,
                str(row["Driver"]).strip(),
                str(row["Team"]).strip(),
                league_config.parse_ocr_aliases(
                    row.get("OCR Aliases", "")
                ),
            )
            for row in roster_records
        )
        profiles, points = _scoring_dataclasses(
            draft, source_key.league_id, effective
        )
        update = league_config.RosterSnapshotUpdate(
            source_key.league_id,
            effective,
            complete_roster,
            profiles,
            points,
        )
        league_config.validate_roster_snapshot_update(existing, update)
        return league_workbook.mutation_from_roster_snapshot_update(existing, update)

    if mode == "new":
        league_id = _league_id(game, season, league)
        normalized_league = league_config.normalize_identity(league)
        historical_names = {
            league_config.normalize_identity(value)
            for value in standings.get(
                "League Name", pd.Series(dtype=object)
            ).tolist()
        }
        configured_names = {
            league_config.normalize_identity(key.league_name)
            for key in configured
        }
        if normalized_league in historical_names | configured_names:
            raise ValueError(
                "League name must be unique across every current and historical league."
            )
        calendar_records = draft.get("calendar")
        if not isinstance(calendar_records, list):
            raise ValueError("Calendar review is missing.")
        reviewed_dates = pd.to_datetime(
            [row.get("Date") for row in calendar_records], errors="coerce"
        )
        valid_dates = reviewed_dates[~pd.isna(reviewed_dates)]
        if len(valid_dates) == 0:
            raise ValueError(
                "The reviewed Calendar needs a valid season start date."
            )
        import dashboard_core

        reviewed_calendar = dashboard_core.load_calendar_data(workbook_path)
        championship_identities = _season_code_championships(
            workbook_path, standings, reviewed_calendar
        )
        expected_season = derive_next_season_code(
            min(valid_dates).date(), championship_identities
        )
        if season != expected_season:
            raise ValueError(
                "Season code is stale or does not match the earliest Calendar "
                f"date; expected {expected_season}."
            )
        calendar_rows = _calendar_dataclasses(calendar_records)
        roster = tuple(
            league_config.RosterChange(
                league_id,
                1,
                str(row["Driver"]).strip(),
                str(row["Team"]).strip(),
                league_config.parse_ocr_aliases(
                    row.get("OCR Aliases", "")
                ),
            )
            for row in roster_records
        )
        profiles, points = _scoring_dataclasses(draft, league_id, 1)
        created_text = str(identity.get("created_utc") or "")
        if not created_text:
            raise ValueError("The reviewed setup creation timestamp is missing.")
        created = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
        setup = league_config.LeagueSetup(
            league_config.LeagueKey(league_id, game, season, league),
            calendar_rows,
            roster,
            profiles,
            points,
            "Active",
            source_key.league_id if source_key is not None else "",
            created,
        )
        active_ids = tuple(
            str(value).strip()
            for value in existing.league_config.loc[
                existing.league_config["Status"]
                .astype(str)
                .str.casefold()
                .eq("active"),
                "League ID",
            ].tolist()
            if str(value).strip() and str(value).strip() != league_id
        )
        _require_completed_calendar(
            workbook_path, active_ids, standings=standings
        )
        validation_existing = existing
        if active_ids:
            league_rows = existing.league_config.copy()
            league_rows.loc[
                league_rows["League ID"].astype(str).isin(active_ids), "Status"
            ] = "Completed"
            validation_existing = league_config.ConfigTables(
                league_rows,
                existing.roster_config.copy(),
                existing.scoring_profiles.copy(),
                existing.scoring_points.copy(),
            )
        league_config.validate_league_setup(setup, existing=validation_existing)
        return _mutation_from_setup(
            setup,
            include_calendar=True,
            complete_league_ids=active_ids,
        )

    raise ValueError(
        "Roster changes are available only for configuration-backed leagues."
    )


def render_event_correction(
    workbook_path: str,
    standings: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    lang: str,
    clear_data_cache: Callable[[], None],
    source_version: str,
    hosted_publisher: CorrectionPublisher | None,
) -> None:
    """Render correction selection and approval.

    The replacement screenshot review is delegated lazily to the correction
    backend once available. Undo remains a complete old-row review here.
    """

    st.header(_text(lang, "correction_title"))
    st.write(_text(lang, "correction_intro"))
    token = _source_token(source_version)
    token_key = f"{CORRECTION_PREFIX}source_token"
    if st.session_state.get(token_key) != token:
        _clear_prefix(st.session_state, CORRECTION_PREFIX)
        st.session_state[token_key] = token

    events = _published_events(standings, calendar)
    if not events:
        st.info(_text(lang, "no_events"))
        return
    event = st.selectbox(
        _text(lang, "event"),
        events,
        format_func=lambda item: _format_event(item, lang=lang),
        key=f"{CORRECTION_PREFIX}event_{token}",
    )
    try:
        operations, configured_status = _correction_operations(
            workbook_path, event
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    if configured_status not in {None, "Active"}:
        st.info(_text(lang, "undo_closed"), icon=":material/history:")
    operation = st.radio(
        _text(lang, "operation"),
        operations,
        format_func=lambda item: _text(lang, item),
        horizontal=True,
        key=f"{CORRECTION_PREFIX}operation_{token}_{_digest(event)[:8]}",
    )
    import race_metadata

    try:
        metadata = event_metadata_from_mapping(event)
    except (
        TypeError,
        ValueError,
        race_metadata.RaceMetadataCompatibilityError,
    ):
        st.error(_text(lang, "event_identity_error"))
        return
    import race_correction

    try:
        snapshot = race_correction.load_event_snapshot(workbook_path, metadata)
    except race_correction.EventCorrectionError as exc:
        st.error(str(exc))
        return
    old_rows = pd.DataFrame(
        [
            {
                "Excel Row": row.excel_row,
                "Finish Pos": row.position,
                "Driver": row.driver,
                "Team": row.team,
                "Points": row.points,
                "Time": row.time,
                "Fastest Lap": row.fastest_lap,
            }
            for row in snapshot.rows
        ]
    )
    st.subheader(_text(lang, "old_results"))
    display_columns = [
        column
        for column in ["Finish Pos", "Driver", "Team", "Points", "Time", "Fastest Lap"]
        if column in old_rows
    ]
    st.dataframe(
        _localized_frame(old_rows[display_columns], lang),
        hide_index=True,
        width="stretch",
    )

    if operation == "replace":
        _render_replace_correction(
            event,
            old_rows,
            workbook_path=workbook_path,
            standings=standings,
            metadata=metadata,
            snapshot_digest=snapshot.digest,
            lang=lang,
            source_version=source_version,
            hosted_publisher=hosted_publisher,
            clear_data_cache=clear_data_cache,
        )
        return
    st.warning(_text(lang, "undo_warning"), icon=":material/undo:")
    request = {
        "operation": "undo",
        "event": event,
        "old_rows": _frame_records(old_rows),
        "expected_event_digest": snapshot.digest,
        "source_version": source_version,
    }
    _render_correction_approval(
        request,
        lang=lang,
        source_version=source_version,
        hosted_publisher=hosted_publisher,
        clear_data_cache=clear_data_cache,
    )


def _correction_operations(
    workbook_path: str, event: Mapping[str, object]
) -> tuple[tuple[str, ...], str | None]:
    """Expose Undo only when its configured league can be re-imported safely."""

    league_id = str(event.get("league_id") or "").strip()
    if not league_id:
        # Unmanaged legacy history retains the existing correction behavior.
        return ("replace", "undo"), None
    try:
        import league_config

        status = league_config.configured_league_status(
            league_config.load_config_tables(workbook_path), league_id
        )
    except league_config.LeagueConfigError as exc:
        raise ValueError(
            "The managed league status could not be verified. Reload the latest workbook before correcting this event."
        ) from exc
    return (("replace", "undo") if status == "Active" else ("replace",)), status


def _published_events(
    standings: pd.DataFrame, calendar: pd.DataFrame | None = None
) -> list[dict[str, object]]:
    required = {"Game", "League Name", "Round", "GP Name", "Type"}
    season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
    if standings.empty or not required.union({season_column}).issubset(standings.columns):
        return []
    rows = standings.copy()
    if "IsSeasonFinal" in rows:
        rows = rows[~rows["IsSeasonFinal"].fillna(False)]
    events: list[dict[str, object]] = []
    group_columns = ["Game", season_column, "League Name", "Round", "GP Name", "Type"]
    for key, group in rows.groupby(group_columns, sort=False, dropna=False):
        game, season, league, round_number, gp_name, event_type = key
        positions = pd.to_numeric(group.get("Finish Pos"), errors="coerce").dropna().astype(int)
        drivers = group.get("Driver", pd.Series(dtype=object)).fillna("").astype(str).str.strip()
        if not len(group) or positions.nunique() != len(group) or drivers.nunique() != len(group):
            continue
        matching_calendar = pd.DataFrame()
        if calendar is not None and not calendar.empty:
            matching_calendar = calendar[
                calendar["League Name"].astype(str).eq(str(league))
                & pd.to_numeric(calendar["Round"], errors="coerce").eq(
                    int(round_number)
                )
                & calendar["GP Name"].astype(str).eq(str(gp_name))
            ].copy()
            if "Game" in matching_calendar and matching_calendar["Game"].astype(str).str.strip().ne("").any():
                matching_calendar = matching_calendar[
                    matching_calendar["Game"].astype(str).eq(str(game))
                ]
            if "Season" in matching_calendar and matching_calendar["Season"].astype(str).str.strip().ne("").any():
                matching_calendar = matching_calendar[
                    matching_calendar["Season"].astype(str).eq(str(season))
                ]
            if len(matching_calendar) != 1:
                continue
        league_id = (
            _optional_text(matching_calendar.iloc[0].get("League ID"))
            if len(matching_calendar) == 1
            else ""
        )
        events.append(
            {
                "game": str(game),
                "season": str(season),
                "league": str(league),
                "round": int(round_number),
                "gp": str(gp_name),
                "type": str(event_type).upper(),
                "league_id": league_id,
            }
        )
    return sorted(
        events,
        key=lambda item: (str(item["season"]), int(item["round"]), item["type"] == "R"),
        reverse=True,
    )


def _format_event(event: Mapping[str, object], *, lang: str = "en") -> str:
    session = _text(lang, "sprint" if event["type"] == "SR" else "race")
    return f"{event['season']} · {event['league']} · R{event['round']} · {event['gp']} · {session}"


def _event_rows(standings: pd.DataFrame, event: Mapping[str, object]) -> pd.DataFrame:
    season_column = "SeasonLabel" if "SeasonLabel" in standings else "Season"
    event_types = standings["Type"] if "Type" in standings else pd.Series("R", index=standings.index)
    selected = standings[
        standings["Game"].astype(str).eq(str(event["game"]))
        & standings[season_column].astype(str).eq(str(event["season"]))
        & standings["League Name"].astype(str).eq(str(event["league"]))
        & pd.to_numeric(standings["Round"], errors="coerce").eq(int(event["round"]))
        & standings["GP Name"].astype(str).eq(str(event["gp"]))
        & event_types.fillna("R").astype(str).str.upper().eq(str(event["type"]))
    ].copy()
    return selected.sort_values("Finish Pos").reset_index(drop=True)


def _render_replace_correction(
    event: Mapping[str, object],
    old_rows: pd.DataFrame,
    *,
    workbook_path: str,
    standings: pd.DataFrame,
    metadata: object,
    snapshot_digest: str,
    lang: str,
    source_version: str,
    hosted_publisher: CorrectionPublisher | None,
    clear_data_cache: Callable[[], None],
) -> None:
    st.caption(_text(lang, "replace_help"))
    extract_error_key = f"{CORRECTION_PREFIX}extract_error"
    if extract_error := st.session_state.pop(extract_error_key, None):
        st.error(str(extract_error))
    import race_import
    import race_import_ui
    import league_runtime

    try:
        authority = league_runtime.resolve_event_authority(
            workbook_path, standings, metadata
        )
    except league_runtime.LeagueAuthorityError as exc:
        st.error(str(exc))
        return
    roster = list(authority.roster)
    scoring = authority.base_points
    context = {
        "event": dict(event),
        "source_version": source_version,
        "event_digest": snapshot_digest,
    }
    context_digest = _digest(context)
    upload_generation_key = f"{CORRECTION_PREFIX}upload_generation"
    upload_generation = int(st.session_state.get(upload_generation_key, 0))
    upload_key = (
        f"{CORRECTION_PREFIX}uploads_{context_digest[:12]}_{upload_generation}"
    )
    _clear_stale_correction_uploads(
        st.session_state,
        current_upload_key=upload_key,
    )
    import secure_image_upload

    if hosted_publisher is not None and secure_image_upload.enabled():
        uploads, transport_errors = secure_image_upload.render_uploader(
            _text(lang, "corrected_uploads"),
            help_text=_text(lang, "replace_help"),
            key=upload_key,
            lang=lang,
        )
    else:
        uploads = st.file_uploader(
            _text(lang, "corrected_uploads"),
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help=_text(lang, "replace_help"),
            key=upload_key,
        )
        transport_errors = []
    upload_bytes = [upload.getvalue() for upload in uploads] if uploads else []
    upload_errors = list(transport_errors)
    if uploads:
        upload_errors.extend(race_import_ui.validate_screenshot_set(upload_bytes))
    if uploads and not upload_errors:
        with st.expander(
            _format_text(lang, "view_screenshots", count=len(uploads))
        ):
            columns = st.columns(min(2, len(uploads)))
            for index, upload in enumerate(uploads):
                columns[index % len(columns)].image(
                    upload.getvalue(), caption=upload.name, width="stretch"
                )
    for error in upload_errors:
        st.error(error)
    if not race_import_ui.valid_screenshot_count(len(upload_bytes)):
        st.caption(_text(lang, "upload_count"))
    screenshot_digests = [hashlib.sha256(value).hexdigest() for value in upload_bytes]
    extract_context = _digest({**context, "screenshots": screenshot_digests})
    extract = st.button(
        _text(lang, "extract"),
        type="primary",
        use_container_width=True,
        disabled=bool(upload_errors)
        or not race_import_ui.valid_screenshot_count(len(upload_bytes)),
        key=f"{CORRECTION_PREFIX}extract_{extract_context[:16]}",
    )
    draft_key = f"{CORRECTION_PREFIX}draft"
    if extract:
        extract_error: str | None = None
        try:
            with st.spinner(_text(lang, "reading_screenshots")):
                ocr_draft = race_import_ui._prepare_ocr_draft(
                    upload_bytes,
                    roster,
                    require_timing_detail=True,
                    expected_event_type=str(event["type"]),
                    expected_gp=str(event["gp"]),
                    auto_detect_event_type=False,
                )
        except Exception as exc:
            extract_error = str(exc)
        else:
            st.session_state[draft_key] = {
                "base_context_digest": context_digest,
                "context_digest": extract_context,
                "screenshot_hashes": screenshot_digests,
                "rows": ocr_draft.rows,
                "draft_id": _digest(ocr_draft.rows)[:12],
            }
        finally:
            # Uploaded image bytes are needed only for this extraction
            # attempt. Discard them on both success and failure, then retain
            # only hashes/review rows or a non-sensitive error notice.
            _finalize_correction_ocr_attempt(
                st.session_state,
                upload_key=upload_key,
                upload_generation_key=upload_generation_key,
                upload_generation=upload_generation,
                draft_key=draft_key,
                error_key=extract_error_key,
                error_message=extract_error,
            )
            st.rerun()

    draft = st.session_state.get(draft_key)
    if not isinstance(draft, Mapping):
        return
    if draft.get("base_context_digest") != context_digest:
        st.warning(_text(lang, "stale"))
        return
    editor_frame = pd.DataFrame(draft.get("rows", []))
    if editor_frame.empty:
        st.error(_text(lang, "no_rows_recognized"))
        return
    for column in ("Position", "Driver", "Time", "Fastest Lap"):
        if column not in editor_frame:
            editor_frame[column] = ""
    unselected = _text(lang, "select_driver")
    editor_frame["Driver"] = editor_frame["Driver"].fillna("").replace("", unselected)
    editable = editor_frame[["Position", "Driver", "Time", "Fastest Lap"]].copy()
    corrected = st.data_editor(
        editable,
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "Position": st.column_config.NumberColumn(
                _text(lang, "position"),
                min_value=1,
                max_value=len(roster),
                required=True,
            ),
            "Driver": st.column_config.SelectboxColumn(
                _text(lang, "driver"),
                options=[unselected] + [entry.driver for entry in roster],
                required=True,
            ),
            "Time": st.column_config.TextColumn(
                _text(lang, "time"), required=True
            ),
            "Fastest Lap": st.column_config.TextColumn(
                _text(lang, "fastest_lap"), required=True
            ),
        },
        key=f"{CORRECTION_PREFIX}replacement_editor_{draft['draft_id']}",
    )
    unresolved_count = int(corrected["Driver"].eq(unselected).sum())
    if unresolved_count:
        st.warning(
            _format_text(
                lang, "driver_choices_needed", count=unresolved_count
            )
        )
    with st.expander(_text(lang, "ocr_details")):
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
            _localized_frame(
                editor_frame[
                    [column for column in detail_columns if column in editor_frame]
                ],
                lang,
            ),
            hide_index=True,
            width="stretch",
        )
    validation_frame = corrected.copy()
    validation_frame["Driver"] = validation_frame["Driver"].replace(unselected, "")
    validation_frame["Timing Expected"] = True
    validation = race_import.validate_review_rows(
        _frame_records(validation_frame), roster, scoring
    )
    blockers = list(validation.blockers)
    try:
        new_records, fastest_award = league_runtime.apply_configured_points(
            validation.rows, authority
        )
    except league_runtime.LeagueAuthorityError as exc:
        blockers.append(str(exc))
        new_records = validation.rows
        fastest_award = None
    if blockers:
        st.error(_text(lang, "resolve"))
        for blocker in blockers:
            st.markdown(f"- {blocker}")
    st.subheader(_text(lang, "new_results"))
    st.dataframe(
        _localized_frame(
            pd.DataFrame(new_records).sort_values(
                "Position", na_position="last"
            ),
            lang,
        ),
        hide_index=True,
        width="stretch",
    )
    st.subheader(_text(lang, "comparison"))
    if fastest_award is not None and fastest_award.bonus:
        st.info(
            _format_text(
                lang,
                "fastest_bonus_award",
                driver=fastest_award.driver_name,
                bonus=fastest_award.bonus,
            )
        )
    new_by_position = {
        int(row["Position"]): row
        for row in new_records
        if row.get("Position") is not None
    }
    old_by_position = {
        int(row["Finish Pos"]): row
        for row in _frame_records(old_rows)
        if row.get("Finish Pos") is not None
    }
    positions = sorted(set(old_by_position) | set(new_by_position))
    comparison = pd.DataFrame(
        [
            {
                "Position": position,
                "Old driver": old_by_position.get(position, {}).get("Driver", ""),
                "New driver": new_by_position.get(position, {}).get("Driver", ""),
                "Old team": old_by_position.get(position, {}).get("Team", ""),
                "New team": new_by_position.get(position, {}).get("Team", ""),
                "Old points": old_by_position.get(position, {}).get("Points", ""),
                "New points": new_by_position.get(position, {}).get("Points", ""),
                "Old time": old_by_position.get(position, {}).get("Time", ""),
                "New time": new_by_position.get(position, {}).get("Time", ""),
                "Old fastest lap": old_by_position.get(position, {}).get(
                    "Fastest Lap", ""
                ),
                "New fastest lap": new_by_position.get(position, {}).get(
                    "Fastest Lap", ""
                ),
            }
            for position in positions
        ]
    )
    st.dataframe(
        _localized_frame(comparison, lang), hide_index=True, width="stretch"
    )
    request = {
        "operation": "replace",
        "event": dict(event),
        "old_rows": _frame_records(old_rows),
        "new_rows": new_records,
        "authoritative_roster": [
            {"Driver": entry.driver, "Team": entry.team} for entry in roster
        ],
        "authoritative_scoring": scoring,
        "expected_event_digest": snapshot_digest,
        "screenshot_hashes": list(draft.get("screenshot_hashes", ())),
        "source_version": source_version,
    }
    if blockers:
        return
    _render_correction_approval(
        request,
        lang=lang,
        source_version=source_version,
        hosted_publisher=hosted_publisher,
        clear_data_cache=clear_data_cache,
    )


def _render_correction_approval(
    request: Mapping[str, object],
    *,
    lang: str,
    source_version: str,
    hosted_publisher: CorrectionPublisher | None,
    clear_data_cache: Callable[[], None],
) -> None:
    digest = _digest(request)
    st.success(_text(lang, "correction_ready"))
    approved = st.checkbox(
        _text(lang, "correction_approval"),
        key=f"{CORRECTION_PREFIX}approval_{digest[:16]}",
    )
    clicked = st.button(
        _text(lang, "publish_correction"),
        type="primary",
        use_container_width=True,
        disabled=not approved or hosted_publisher is None,
        key=f"{CORRECTION_PREFIX}publish_{digest[:16]}",
    )
    if not clicked or hosted_publisher is None:
        return
    try:
        result = hosted_publisher(request, source_version, approved)
    except Exception:
        st.error(_text(lang, "publisher_error"))
        return
    clear_data_cache()
    _clear_prefix(st.session_state, CORRECTION_PREFIX)
    st.session_state[f"{STATE_PREFIX}management_success"] = {
        "message": _text(lang, "correction_success"),
        "commit_url": getattr(result, "commit_url", ""),
    }
    st.rerun()
