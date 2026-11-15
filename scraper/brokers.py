"""Geschäftliche Mail-Adresse eines Maklers über seine eigene Website finden.

willhaben & Co. zeigen bei Maklern oft nur ein Kontaktformular. Viele Anfragen darüber versanden.
Die Firmen-Website (Impressum/Kontakt/Team) nennt fast immer eine echte Adresse, oft sogar die
persönliche der Ansprechpartnerin. Ergebnisse werden pro Domain zwischengespeichert, damit jede
Website nur selten abgefragt wird.
"""
import json
import os
import re
import time
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from common import find_emails, get

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "brokers.json")
RECHECK_DAYS = 21
MAX_NEW_PER_RUN = 6
PAGE_HINTS = ("impressum", "kontakt", "contact", "team", "ueber-uns", "uber-uns", "about")
GENERIC = ("office", "vermietung", "miete", "info", "kontakt", "service", "immobilien", "anfrage")

_cache = None
_new_this_run = 0


def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def save():
    if _cache is not None:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=1, sort_keys=True)


def _ascii(s):
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _domain(website):
    if not website:
        return ""
    if not website.startswith("http"):
        website = "https://" + website
    host = urlparse(website).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _scan(domain):
    """Startseite + Impressum/Kontakt/Team nach Mail-Adressen durchsuchen."""
    emails, seen = [], set()
    queue = [f"https://www.{domain}/", f"https://{domain}/"]
    pages = 0
    while queue and pages < 5:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        r = get(url)
        if not r or "html" not in r.headers.get("content-type", "html"):
            continue
        pages += 1
        html = r.text
        # mailto-Links und Klartext; einfache Verschleierung "name [at] firma.at" auflösen
        text = re.sub(r"\s*(\[at\]|\(at\)|\{at\}| at )\s*", "@", html, flags=re.I)
        text = re.sub(r"\s*(\[dot\]|\(dot\)|\{dot\})\s*", ".", text, flags=re.I)
        for e in find_emails(text):
            if e not in emails:
                emails.append(e)
        if pages <= 2:
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(h in href for h in PAGE_HINTS):
                    full = urljoin(r.url, a["href"]).split("#")[0]
                    if _domain(full) == domain and full not in seen and len(queue) < 6:
                        queue.append(full)
    # nur Adressen der eigenen Domain (Ausnahme: gar keine eigene gefunden)
    own = [e for e in emails if e.split("@")[1].endswith(domain)]
    return own or emails[:3]


def best_email(emails, contact=""):
    """Persönliche Adresse der Ansprechperson vor office@/vermietung@ vor dem Rest."""
    if not emails:
        return ""
    parts = [p for p in _ascii(contact).split() if len(p) > 1]
    if parts:
        last, first = parts[-1], parts[0]
        for e in emails:
            local = e.split("@")[0]
            if last in local or (len(local) <= 3 and local.startswith(first[0]) and local.endswith(last[0])):
                return e
    for g in GENERIC:
        for e in emails:
            if e.split("@")[0].startswith(g):
                return e
    return emails[0]


def email_for(website, contact=""):
    """Mail-Adresse für einen Makler. Leerer String, wenn nichts gefunden (oder Limit erreicht)."""
    global _new_this_run
    domain = _domain(website)
    if not domain or any(b in domain for b in ("willhaben", "facebook", "instagram", "immobilienscout")):
        return ""
    cache = _load()
    entry = cache.get(domain)
    fresh = entry and time.time() - entry.get("t", 0) < RECHECK_DAYS * 86400
    if not fresh:
        if _new_this_run >= MAX_NEW_PER_RUN:
            return best_email((entry or {}).get("emails", []), contact)
        _new_this_run += 1
        try:
            emails = _scan(domain)
        except Exception as ex:  # Website kaputt o. ä. – kein Grund, den Lauf zu stören
            print(f"  ! Makler-Website {domain}: {ex}")
            emails = (entry or {}).get("emails", [])
        entry = cache[domain] = {"emails": emails[:60], "t": int(time.time())}
        print(f"  Makler-Website {domain}: {len(emails)} Mail-Adresse(n)")
    return best_email(entry.get("emails", []), contact)
