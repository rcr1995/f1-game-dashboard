"""Real-world F1 race-lap records, independent of the league's game results.

Sources were checked on 2026-09-25. These are race records for the listed
circuits, not qualifying/absolute records. Refresh the curated values against
the linked F1 circuit pages when a record or circuit layout changes.
"""

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class CircuitRecord:
    circuit: str
    lap_time: str
    driver: str
    year: int
    source: str
    aliases: tuple[str, ...] = ()


def _record(circuit, lap_time, driver, year, page, *aliases):
    return CircuitRecord(circuit, lap_time, driver, year,
                         f"https://www.formula1.com/en/racing/{page}", aliases)


CIRCUIT_RECORDS = {
    "Australian GP": _record("Albert Park Circuit", "1:19.813", "Charles Leclerc", 2024, "2026/australia", "Melbourne"),
    "Chinese GP": _record("Shanghai International Circuit", "1:32.238", "Michael Schumacher", 2004, "2026/china", "Shanghai"),
    "Japanese GP": _record("Suzuka International Racing Course", "1:30.965", "Kimi Antonelli", 2025, "2026/japan", "Suzuka", "Suzuka Circuit"),
    "Bahrain GP": _record("Bahrain International Circuit", "1:31.447", "Pedro de la Rosa", 2005, "2025/bahrain", "Bahrain", "Sakhir"),
    "Saudi Arabian GP": _record("Jeddah Corniche Circuit", "1:30.734", "Lewis Hamilton", 2021, "2025/saudi-arabia", "Jeddah"),
    "Miami GP": _record("Miami International Autodrome", "1:29.708", "Max Verstappen", 2023, "2026/miami", "Miami"),
    "Emilia Romagna GP": _record("Autodromo Internazionale Enzo e Dino Ferrari", "1:15.484", "Lewis Hamilton", 2020, "2025/emiliaromagna", "Imola", "Autodromo Enzo e Dino Ferrari (Imola)"),
    "Monaco GP": _record("Circuit de Monaco", "1:12.909", "Lewis Hamilton", 2021, "2026/monaco", "Monaco"),
    "Canadian GP": _record("Circuit Gilles-Villeneuve", "1:13.078", "Valtteri Bottas", 2019, "2026/canada", "Montreal"),
    "Barcelona-Catalunya GP": _record("Circuit de Barcelona-Catalunya", "1:15.743", "Oscar Piastri", 2025, "2026/barcelona-catalunya", "Barcelona", "Catalunya"),
    "Austrian GP": _record("Red Bull Ring", "1:07.924", "Oscar Piastri", 2025, "2026/austria", "Spielberg"),
    "British GP": _record("Silverstone Circuit", "1:27.097", "Max Verstappen", 2020, "2026/great-britain", "Silverstone"),
    "Belgian GP": _record("Circuit de Spa-Francorchamps", "1:44.701", "Sergio Perez", 2024, "2026/belgium", "Spa-Francorchamps", "Spa"),
    "Hungarian GP": _record("Hungaroring", "1:16.627", "Lewis Hamilton", 2020, "2026/hungary"),
    "Dutch GP": _record("Circuit Zandvoort", "1:11.097", "Lewis Hamilton", 2021, "2026/netherlands", "Zandvoort"),
    "Italian GP": _record("Autodromo Nazionale Monza", "1:20.901", "Lando Norris", 2025, "2026/italy", "Monza"),
    "Spanish GP": _record("Madring", "1:35.587", "George Russell", 2026, "2026/spain", "Madrid"),
    "Azerbaijan GP": _record("Baku City Circuit", "1:43.009", "Charles Leclerc", 2019, "2026/azerbaijan", "Baku"),
    "Singapore GP": _record("Marina Bay Street Circuit", "1:33.808", "Lewis Hamilton", 2025, "2026/singapore", "Marina Bay", "Marina Bay Circuit"),
    "United States GP": _record("Circuit of the Americas", "1:36.169", "Charles Leclerc", 2019, "2026/united-states", "Austin", "COTA"),
    "Mexico City GP": _record("Autódromo Hermanos Rodríguez", "1:17.774", "Valtteri Bottas", 2021, "2026/mexico", "Mexico City"),
    "São Paulo GP": _record("Autódromo José Carlos Pace", "1:10.540", "Valtteri Bottas", 2018, "2026/brazil", "Interlagos", "Autódromo José Carlos Pace (Interlagos)"),
    "Las Vegas GP": _record("Las Vegas Strip Circuit", "1:33.365", "Max Verstappen", 2025, "2026/las-vegas", "Las Vegas"),
    "Qatar GP": _record("Lusail International Circuit", "1:22.384", "Lando Norris", 2024, "2026/qatar", "Lusail", "Losail International Circuit"),
    "Abu Dhabi GP": _record("Yas Marina Circuit", "1:25.637", "Kevin Magnussen", 2024, "2025/united-arab-emirates", "Yas Marina"),
    "Portuguese GP": _record("Algarve International Circuit", "1:18.750", "Lewis Hamilton", 2020, "2021/portugal", "Portimão", "Autódromo Internacional do Algarve"),
    "French GP": _record("Circuit Paul Ricard", "1:32.740", "Sebastian Vettel", 2019, "2022/france", "Paul Ricard"),
}

GP_ALIASES = {
    "Brazil GP": "São Paulo GP", "Brazilian GP": "São Paulo GP",
    "Sao Paulo GP": "São Paulo GP", "Mexico GP": "Mexico City GP",
    "Mexican GP": "Mexico City GP", "Madrid GP": "Spanish GP",
}


def _key(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold()
                   if c.isalnum() and not unicodedata.combining(c))


_BY_CIRCUIT = {
    _key(name): record
    for record in CIRCUIT_RECORDS.values()
    for name in (record.circuit, *record.aliases)
}
_BY_GP = {_key(name): record for name, record in CIRCUIT_RECORDS.items()}
_BY_GP.update({_key(alias): CIRCUIT_RECORDS[name] for alias, name in GP_ALIASES.items()})


def get_circuit_record(gp_name: str, circuit: str = "") -> CircuitRecord | None:
    """Prefer an explicit venue, so a reused GP name cannot show another track's record.

    Unknown explicit circuits deliberately have no record; the caller can still
    show the calendar's name. A blank venue falls back to the known GP mapping.
    """
    if circuit.strip():
        return _BY_CIRCUIT.get(_key(circuit))
    return _BY_GP.get(_key(gp_name))
