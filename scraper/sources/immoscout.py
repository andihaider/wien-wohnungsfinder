import json
import re

from bs4 import BeautifulSoup

from common import COLLECT_MAX_PRICE, Listing, find_emails, find_phone, get

BASE = "https://www.immobilienscout24.at"
SLUGS = {
    "1040": "4-bezirk-wieden", "1050": "5-bezirk-margareten",
    "1060": "6-bezirk-mariahilf", "1070": "7-bezirk-neubau",
}

BADGE_TAGS = {
    "BALCONY": "Balkon", "TERRACE": "Terrasse", "GARDEN": "Garten", "LOGGIA": "Loggia",
    "ELEVATOR": "Lift", "COMMISSION_FREE": "provisionsfrei", "FURNISHED_FULL": "möbliert",
    "FURNISHED_PARTIAL": "teilmöbliert",
}


def _state(html):
    i = html.find("window.__INITIAL_STATE__")
    if i < 0:
        return None
    j = html.find("{", i)
    k = html.find("</script>", j)
    raw = html[j:k].strip().rstrip(";")
    raw = re.sub(r":\s*undefined", ":null", raw)
    raw = re.sub(r"\[undefined\]", "[null]", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        o, _ = json.JSONDecoder().raw_decode(raw)
        return o


def _find_hits(o):
    if isinstance(o, dict):
        if isinstance(o.get("hits"), list) and o["hits"] and isinstance(o["hits"][0], dict) and "exposeId" in o["hits"][0]:
            return o["hits"]
        for v in o.values():
            h = _find_hits(v)
            if h:
                return h
    elif isinstance(o, list):
        for v in o:
            h = _find_hits(v)
            if h:
                return h
    return None


# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True}


def fetch():
    STATE["complete"] = True
    out = []
    for zip_, slug in SLUGS.items():
        for page in range(1, 5):
            url = f"{BASE}/regional/wien/wien/{slug}/wohnung-mieten?primaryPriceTo={COLLECT_MAX_PRICE}"
            if page > 1:
                url += f"&pageNumber={page}"
            r = get(url)
            if not r:
                STATE["complete"] = False
                break
            st = _state(r.text)
            hits = _find_hits(st) or []
            for h in hits:
                if (h.get("meta") or {}).get("transferType") not in (None, "RENT"):
                    continue
                pic = (h.get("primaryPictureImageProps") or {}).get("src") or ""
                badges = [((b.get("details") or {}).get("value")) for b in (h.get("typedBadges") or [])]
                addr = h.get("addressString") or ""
                rc = h.get("realtorContact") or {}
                out.append(Listing(
                    source="immoscout24",
                    source_id=h["exposeId"],
                    url=f"{BASE}/expose/{h['exposeId']}",
                    title=h.get("headline") or "",
                    price=h.get("primaryPrice"),
                    price_note="Gesamtmiete",
                    zip=(re.search(r"\b1\d{3}\b", addr) or [zip_])[0],
                    area=h.get("primaryArea"),
                    rooms=h.get("numberOfRooms"),
                    address=addr,
                    image=pic,
                    published=h.get("dateCreated") or "",
                    advertiser=" ".join(x for x in [rc.get("company"), rc.get("name")] if x),
                    private=h.get("isPrivate"),
                    tags=[BADGE_TAGS[b] for b in badges if b in BADGE_TAGS]
                    + (["Gemeinde/gefördert"] if h.get("isSocialHousing") else []),
                ))
            if len(hits) < 20:
                break
            if page == 4:
                STATE["complete"] = False  # Seitenlimit erreicht
    return out


def enrich(l: Listing):
    r = get(l.url)
    if not r:
        return
    soup = BeautifulSoup(r.text, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Objektbeschreibung(.{30,3000}?)(?:Ausstattung|Lage|Sonstiges|Energieausweis|Anbieter)", text)
    if m:
        l.description = m.group(1).strip()
    emails = find_emails(l.description)
    if emails:
        l.email = emails[0]
    l.phone = find_phone(l.description)
