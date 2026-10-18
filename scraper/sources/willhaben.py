import json
import re

from common import COLLECT_MAX_PRICE, Listing, find_emails, find_phone, get, parse_number

# willhaben-areaIds der Wiener Bezirke
AREA_IDS = {"1040": 117226, "1050": 117227, "1060": 117228, "1070": 117229}
BASE = "https://www.willhaben.at"


def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True}


def fetch():
    STATE["complete"] = True
    areas = "&".join(f"areaId={a}" for a in AREA_IDS.values())
    out = []
    for page in range(1, 6):
        url = (f"{BASE}/iad/immobilien/mietwohnungen/wien?{areas}"
               f"&PRICE_TO={COLLECT_MAX_PRICE}&rows=90&sort=1&page={page}")
        r = get(url)
        if not r:
            STATE["complete"] = False
            break
        d = _next_data(r.text)
        try:
            sr = d["props"]["pageProps"]["searchResult"]
            ads = sr["advertSummaryList"]["advertSummary"]
        except (TypeError, KeyError):
            print("  ! willhaben: Struktur unerwartet")
            STATE["complete"] = False
            break
        for a in ads:
            at = {x["name"]: x["values"] for x in a["attributes"]["attribute"]}
            g = lambda k: (at.get(k) or [None])[0]
            img = g("MMO")
            out.append(Listing(
                source="willhaben",
                source_id=str(a["id"]),
                url=f"{BASE}/iad/{g('SEO_URL')}" if g("SEO_URL") else f"{BASE}/iad/object?adId={a['id']}",
                title=a.get("description") or g("HEADING") or "",
                price=parse_number(g("PRICE")),
                price_note="Gesamtmiete",
                zip=g("POSTCODE"),
                area=parse_number(g("ESTATE_SIZE/LIVING_AREA") or g("ESTATE_SIZE")),
                rooms=parse_number(g("NUMBER_OF_ROOMS")),
                address=g("ADDRESS") or g("LOCATION") or "",
                image=f"https://cache.willhaben.at/mmo/{img}" if img else "",
                description=g("BODY_DYN") or "",
                published=g("PUBLISHED_String") or "",
                advertiser=g("ORGNAME") or ("Privat" if g("ISPRIVATE") == "1" else ""),
                private=g("ISPRIVATE") == "1",
                tags=list(at.get("FREE_AREA_TYPE_NAME") or []),
            ))
        if len(ads) < 90:
            break
        if page == 5:
            STATE["complete"] = False  # Seitenlimit erreicht
    return out


def enrich(l: Listing):
    """Detailseite: vollständige Beschreibung, Telefon, ggf. E-Mail."""
    r = get(l.url)
    if not r:
        return
    d = _next_data(r.text)
    try:
        ad = d["props"]["pageProps"]["advertDetails"]
    except (TypeError, KeyError):
        return
    attrs = {x["name"]: x["values"] for x in ad.get("attributes", {}).get("attribute", [])}
    desc = " ".join((attrs.get("DESCRIPTION") or attrs.get("GENERAL_TEXT_ADVERT/Beschreibung") or []))
    texts = [v[0] for k, v in attrs.items() if k.startswith(("DESCRIPTION", "GENERAL_TEXT")) and v]
    full = re.sub(r"<[^>]+>", " ", " ".join(texts) or desc)
    if full.strip():
        l.description = re.sub(r"\s+", " ", full).strip()[:3000]
    contact = {}
    for cd in (ad.get("advertContactDetails") or {}).get("contactDetail", []):
        for f in cd.get("contactDetailField", []):
            contact[f.get("id")] = f.get("value")
    l.phone = contact.get("phoneNo") or contact.get("phone") or contact.get("phoneNo2") or find_phone(l.description)
    if contact.get("contactName") and not l.private:
        l.advertiser = f"{l.advertiser} ({contact['contactName']})" if l.advertiser else contact["contactName"]
    emails = find_emails(contact.get("email", "") + " " + l.description)
    if emails:
        l.email = emails[0]
