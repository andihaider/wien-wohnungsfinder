"""Einzelne Makler und Bauträger, deren Wohnungen (meist) NICHT auf den großen Portalen stehen.

- justimmo-Makler: Brezina, TICON (weitere justimmo-Seiten einfach in JUSTIMMO ergänzen)
- ARWAG: nur Objekte, deren Koordinaten im 4.–7. Bezirk liegen
- Siedlungsunion: "Sofort wohnen"-Liste (PLZ steht im Link)
"""
import re

from bs4 import BeautifulSoup

from common import (COLLECT_MAX_PRICE, DISTRICTS, Listing, find_emails, find_phone, get,
                    parse_detail_text, zip_from_text)

# Name, Listen-URL (Mietwohnungen) – alle laufen auf der Makler-Software justimmo
JUSTIMMO = [
    ("Brezina Immobilien", "https://brezina.at/mieten"),
    ("TICON Immobilien", "https://www.ticon.cc/mietwohnung"),
]
ARWAG_GEO = "https://www.arwag.at/immobiliensuche/realties-geo.json"
ARWAG_DETAIL = "https://www.arwag.at/immobiliensuche/lazylist/link/Realties/{id}"
# grobes Rechteck um Wieden, Margareten, Mariahilf, Neubau (PLZ wird danach auf der Detailseite geprüft)
BOX = (48.180, 48.207, 16.330, 16.375)
SIEDLUNGSUNION = "https://www.siedlungsunion.at/wohnen/sofort"

# Makler-Listen werden nur auf der ersten Seite gelesen → "fehlt in der Liste" heißt nicht offline
STATE = {"complete": False, "raw": 0}  # raw = Inserate vor dem Bezirks-/Preisfilter


def _text(soup):
    for t in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _card(a):
    """Kleinster Container um einen Inserats-Link, der noch wie eine einzelne Karte aussieht."""
    el = a
    while el.parent is not None and len(el.parent.get_text(" ", strip=True)) < 700:
        el = el.parent
    return el


def _justimmo(name, url):
    out = []
    r = get(url)
    if not r:
        return out
    base = re.match(r"https?://[^/]+", url).group(0)
    soup = BeautifulSoup(r.text, "lxml")
    seen = set()
    for a in soup.select('a[href*="/objekt/"]'):
        m = re.search(r"/objekt/(\d+)", a["href"])
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        STATE["raw"] += 1
        card = _card(a)
        txt = card.get_text(" | ", strip=True)
        d = parse_detail_text(txt)
        zip_ = d.get("zip") or zip_from_text(txt)
        price = d.get("price")
        if zip_ not in DISTRICTS or not price or price > COLLECT_MAX_PRICE:
            continue
        if re.search(r"\b(Büro|Geschäftslokal|Garage|Stellplatz|Lager)\b", txt, re.I) and not re.search(r"wohnung", txt, re.I):
            continue
        h = card.find(["h2", "h3", "h4"])
        title = (h.get_text(" ", strip=True) if h else txt.split("|")[0]).strip(" |,")
        img = card.find("img")
        l = Listing(
            source="makler", source_id=f"justimmo-{m.group(1)}", url=f"{base}/objekt/{m.group(1)}",
            title=title[:160], price=price, price_note=d.get("price_note") or "Miete", zip=zip_,
            area=d.get("area"), rooms=d.get("rooms"), address=f"{zip_} Wien",
            image=(img.get("data-src") or img.get("src") or "") if img else "", advertiser=name,
        )
        l.source_label = name
        out.append(l)
    return out


