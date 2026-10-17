"""Gemeinsame Helfer: HTTP-Session, Listing-Datenmodell, Text-Parsing."""
import json
import random
import re
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)

# Bezirke, die gesammelt werden (PLZ -> Name). In der App kann man daraus weiter filtern.
DISTRICTS = {
    "1040": "Wieden",
    "1050": "Margareten",
    "1060": "Mariahilf",
    "1070": "Neubau",
}

# Obergrenze beim Sammeln. Etwas über dem Budget, damit der Preis-Regler in der App Spielraum hat.
COLLECT_MAX_PRICE = 800

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
        })
        _session = s
    return _session


def get(url: str, **kw) -> Optional[requests.Response]:
    """GET mit kleiner Pause und einem Retry. Gibt None bei Fehler zurück."""
    for attempt in range(2):
        try:
            time.sleep(random.uniform(0.8, 1.8))
            r = session().get(url, timeout=25, **kw)
            if r.status_code == 200:
                return r
            print(f"  ! HTTP {r.status_code} {url}")
        except requests.RequestException as e:
            print(f"  ! {type(e).__name__} {url}")
        time.sleep(3)
    return None


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    price: Optional[float]
    zip: Optional[str]
    area: Optional[float] = None
    rooms: Optional[float] = None
    price_note: str = ""            # z. B. "Gesamtmiete", "Nettomiete"
    address: str = ""
    image: str = ""
    description: str = ""
    published: str = ""             # ISO-Zeitstempel laut Quelle
    advertiser: str = ""
    email: str = ""
    phone: str = ""
    private: Optional[bool] = None
    tags: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self):
        d = asdict(self)
        d["key"] = self.key
        return d


def parse_number(s) -> Optional[float]:
    """'€ 1.179,91' -> 1179.91, '45 m²' -> 45.0, '1,5 Zimmer' -> 1.5"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s)
    m = re.search(r"\d[\d.\s]*(?:,\d+)?|\d+(?:\.\d+)?", s)
    if not m:
        return None
    t = m.group(0).replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_BLOCKLIST = (
    "user@email.com", "example.", "@derstandard", "@willhaben", "@immobilienscout24",
    "@immowelt", "@immmo", "@sentry", "@2x", ".png", ".jpg", ".webp", "noreply", "no-reply",
)


def find_emails(text: str) -> List[str]:
    out = []
    for m in EMAIL_RE.findall(text or ""):
        low = m.lower().rstrip(".")
        if any(b in low for b in EMAIL_BLOCKLIST):
            continue
        if low not in out:
            out.append(low)
    return out


PHONE_RE = re.compile(r"(?:\+43|0043|0)\s?\(?0?\)?\s?[1-9][\d /-]{6,14}\d")


def find_phone(text: str) -> str:
    m = PHONE_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def zip_from_text(text: str) -> Optional[str]:
    m = re.search(r"\b(1[0-2]\d0)\b", text or "")
    return m.group(1) if m else None


def next_f_payload(html: str) -> str:
    """Setzt die Next.js-App-Router-Datenblöcke (self.__next_f.push) zu einem String zusammen."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)
