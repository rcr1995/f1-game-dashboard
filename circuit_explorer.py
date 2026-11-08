"""Pure country labels, circuit search and stable gallery sorting."""
from __future__ import annotations

import math
import unicodedata

from circuit_records import CIRCUIT_RECORDS, GP_ALIASES, get_circuit_record


_COUNTRIES = {
    "au": ("Australia", "Austrália"), "cn": ("China", "China"),
    "jp": ("Japan", "Japão"), "bh": ("Bahrain", "Barém"),
    "sa": ("Saudi Arabia", "Arábia Saudita"), "us": ("United States", "Estados Unidos"),
    "it": ("Italy", "Itália"), "mc": ("Monaco", "Mónaco"),
    "ca": ("Canada", "Canadá"), "es": ("Spain", "Espanha"),
    "at": ("Austria", "Áustria"), "gb": ("United Kingdom", "Reino Unido"),
    "be": ("Belgium", "Bélgica"), "hu": ("Hungary", "Hungria"),
    "nl": ("Netherlands", "Países Baixos"), "az": ("Azerbaijan", "Azerbaijão"),
    "sg": ("Singapore", "Singapura"), "mx": ("Mexico", "México"),
    "br": ("Brazil", "Brasil"), "qa": ("Qatar", "Catar"),
    "ae": ("United Arab Emirates", "Emirados Árabes Unidos"),
    "pt": ("Portugal", "Portugal"), "fr": ("France", "França"),
}
_GP_COUNTRY = dict(zip(
    ("Australian GP", "Chinese GP", "Japanese GP", "Bahrain GP", "Saudi Arabian GP",
     "Miami GP", "Emilia Romagna GP", "Monaco GP", "Canadian GP", "Barcelona-Catalunya GP",
     "Austrian GP", "British GP", "Belgian GP", "Hungarian GP", "Dutch GP", "Italian GP",
     "Spanish GP", "Azerbaijan GP", "Singapore GP", "United States GP", "Mexico City GP",
     "São Paulo GP", "Las Vegas GP", "Qatar GP", "Abu Dhabi GP", "Portuguese GP", "French GP"),
    ("au", "cn", "jp", "bh", "sa", "us", "it", "mc", "ca", "es", "at", "gb", "be", "hu",
     "nl", "it", "es", "az", "sg", "us", "mx", "br", "us", "qa", "ae", "pt", "fr"),
))
_GP_PT = {
    "Australian": "Austrália", "Chinese": "China", "Japanese": "Japão", "Bahrain": "Barém",
    "Saudi Arabian": "Arábia Saudita", "Emilia Romagna": "Emília-Romanha", "Monaco": "Mónaco",
    "Canadian": "Canadá", "Austrian": "Áustria", "British": "Grã-Bretanha", "Belgian": "Bélgica",
    "Hungarian": "Hungria", "Dutch": "Países Baixos", "Italian": "Itália", "Spanish": "Espanha",
    "Azerbaijan": "Azerbaijão", "Singapore": "Singapura", "United States": "Estados Unidos",
    "Mexico City": "Cidade do México", "Qatar": "Catar", "Portuguese": "Portugal", "French": "França",
    "Brazil": "Brasil", "Brazilian": "Brasil", "Mexico": "México", "Mexican": "México",
}
_COUNTRY_ALIASES = {"gb": ("UK", "Great Britain", "Grã-Bretanha"),
                    "us": ("USA", "United States of America", "Estados Unidos da América"),
                    "ae": ("UAE",)}
_CANONICAL_GP = {record.circuit: gp for gp, record in CIRCUIT_RECORDS.items()}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _normalized(value: object) -> str:
    folded = unicodedata.normalize("NFKD", _text(value)).casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in folded
                            if not unicodedata.combining(char)).split())


def circuit_label(gp_name: str, lang: str = "en") -> str:
    """Match the gallery's existing public GP headings without importing its UI."""
    gp = _text(gp_name)
    if gp == "Barcelona-Catalunya GP" or (gp == "Spanish GP" and lang != "pt"):
        return gp
    clean = gp.removesuffix(" GP").strip()
    return _GP_PT.get(clean, clean) if lang == "pt" else clean


def country_metadata(gp_name: str, circuit: str = "") -> dict[str, str]:
    """Country of a recorded venue, with unknown explicit venues left unknown."""
    gp, venue = _text(gp_name), _text(circuit)
    record = get_circuit_record(gp, venue)
    if record:
        canonical = _CANONICAL_GP.get(record.circuit, gp)
    elif venue:
        canonical = ""  # A known GP title must not override an unknown explicit venue.
    else:
        canonical = next((name for name in _GP_COUNTRY if _normalized(name) == _normalized(gp)), "")
        if not canonical:
            canonical = next((target for alias, target in GP_ALIASES.items()
                              if _normalized(alias) == _normalized(gp)), "")
    code = _GP_COUNTRY.get(canonical, "")
    names = _COUNTRIES.get(code, ("", ""))
    return {"country_code": code, "country_en": names[0], "country_pt": names[1]}


def _search_text(card: dict) -> str:
    gp, venue = _text(card.get("gp_name")), _text(card.get("circuit_name"))
    countries = country_metadata(gp, venue)
    countries.update({key: _text(card[key]) for key in countries if key in card})
    fields = [gp, venue, circuit_label(gp, "en"), circuit_label(gp, "pt"), *countries.values()]
    fields.extend(_COUNTRY_ALIASES.get(countries["country_code"], ()))
    # A generic Spanish GP with no recorded venue must not acquire Madrid's alias.
    record = get_circuit_record(gp, venue) if card.get("venue_recorded", True) else None
    if record:
        canonical = _CANONICAL_GP.get(record.circuit)
        fields.extend((record.circuit, *record.aliases))
        fields.extend(alias for alias, target in GP_ALIASES.items() if target == canonical)
    return _normalized(" ".join(fields))


def _count(value: object) -> int:
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def filter_circuits(cards: list[dict], query: str = "", sort: str = "name",
                    lang: str = "en") -> list[dict]:
    """Filter names/aliases/countries and sort a new list without changing cards.

    Race totals include recorded main-race events whose winner is unresolved.
    Sprint-only venues therefore still have zero main races.
    """
    terms = _normalized(query).split()
    selected = [card for card in (cards or [])
                if all(term in _search_text(card) for term in terms)]

    def name_key(card):
        return (_normalized(circuit_label(card.get("gp_name", ""), lang)),
                _normalized(card.get("circuit_name")), _text(card.get("key")))

    def country_key(card):
        metadata = country_metadata(card.get("gp_name", ""), card.get("circuit_name", ""))
        country = _text(card.get("country_pt" if lang == "pt" else "country_en",
                                 metadata["country_pt" if lang == "pt" else "country_en"]))
        return (not bool(country), _normalized(country), *name_key(card))

    if sort == "country":
        key = country_key
    elif sort == "races":
        key = lambda card: (-(_count(card.get("race_count")) + _count(card.get("unresolved_events"))),
                            *name_key(card))
    else:
        key = name_key
    return sorted(selected, key=key)
