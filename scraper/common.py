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
    "1010": "Innere Stadt",
    "1030": "Landstraße",
    "1040": "Wieden",
    "1050": "Margareten",
    "1060": "Mariahilf",
    "1070": "Neubau",
    "1080": "Josefstadt",
    "1120": "Meidling",
    "1150": "Rudolfsheim-Fünfhaus",
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


_browser_hosts = set()  # Hosts, die normale Requests blocken -> gleich als Browser anfragen


def _browser_get(url: str):
    """Fallback: Anfrage mit echtem Chrome-TLS-Fingerprint (hilft gegen Bot-Sperren)."""
    try:
        from curl_cffi import requests as cr
    except ImportError:
        return None
    try:
        r = cr.get(url, impersonate="chrome", timeout=25,
                   headers={"Accept-Language": "de-AT,de;q=0.9"})
        return r if r.status_code == 200 else None
    except Exception as e:
        print(f"  ! browser-fallback {type(e).__name__} {url}")
        return None


def get(url: str, **kw):
    """GET mit kleiner Pause, Retry und Browser-Fallback. Gibt None bei Fehler zurück."""
    host = url.split("/")[2]
    for attempt in range(2):
        time.sleep(random.uniform(0.8, 1.8))
        if host in _browser_hosts:
            r = _browser_get(url)
            if r is not None:
                return r
            print(f"  ! browser-fallback fehlgeschlagen {url}")
            return None
        try:
            r = session().get(url, timeout=25, **kw)
            if r.status_code == 200:
                return r
            print(f"  ! HTTP {r.status_code} {url}")
            if r.status_code in (403, 429, 503):
                _browser_hosts.add(host)
                continue
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
    category: str = "wohnung"       # "wohnung" oder "wg"
    eigenmittel: Optional[float] = None  # Finanzierungsbeitrag / Eigenmittel (Genossenschaften)
    source_label: str = ""          # Anzeigename der Quelle, z. B. Maklername
    wg_size: Optional[int] = None   # Personen in der WG

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


def check_alive(url: str, source: str):
    """Ist das Inserat noch online? True/False, None = weiß nicht (z. B. gesperrt).

    Nur eindeutige Signale – Textsuche auf der ganzen Seite ist zu unzuverlässig
    (derStandard hat z. B. "Inserat nicht mehr verfügbar" als Übersetzungstext auf jeder Seite).
    """
    try:
        time.sleep(random.uniform(0.8, 1.6))
        r = session().get(url, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code in (404, 410):
        return False
    if r.status_code != 200 or "cuba.html" in r.url:
        return None
    if "fromExpiredAdId" in r.url:
        return False
    if source == "willhaben":
        m = re.search(r'"advertStatus":\{"id":"(\w+)"', r.text)
        if m:
            return m.group(1) == "active"
        return None
    if source == "wggesucht":
        head = r.text[:60000]
        if re.search(r"Anzeige ist (deaktiviert|nicht mehr aktiv)|Angebot ist (deaktiviert|nicht mehr verfügbar)", head):
            return False
    return True


# ---------- Allgemeiner Detailseiten-Leser (für Makler-/Genossenschaftsseiten) ----------

_NUM = r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)"


def _num_after(text, keys, lo, hi):
    """Erste plausible Zahl nach einem der Schlüsselwörter (max. 60 Zeichen Abstand)."""
    for k in keys:
        for m in re.finditer(k + r"[^\d€]{0,60}(?:€\s*)?" + _NUM, text, re.I):
            v = parse_number(m.group(1))
            if v is not None and lo <= v <= hi:
                return v
    return None


def parse_detail_text(text: str) -> dict:
    """Liest Preis, Fläche, Zimmer, PLZ und Eigenmittel aus dem sichtbaren Text einer Inseratsseite."""
    t = re.sub(r"[\u00ad\u200b]", "", text)          # weiche Trennstriche (z. B. "Gesamt­belastung")
    t = re.sub(r"\s+", " ", t)
    out = {}
    gross = _num_after(t, [r"Gesamtmiete", r"Gesamtbelastung brutto", r"monatliche Gesamtbelastung",
                           r"Bruttomiete", r"Miete (?:inkl|brutto)[^\d€]{0,20}", r"monatl(?:iche)? Miete"], 100, 5000)
    net = _num_after(t, [r"Gesamtbelastung netto", r"Miete netto", r"Nettomiete"], 100, 5000)
    plain = _num_after(t, [r"\bMiete\b"], 100, 5000)
    if gross:
        out["price"], out["price_note"] = gross, "Gesamtmiete"
    elif net:
        out["price"], out["price_note"] = round(net * 1.1, 2), "ca. brutto (netto + 10 % USt.)"
    elif plain:
        out["price"], out["price_note"] = plain, "Miete"
    area = _num_after(t, [r"Wohnfläche", r"Nutzfläche", r"Fläche"], 10, 300)
    if area is None:
        m = re.search(_NUM + r"\s*m\s?(?:²|2)\b", t)
        area = parse_number(m.group(1)) if m else None
    out["area"] = area
    m = re.search(r"(\d(?:,5)?)\s*-?\s*Zimmer|Zimmer[^\d]{0,12}(\d(?:,5)?)\b", t)
    if m:
        out["rooms"] = parse_number(m.group(1) or m.group(2))
    out["zip"] = zip_from_text(t)
    out["eigenmittel"] = _num_after(t, [r"Finanzierungsbeitrag", r"Eigenmittel(?:anteil|beitrag)?", r"Grundkostenbeitrag",
                                        r"Baukostenbeitrag"], 300, 200000)
    out["email"] = (find_emails(t) or [""])[0]
    out["phone"] = find_phone(t)
    return out
