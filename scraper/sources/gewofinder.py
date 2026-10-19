"""GEWOFinder: offene Schnittstelle, die viele gemeinnützige Bauträger sammelt
(u. a. Sozialbau, GESIBA, Wien-Süd, ÖSW, ÖVW, BWSG, EBG, Familienwohnbau, Frieden, Neues Leben,
Heimat Österreich, WBV-GPA, GEWOG/Neue Heimat, ARWAG). Liefert Miete UND Eigenmittel."""
import re

from common import COLLECT_MAX_PRICE, DISTRICTS, Listing, get

API = "https://api.gewofinder.at/api/listings/"

# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True, "raw": 0}


def _zip(item):
    pc = str(item.get("postal_code") or "")
    if pc in DISTRICTS:
        return pc
    if pc:
        return None
    # PLZ fehlt oft – im Adress-/Linktext nach "1050" suchen (aber nicht nach dem Wort "Neubau",
    # das steckt in vielen Projektnamen)
    text = " ".join(str(item.get(k) or "") for k in ("address", "source_url"))
    for m in re.finditer(r"(?<!\d)(1\d{2}0)(?!\d)", text):
        if m.group(1) in DISTRICTS:
            return m.group(1)
    return None


def fetch():
    STATE["complete"], STATE["raw"] = True, 0
    out, page = [], 1
    while True:
        r = get(f"{API}?city=Wien&per_page=100&page={page}", headers={"Accept": "application/json"})
        if not r:
            STATE["complete"] = False
            break
        d = r.json()
        STATE["raw"] += len(d.get("items") or [])
        for it in d.get("items") or []:
            if it.get("status") != "active":
                continue
            zip_ = _zip(it)
            price = it.get("rent_monthly")
            if zip_ not in DISTRICTS or not price or price > COLLECT_MAX_PRICE:
                continue
            provider = it.get("provider_name") or "Genossenschaft"
            imgs = it.get("image_urls") or []
            l = Listing(
                source="gewofinder",
                source_id=it["id"],
                url=it.get("source_url") or "https://gewofinder.at/",
                title=f"{provider}: {it.get('address') or 'Genossenschaftswohnung'}",
                price=float(price),
                price_note="Miete laut Genossenschaft",
                zip=zip_,
                area=it.get("area_sqm"),
                rooms=it.get("rooms"),
                address=" ".join(x for x in [it.get("address"), zip_, "Wien"] if x),
                image=imgs[0] if imgs else "",
                published=it.get("first_seen_at") or "",
                advertiser=provider,
                tags=["Genossenschaft"],
            )
            l.eigenmittel = it.get("capital_contribution")
            l.source_label = f"{provider} (via GEWOFinder)"
            out.append(l)
        if page >= (d.get("pages") or 1) or page >= 20:
            break
        page += 1
    return out


def enrich(l: Listing):
    pass  # die Schnittstelle liefert schon alles Wichtige
