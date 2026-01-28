import os
import sys
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Dict, Any, Tuple

import yaml
import requests
from dateutil import tz


# ---------- Modelos ----------
@dataclass
class VenueSource:
    name: str
    city: str
    url: str
    type: str  # "html" o "js" (por ahora solo "html")
    notes: str = ""


@dataclass
class Event:
    title: str
    venue: str
    event_date: date
    event_time: Optional[str]  # "21:00" si lo tenemos, o None
    url: str
    source_url: str
    raw_genre_text: str = ""   # opcional: texto encontrado (si lo hay)


# ---------- Config de “bailable” (la afinaremos luego) ----------
DANCE_KEYWORDS = [
    "soul", "funk", "funky", "disco", "groove",
    "jazz", "jazz-funk", "latin", "latin jazz",
    "pop", "r&b", "rhythm and blues",
    "swing", "big band",
    "baile", "dance", "fiesta", "dj set", "jam"
]


# ---------- Utilidades ----------
def load_venues(path: str = "venues.yaml") -> List[VenueSource]:
    """Lee venues.yaml y devuelve una lista de fuentes."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe {path}. ¿Lo has creado en la raíz del repo?")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    venues_data = data.get("venues", [])
    venues: List[VenueSource] = []
    for v in venues_data:
        venues.append(
            VenueSource(
                name=v["name"],
                city=v.get("city", ""),
                url=v["url"],
                type=v.get("type", "html"),
                notes=v.get("notes", ""),
            )
        )
    return venues


def madrid_weekend_window(today_madrid: date) -> Tuple[date, date]:
    """
    Devuelve (viernes, sábado) de la misma semana que 'today_madrid',
    entendiendo semana como lunes-domingo.
    """
    # weekday: lunes=0 ... domingo=6
    weekday = today_madrid.weekday()
    # viernes es 4
    days_to_friday = 4 - weekday
    if days_to_friday < 0:
        # Si hoy es sábado/domingo y ejecutases, saltaría al viernes siguiente.
        days_to_friday += 7

    friday = today_madrid + timedelta(days=days_to_friday)
    saturday = friday + timedelta(days=1)
    return friday, saturday


def is_danceable(text: str) -> bool:
    """Filtro simple por palabras clave (lo refinaremos)."""
    t = (text or "").lower()
    return any(k in t for k in DANCE_KEYWORDS)


def fetch_html(url: str, timeout: int = 30) -> str:
    """
    Descarga HTML de una web de agenda.
    Ojo: añadimos User-Agent para evitar bloqueos tontos.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MadridConcertsBot/1.0; +https://github.com/)"
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


# ---------- “Parsers” por fuente (aún vacíos) ----------
def parse_events_from_teatro_del_barrio(html: str, source: VenueSource) -> List[Event]:
    """
    TODO: implementar scraping real.
    Debe devolver lista de Event con fecha y link.
    """
    return []


def parse_events_from_tempo_club(html: str, source: VenueSource) -> List[Event]:
    """
    TODO: implementar scraping real.
    """
    return []


def parse_events_from_cafe_berlin(html: str, source: VenueSource) -> List[Event]:
    """
    TODO: implementar scraping real.
    """
    return []


def parse_events_from_sala_riviera(html: str, source: VenueSource) -> List[Event]:
    """
    TODO: implementar scraping real.
    """
    return []


def parse_events(html: str, source: VenueSource) -> List[Event]:
    """
    Router: elige el parser según la fuente.
    (Esto hace el sistema mantenible.)
    """
    u = source.url.lower()

    if "teatrodelbarrio.com" in u:
        return parse_events_from_teatro_del_barrio(html, source)
    if "tempoclub.es" in u:
        return parse_events_from_tempo_club(html, source)
    if "cafeberlinentradas.com" in u:
        return parse_events_from_cafe_berlin(html, source)
    if "salariviera.com" in u:
        return parse_events_from_sala_riviera(html, source)

    # fallback
    return []


# ---------- Pipeline principal ----------
def collect_events(venues: List[VenueSource]) -> List[Event]:
    """
    Descarga cada fuente y parsea eventos.
    """
    all_events: List[Event] = []

    for v in venues:
        if v.type != "html":
            print(f"[WARN] Fuente {v.name} es type={v.type}. Aún no soportado en este paso.")
            continue

        try:
            html = fetch_html(v.url)
            events = parse_events(html, v)
            all_events.extend(events)
            print(f"[OK] {v.name}: {len(events)} eventos extraídos")
        except Exception as e:
            print(f"[ERROR] {v.name}: fallo al obtener/parsear -> {e}")

    return all_events


def filter_for_this_weekend(events: List[Event], friday: date, saturday: date) -> List[Event]:
    """
    Filtra eventos cuyo event_date sea viernes o sábado (de esa semana).
    """
    out: List[Event] = []
    for e in events:
        if e.event_date in (friday, saturday):
            out.append(e)
    return out


def main():
    # “Hoy” en zona Madrid (Europe/Madrid)
    madrid_tz = tz.gettz("Europe/Madrid")
    now_madrid = datetime.now(tz=madrid_tz)
    today_madrid = now_madrid.date()

    friday, saturday = madrid_weekend_window(today_madrid)

    print(f"Hoy (Madrid): {today_madrid.isoformat()}")
    print(f"Buscando conciertos para: viernes {friday.isoformat()} y sábado {saturday.isoformat()}")

    venues = load_venues("venues.yaml")
    print(f"Fuentes cargadas: {len(venues)}")

    all_events = collect_events(venues)

    weekend_events = filter_for_this_weekend(all_events, friday, saturday)

    # De momento solo mostramos (aún no scrapeamos, así que saldrá vacío)
    print(f"Eventos viernes/sábado encontrados: {len(weekend_events)}")

    # (Más adelante) aplicar filtro bailable, ordenar y mandar email.


if __name__ == "__main__":
    main()
