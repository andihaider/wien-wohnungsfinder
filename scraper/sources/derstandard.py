import json
import re

from bs4 import BeautifulSoup

from common import Listing, find_emails, find_phone, get, next_f_payload

BASE = "https://immobilien.derstandard.at"
SLUGS = {"1040": "wien-wieden", "1050": "wien-margareten", "1060": "wien-mariahilf", "1070": "wien-neubau"}

AMENITY_TAGS = {
    "BALCONY": "Balkon", "TERRACE": "Terrasse", "LOGGIA": "Loggia", "GARDEN": "Garten",
    "ELEVATOR": "Lift", "NO_COMMISSION_FEE": "provisionsfrei", "KITCHEN": "Küche",
    "FURNISHED": "möbliert", "BATHTUB": "Badewanne", "SHOWER": "Dusche",
}


def _entries(html):
    s = next_f_payload(html)
    i = s.find('{"__typename":"PaginatedPropertyEntriesResponse"')
    if i < 0:
        return [], 0
    o, _ = json.JSONDecoder().raw_decode(s[i:])
    return o.get("entries") or [], o.get("totalEntries") or 0


# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True}


def fetch():
    STATE["complete"] = True
    out = []
    for zip_, slug in SLUGS.items():
        for page in range(1, 8):
            r = get(f"{BASE}/suche/{slug}/mieten-wohnung" + (f"?page={page}" if page > 1 else ""))
            if not r:
                STATE["complete"] = False
                break
            entries, total = _entries(r.text)
            for e in entries:
                p = e.get("property") or {}
                costs = p.get("costs") or {}
                main = costs.get("main") or {}
                price = main.get("value")
                note = "Gesamtmiete" if main.get("kind") in ("BASE_RENT_PLUS_UTILITIES", "TOTAL_RENT") else ""
                for c in costs.get("details") or []:
                    if c.get("kind") == "TOTAL_RENT" and c.get("gross"):
                        price, note = c["gross"], "Gesamtmiete"
                areas = {a.get("kind"): a.get("value") for a in ((p.get("areas") or {}).get("details") or [])}
                loc = p.get("location") or {}
                imgs = ((e.get("media") or {}).get("images") or [])
                adv = e.get("advertiser") if isinstance(e.get("advertiser"), dict) else {}
                company = adv.get("company") if isinstance(adv.get("company"), dict) else {}
                amen = p.get("amenities") or []
                out.append(Listing(
                    source="derstandard",
                    source_id=str(e["id"]),
                    url=f"{BASE}/detail/{e['id']}",
                    title=e.get("title") or "",
                    price=float(price) if price is not None else None,
                    price_note=note,
                    zip=loc.get("zipCode") or zip_,
                    area=areas.get("LIVING_SPACE"),
                    rooms=areas.get("ROOM_COUNT"),
                    address=" ".join(x for x in [loc.get("street"), loc.get("zipCode"), "Wien"] if x),
                    image=imgs[0]["path"] if imgs else "",
                    published=((e.get("metaData") or {}).get("publishedAt") or ""),
                    advertiser=company.get("name") or "",
                    tags=[AMENITY_TAGS[a] for a in amen if a in AMENITY_TAGS],
                ))
            if not entries or page * 15 >= total:
                break
            if page == 7:
                STATE["complete"] = False  # Seitenlimit erreicht
    return out


def enrich(l: Listing):
    r = get(l.url)
    if not r:
        return
    html = r.text
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Beschreibung(.{50,3000}?)(?:Ausstattung|Kosten|Lage|Energie)", text)
    if m:
        l.description = m.group(1).strip()
    emails = find_emails(html)
    if emails:
        l.email = emails[0]
    tel = re.search(r'href="tel:([^"]+)"', html)
    l.phone = tel.group(1) if tel else find_phone(l.description)