def _arwag():
    out = []
    r = get(ARWAG_GEO)
    if not r:
        return out
    lat0, lat1, lon0, lon1 = BOX
    feats = r.json().get("features") or []
    STATE["raw"] += len(feats)
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            continue
        d_r = get(ARWAG_DETAIL.format(id=f["id"]))
        if not d_r or "miete" not in d_r.url or "gewerbe" in d_r.url:
            continue
        soup = BeautifulSoup(d_r.text, "lxml")
        title = (soup.title.get_text(strip=True) if soup.title else f["properties"].get("title", "ARWAG")).split("|")[0]
        img = soup.find("meta", property="og:image")
        d = parse_detail_text(_text(soup))
        zip_ = d.get("zip")
        if zip_ not in DISTRICTS or not d.get("price") or d["price"] > COLLECT_MAX_PRICE:
            continue
        l = Listing(
            source="makler", source_id=f"arwag-{f['id']}", url=d_r.url, title=title.strip()[:160],
            price=d["price"], price_note=d.get("price_note", ""), zip=zip_, area=d.get("area"), rooms=d.get("rooms"),
            address=f["properties"].get("title", ""), image=img["content"] if img else "", advertiser="ARWAG",
            phone=d.get("phone", ""), email=d.get("email", ""),
        )
        l.eigenmittel = d.get("eigenmittel")
        l.source_label = "ARWAG"
        out.append(l)
    return out


def _siedlungsunion():
    out = []
    r = get(SIEDLUNGSUNION)
    if not r:
        return out
    soup = BeautifulSoup(r.text, "lxml")
    links = {a["href"] for a in soup.select('a[href*="/wohnen/sofort/"]')}
    STATE["raw"] += len(links)
    for href in links:
        m = re.search(r"/wohnen/sofort/(1\d{2}0)-", href)
        if not m or m.group(1) not in DISTRICTS:
            continue
        url = href if href.startswith("http") else "https://www.siedlungsunion.at" + href
        d_r = get(url)
        if not d_r:
            continue
        txt = _text(BeautifulSoup(d_r.text, "lxml"))
        d = parse_detail_text(txt)
        pm = re.search(r"SOFORT WOHNEN.{0,40}?m\s?2\s*([\d.,]+)", txt)
        price = d.get("price") or (float(pm.group(1).replace(",", ".")) if pm else None)
        if not price or price > COLLECT_MAX_PRICE:
            continue
        am = re.search(r"(1\d{2}0 Wien,? [^|]{3,60}?)\s+(?:1\d{2}0|Karte)", txt)
        l = Listing(
            source="makler", source_id="su-" + href.rstrip("/").split("/")[-1], url=url,
            title=f"Siedlungsunion: {am.group(1) if am else 'Sofort wohnen'}", price=price,
            price_note="Miete laut Genossenschaft", zip=m.group(1), area=d.get("area"), rooms=d.get("rooms"),
            address=am.group(1) if am else f"{m.group(1)} Wien", advertiser="Siedlungsunion", tags=["Genossenschaft"],
        )
        l.eigenmittel = d.get("eigenmittel")
        l.source_label = "Siedlungsunion"
        out.append(l)
    return out


def fetch():
    STATE["raw"] = 0
    out = []
    for name, url in JUSTIMMO:
        out += _justimmo(name, url)
    out += _arwag()
    out += _siedlungsunion()
    return out


def enrich(l: Listing):
    """Detailseite: Gesamtmiete, Eigenmittel, Kontakt, Beschreibung."""
    r = get(l.url)
    if not r:
        return
    soup = BeautifulSoup(r.text, "lxml")
    txt = _text(soup)
    d = parse_detail_text(txt)
    if d.get("price_note") == "Gesamtmiete" and d.get("price"):
        l.price, l.price_note = d["price"], "Gesamtmiete"
    l.eigenmittel = l.eigenmittel or d.get("eigenmittel")
    l.email = l.email or d.get("email") or (find_emails(r.text) or [""])[0]
    l.phone = l.phone or d.get("phone") or find_phone(txt)
    m = re.search(r"(?:Objektbeschreibung|Beschreibung)\s*(.{40,1500}?)(?:Ausstattung|Lage|Energieausweis|Kontakt|Anfrage)", txt)
    if m:
        l.description = m.group(1).strip()
