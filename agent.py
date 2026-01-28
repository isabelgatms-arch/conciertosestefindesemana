import re
from bs4 import BeautifulSoup
from dateutil.parser import parse as dtparse


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

SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # abreviaturas típicas
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

def parse_spanish_date_str(s: str) -> Optional[date]:
    """
    Acepta strings tipo:
      - '29 enero'
      - '30 de enero de 2026'
      - '28 ene'
    Devuelve date o None.
    """
    if not s:
        return None
    t = s.strip().lower()

    # 30 de enero de 2026
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})\b", t)
    if m:
        d = int(m.group(1))
        mon = SPANISH_MONTHS.get(m.group(2).replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u"))
        y = int(m.group(3))
        if mon:
            return date(y, mon, d)

    # 29 enero  (sin año)
    m = re.search(r"\b(\d{1,2})\s+([a-záéíóú]{3,})\b", t)
    if m:
        d = int(m.group(1))
        mon_key = m.group(2)
        mon_key = mon_key.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
        mon = SPANISH_MONTHS.get(mon_key)
        if mon:
            # año “probable”: lo decide el caller comparando con 'today'
            return date(1900, mon, d)  # año placeholder
    return None


def attach_year(d: date, today_madrid: date) -> date:
    """
    Si la fecha venía sin año (1900), asigna el año correcto.
    Estrategia: si mes/día ya pasó “mucho” respecto a hoy, asumimos año siguiente.
    (Para nuestro caso semanal funciona bien.)
    """
    if d.year != 1900:
        return d
    y = today_madrid.year
    candidate = date(y, d.month, d.day)
    # Si hoy es diciembre y candidate es enero, debe ser año siguiente
    if (today_madrid.month == 12 and candidate.month == 1):
        return date(y + 1, d.month, d.day)
    # Si hoy es enero y candidate es diciembre, debe ser año anterior (no nos interesa)
    return candidate



# ---------- “Parsers” por fuente (aún vacíos) ----------
def parse_events_from_teatro_del_barrio(html: str, source: VenueSource) -> List[Event]:
    """
    TODO: implementar scraping real.
    Debe devolver lista de Event con fecha y link.
    """
    return []


def parse_events_from_tempo_club(html: str, source: VenueSource) -> List[Event]:
    soup = BeautifulSoup(html, "lxml")
    text_lines = [ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()]

    # Patrón visible: "29 enero | 21:00" y justo después el título
    # Ejemplo en la página: :contentReference[oaicite:2]{index=2}
    events: List[Event] = []
    i = 0

    # Links de "+ info": los usamos para sacar URL del evento en orden
    info_links = []
    for a in soup.select("a"):
        label = (a.get_text(" ", strip=True) or "").lower()
        href = a.get("href") or ""
        if "+ info" in label and href:
            info_links.append(href)

    info_idx = 0

    while i < len(text_lines):
        ln = text_lines[i].lower()

        m = re.match(r"^(\d{1,2})\s+([a-záéíóú]+)\s*\|\s*([0-2]?\d:\d{2})$", ln)
        if m and i + 1 < len(text_lines):
            day = int(m.group(1))
            mon = m.group(2)
            hhmm = m.group(3)

            d0 = parse_spanish_date_str(f"{day} {mon}")
            if d0:
                # año real se asignará en main con hoy Madrid: aquí ponemos año placeholder 1900 y luego corregimos fuera,
                # pero como Event exige date real, la corregimos en caliente con 'datetime.now' Madrid:
                today_madrid = datetime.now(tz=tz.gettz("Europe/Madrid")).date()
                d = attach_year(d0, today_madrid)

                title = text_lines[i + 1].strip()
                url = info_links[info_idx] if info_idx < len(info_links) else source.url
                if info_idx < len(info_links):
                    info_idx += 1

                events.append(
                    Event(
                        title=title,
                        venue=source.name,
                        event_date=d,
                        event_time=hhmm,
                        url=url,
                        source_url=source.url,
                        raw_genre_text=title,
                    )
                )
            i += 2
            continue

        i += 1

    return events


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


    dance_events = []
for e in weekend_events:
    # “bailable” lo decidimos por título + texto cercano
    if is_danceable(f"{e.title} {e.raw_genre_text}"):
        dance_events.append(e)

dance_events.sort(key=lambda e: (e.event_date, e.event_time or "99:99", e.venue, e.title))

print(f"Eventos viernes/sábado 'bailables': {len(dance_events)}")
for e in dance_events[:30]:
    print(f"- {e.event_date} {e.event_time or ''} | {e.venue} | {e.title} | {e.url}")

    
    # De momento solo mostramos (aún no scrapeamos, así que saldrá vacío)
    print(f"Eventos viernes/sábado encontrados: {len(weekend_events)}")

    # (Más adelante) aplicar filtro bailable, ordenar y mandar email.


if __name__ == "__main__":
    main()
