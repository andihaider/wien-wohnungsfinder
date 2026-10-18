"""WG-Gesucht: WG-Zimmer (eigene Kategorie) und ganze Wohnungen in Wien."""
import random
import re
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from common import COLLECT_MAX_PRICE, DISTRICTS, Listing, find_emails, find_phone, get, parse_number

BASE = "https://www.wg-gesucht.de"
LISTS = [
    # (Kategorie, URL-Muster, Seiten)
    ("wg", BASE + "/wg-zimmer-in-Wien.163.0.1.{p}.html", 8),
    ("wohnung", BASE + "/wohnungen-in-Wien.163.2.1.{p}.html", 4),
]
# Es werden nur die neuesten Seiten gelesen – ältere, noch aktive Inserate fehlen also in der Liste.
STATE = {"complete": False}
DETAIL_LIMIT = 15  # Detailseiten pro Lauf, um fehlende Bezirke nachzuschlagen


class Blocked(Exception):
    """WG-Gesucht zeigt eine Captcha-Prüfseite – wir umgehen die nicht, sondern versuchen es später wieder."""


def _check_blocked(r):
    if "cuba.html" in r.url or "<title>Überprüfung" in r.text[:5000]:
        raise Blocked("Prüfseite (Captcha) – später erneut")


def _district_zip(text):
    m = re.search(r"\b(\d{1,2})\.\s*Bezirk", text or "")
    if m:
        return f"1{int(m.group(1)):02d}0"
    m = re.search(r"\b(1[0-2]\d0)\b", text or "")
    return m.group(1) if m else None


def _online_since(text):
    """'Online: 37 Min.' / '3 Std.' / '2 Tage' / '02.09.2026' -> ISO-Zeit"""
    now = datetime.now(timezone.utc)
    t = text or ""
    m = re.search(r"(\d+)\s*Min", t)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*Std", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*Tag", t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", t)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc).isoformat()
    return ""


def fetch():
    out = []
    details_left = DETAIL_LIMIT
    for category, pattern, pages in LISTS:
        misses = 0
        for p in range(pages):
            time.sleep(random.uniform(2.5, 5))  # WG-Gesucht reagiert empfindlich auf schnelle Abrufe
            r = get(pattern.format(p=p))
            if not r:
                misses += 1
                if misses >= 2:
                    break
                time.sleep(15)
                continue
            _check_blocked(r)
            soup = BeautifulSoup(r.text, "lxml")
            cards = soup.select("a.offer_list_item")
            for c in cards:
                price = parse_number((c.select_one(".price-row .card-main-text") or c).get_text(" ", strip=True))
                if price is None or price > COLLECT_MAX_PRICE:
                    continue
                sub_el = c.select_one(".ad-subtitle")
                sub = re.sub(r"\s+", " ", sub_el.get_text(" ", strip=True)) if sub_el else ""
                title = (c.get("aria-label") or (c.select_one(".ad-title") or c).get_text(" ", strip=True)).strip()
                size = parse_number((c.select_one(".size-value") or {}).get_text() if c.select_one(".size-value") else None)
                url = BASE + c["href"] if c["href"].startswith("/") else c["href"]
                zip_ = _district_zip(sub) or _district_zip(title)
                desc = ""
                if not zip_ and details_left > 0:
                    # Bezirk fehlt in der Liste – Detailseite nachschlagen
                    details_left -= 1
                    time.sleep(random.uniform(2, 4))
                    d = get(url)
                    if d and "cuba.html" not in d.url:
                        txt = BeautifulSoup(d.text, "lxml").get_text(" ", strip=True)
                        zip_ = _district_zip(txt)
                if zip_ not in DISTRICTS:
                    continue
                wg_size = None
                m = re.search(r"(\d+)er\s*WG", sub)
                if m:
                    wg_size = int(m.group(1))
                img = c.select_one("img.top-image-card")
                bottom = c.select_one(".bottom-card")
                private = bool(c.select_one(".user-badge")) and "Privat" in c.select_one(".user-badge").get_text()
                l = Listing(
                    source="wggesucht",
                    source_id=c.get("data-id") or url,
                    url=url,
                    title=title,
                    price=price,
                    price_note="Gesamtmiete",
                    zip=zip_,
                    area=size,
                    address=" · ".join(x.strip() for x in sub.split("·")[1:]),
                    image=img.get("src", "") if img else "",
                    description=desc,
                    published=_online_since(bottom.get_text(" ", strip=True) if bottom else ""),
                    advertiser="Privat" if private else "",
                    private=private,
                )
                l.category = category
                l.wg_size = wg_size
                out.append(l)
            if len(cards) < 20:
                break
    return out


def enrich(l: Listing):
    r = get(l.url)
    if not r:
        return
    soup = BeautifulSoup(r.text, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    blocks = [b.get_text(" ", strip=True) for b in soup.select("[id^=freitext_]")]
    text = " ".join(blocks) or soup.get_text(" ", strip=True)
    l.description = re.sub(r"\s+", " ", text)[:2500]
    emails = find_emails(l.description)
    if emails:
        l.email = emails[0]
    l.phone = find_phone(l.description)
