import json
import re

import lzstring

from common import Listing, find_emails, find_phone, get, parse_number

BASE = "https://www.immowelt.at"
PATHS = {
    "1040": "wieden-1040/ad09at4", "1050": "margareten-1050/ad09at5",
    "1060": "mariahilf-1060/ad09at6", "1070": "neubau-1070/ad09at7",
}


def _page_props(html):
    m = re.search(r'window\["__UFRN_FETCHER__"\]=JSON\.parse\((".*?")\);?\s*</script>', html, re.S)
    if not m:
        return None
    d = json.loads(json.loads(m.group(1)))
    raw = (d.get("data") or {}).get("classified-serp-init-data")
    if not raw:
        return None
    return json.loads(lzstring.LZString().decompressFromBase64(raw)).get("pageProps")


def _clean_title(t):
    # immowelt hängt teils "Makler | Titel | Zusatz" zusammen – den längsten Teil nehmen
    parts = [p.strip() for p in t.split("|") if p.strip()]
    return max(parts, key=len) if parts else t


# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True}


def fetch():
    STATE["complete"] = True
    out = []
    for zip_, path in PATHS.items():
        for page in range(1, 6):
            r = get(f"{BASE}/suche/mieten/wohnung/wien-1010/{path}?order=DateDesc&page={page}")
            if not r:
                STATE["complete"] = False
                break
            pp = _page_props(r.text)
            if not pp:
                print("  ! immowelt: Struktur unerwartet")
                STATE["complete"] = False
                break
            data = pp.get("classifiedsData") or {}
            for cid in pp.get("classifieds") or []:
                c = data.get(cid)
                if not c:
                    continue
                hf = c.get("hardFacts") or {}
                facts = {f.get("type"): f.get("splitValue") for f in hf.get("facts") or []}
                price = hf.get("price") or {}
                addr = ((c.get("location") or {}).get("address")) or {}
                imgs = ((c.get("gallery") or {}).get("images")) or []
                meta = c.get("metadata") or {}
                prov = c.get("provider") or {}
                out.append(Listing(
                    source="immowelt",
                    source_id=cid,
                    url=f"{BASE}/expose/{meta.get('legacyId') or cid}",
                    title=_clean_title((c.get("mainDescription") or {}).get("headline") or hf.get("title") or "Wohnung zur Miete"),
                    price=parse_number(price.get("ariaLabel") or price.get("value")),
                    price_note=((price.get("addition") or {}).get("value")) or price.get("additionalInformation") or "",
                    zip=addr.get("zipCode") or zip_,
                    area=parse_number(facts.get("livingSpace")),
                    rooms=parse_number(facts.get("numberOfRooms")),
                    address=" ".join(x for x in [addr.get("street"), addr.get("zipCode"), "Wien"] if x),
                    image=imgs[0].get("url", "") if imgs else "",
                    description=(c.get("mainDescription") or {}).get("description") or "",
                    published=meta.get("creationDate") or "",
                    advertiser=(prov.get("intermediaryCard") or {}).get("title") or prov.get("title") or "",
                ))
            total = pp.get("totalCount") or 0
            if page * 30 >= total:
                break
            if page == 5:
                STATE["complete"] = False  # Seitenlimit erreicht
    return out


def enrich(l: Listing):
    r = get(l.url)
    if not r:
        return
    html = r.text
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r'"description"\s*:\s*"(.{40,4000}?)"', html)
    if m:
        try:
            l.description = re.sub(r"\s+", " ", json.loads('"' + m.group(1) + '"')).strip()
        except json.JSONDecodeError:
            pass
    emails = find_emails(l.description)
    if emails:
        l.email = emails[0]
    l.phone = find_phone(l.description) or ""
