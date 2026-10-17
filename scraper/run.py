"""Sammelt alle Quellen, filtert, führt Duplikate zusammen und schreibt docs/data/listings.json."""
import hashlib
import json
import os
import re
import sys
import traceback
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

from common import COLLECT_MAX_PRICE, DISTRICTS, Listing  # noqa: E402
from sources import derstandard, immmo, immoscout, immowelt, willhaben  # noqa: E402

SOURCES = {
    "willhaben": willhaben,
    "derstandard": derstandard,
    "immoscout24": immoscout,
    "immowelt": immowelt,
    "immmo": immmo,
}
SOURCE_LABELS = {
    "willhaben": "willhaben", "derstandard": "DER STANDARD", "immoscout24": "ImmoScout24",
    "immowelt": "immowelt", "immmo": "IMMMO",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "docs", "data", "listings.json")

ENRICH_MAX_PRICE = 750      # nur für diese Inserate Detailseiten laden
ENRICH_LIMIT = 60           # max. Detailseiten pro Lauf
EXPIRE_DAYS = 4             # Inserat verschwindet, wenn so lange nicht mehr gesehen

# Harte Ausschlüsse – Titel
EXCLUDE_TITLE = [
    (r"\bWG\b(?![- ]?(geeignet|tauglich|fähig))|WG-Zimmer|Mitbewohner|\bZimmer in\b|Zimmer zu vermieten|Untermiet.*Zimmer", "WG-Zimmer"),
    (r"tausch", "Wohnungstausch"),
    (r"\b(Lager|Garage|Stellplatz|Parkplatz|Büro|Geschäftslokal|Gewerbe|Kellerabteil|Praxis|Ordination)", "keine Wohnung"),
    (r"kurzzeit|short[- ]?term|ferienwohnung|tageweise|wochenweise|monteur|airbnb", "Kurzzeitmiete"),
    (r"^\s*\(?(reserviert|vergeben|vermietet)\)?|\b(reserviert|vergeben)\b", "reserviert/vergeben"),
    (r"^\s*(suche|gesucht|wir suchen|ich suche)\b", "Gesuch"),
]
# Harte Ausschlüsse – Beschreibung (Bad/Küche fehlt)
EXCLUDE_DESC = [
    (r"WC am Gang|Gang[- ]?WC|Etagen[- ]?(WC|dusche)|Kategorie D|ohne (Bad|Dusche)|kein (Bad|Badezimmer)|Gemeinschafts(bad|küche|dusche)", "kein eigenes Bad/WC"),
    (r"ohne Küche|keine Küche", "keine Küche"),
]

FLAG_RULES = [
    (r"gemeinde(bau|wohnung)|wiener wohnen|direktvergabe|wohn-?ticket", "Gemeindebau – Wohn-Ticket nötig"),
    (r"\bbefristet|befristung", "befristet"),
    (r"unbefristet", "unbefristet"),
    (r"möbliert|furnished", "möbliert"),
    (r"provisionsfrei|ohne provision|keine provision", "provisionsfrei"),
    (r"balkon", "Balkon"),
    (r"terrasse", "Terrasse"),
    (r"loggia", "Loggia"),
    (r"garten", "Garten"),
    (r"\blift\b|aufzug", "Lift"),
    (r"altbau", "Altbau"),
    (r"neubau|erstbezug", "Neubau/Erstbezug"),
    (r"genossenschaft", "Genossenschaft"),
    (r"(?<!keine )(?<!ohne )(?<!keine\n)ablöse(?!frei)", "Ablöse"),
]


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def exclusion_reason(l: Listing):
    if l.price is None or l.price < 100:
        return "kein Preis"
    if l.price > COLLECT_MAX_PRICE:
        return "zu teuer"
    if l.zip not in DISTRICTS:
        return "falscher Bezirk"
    if l.area is not None and l.area < 15:
        return "zu klein (Zimmer?)"
    for rx, why in EXCLUDE_TITLE:
        # "unbefristet vergeben" o. ä. in Beschreibungen ignorieren – nur Titel prüfen
        if re.search(rx, l.title or "", re.I):
            if why == "reserviert/vergeben" and re.search(r"wird vergeben|zu vergeben", l.title, re.I):
                continue
            return why
    for rx, why in EXCLUDE_DESC:
        if re.search(rx, l.description or "", re.I):
            return why
    return None


def flags_for(l: Listing, prev_flags=None):
    text = " ".join([l.title or "", l.description or "", " ".join(l.tags or [])]).lower()
    flags = []
    for rx, name in FLAG_RULES:
        if re.search(rx, text, re.I) and name not in flags:
            flags.append(name)
    if "unbefristet" in flags and "befristet" in flags:
        flags.remove("befristet")
    if l.private:
        flags.append("privat")
    if "flatbee" in (l.url or ""):
        flags.append("Bezahlportal")
    return flags


def same_flat(a: dict, l: Listing) -> bool:
    if a["zip"] != l.zip or not a.get("price") or not l.price:
        return False
    if abs(a["price"] - l.price) > max(5, 0.02 * l.price):
        return False
    if a.get("area") and l.area:
        return abs(a["area"] - l.area) <= 1.5
    return False


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"items": []}


def main():
    data = load()
    items = {it["id"]: it for it in data.get("items", [])}
    key_to_item = {k: it["id"] for it in items.values() for k in it.get("keys", [])}
    run_at = now_iso()
    status = {}
    collected = []

    for name, mod in SOURCES.items():
        print(f"→ {name}")
        if name == "immmo" and not status.get("derstandard", {}).get("count"):
            # derStandard blockt Cloud-Server – dann deren Inserate über IMMMO mitnehmen
            immmo.SKIP_HOSTS = tuple(h for h in immmo.SKIP_HOSTS if h != "derstandard.at")
            print("  (derStandard direkt nicht erreichbar – nehme derStandard-Inserate über IMMMO)")
        try:
            res = mod.fetch()
            # Duplikate innerhalb einer Quelle entfernen
            seen, uniq = set(), []
            for l in res:
                if l.key not in seen:
                    seen.add(l.key)
                    uniq.append(l)
            collected += [(name, l) for l in uniq]
            status[name] = {"ok": True, "count": len(uniq)}
            print(f"  {len(uniq)} Inserate")
        except Exception as e:  # eine kaputte Quelle soll den Rest nicht stoppen
            traceback.print_exc()
            status[name] = {"ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"[:200]}

    excluded = {}
    enrich_budget = ENRICH_LIMIT
    for name, l in collected:
        why = exclusion_reason(l)
        if why:
            excluded[why] = excluded.get(why, 0) + 1
            continue

        item_id = key_to_item.get(l.key)
        if not item_id:
            item_id = next((iid for iid, it in items.items() if same_flat(it, l)), None)
        is_new_key = l.key not in key_to_item

        if item_id is None:
            item_id = hashlib.sha1(l.key.encode()).hexdigest()[:12]
            items[item_id] = {
                "id": item_id, "keys": [], "links": [], "first_seen": run_at,
                "title": l.title, "price": l.price, "price_note": l.price_note, "zip": l.zip,
                "district": DISTRICTS.get(l.zip, ""), "area": l.area, "rooms": l.rooms,
                "address": l.address, "image": l.image, "description": "", "published": l.published,
                "advertiser": l.advertiser, "email": "", "phone": "", "tags": [], "flags": [],
            }
        it = items[item_id]
        key_to_item[l.key] = item_id
        if l.key not in it["keys"]:
            it["keys"].append(l.key)
        if not any(x["source"] == name for x in it["links"]):
            it["links"].append({"source": name, "label": SOURCE_LABELS[name], "url": l.url})
        it["last_seen"] = run_at

        # Detailseite laden, wenn neu und im Budget-Umfeld
        if is_new_key and l.price <= ENRICH_MAX_PRICE and enrich_budget > 0 and not it.get("email"):
            enrich_budget -= 1
            try:
                SOURCES[name].enrich(l)
            except Exception:
                traceback.print_exc()
            # Nach dem Anreichern nochmal auf Ausschluss prüfen (z. B. "WC am Gang" in Beschreibung)
            why = exclusion_reason(l)
            if why:
                excluded[why] = excluded.get(why, 0) + 1
                it["excluded"] = why

        # Felder ergänzen – bessere Werte gewinnen
        if l.price_note == "Gesamtmiete" and it.get("price_note") != "Gesamtmiete":
            it["price"], it["price_note"] = l.price, l.price_note
        for k in ("area", "rooms", "image", "address", "advertiser", "published"):
            if not it.get(k) and getattr(l, k):
                it[k] = getattr(l, k)
        if len(l.description or "") > len(it.get("description") or ""):
            it["description"] = l.description[:2500]
        if l.email and not it.get("email"):
            it["email"] = l.email
        if l.phone and not it.get("phone"):
            it["phone"] = l.phone
        it["tags"] = sorted(set(it.get("tags", [])) | set(l.tags or []))
        it["flags"] = sorted(set(it.get("flags", [])) | set(flags_for(l)))
        # Vergleichspreis: Gesamtmiete; bei Netto-Angaben grob geschätzt (+ ca. 3,2 €/m² BK inkl. USt.)
        note = (it.get("price_note") or "").lower()
        if ("netto" in note or "kalt" in note) and it.get("area"):
            it["price_total"] = round(it["price"] + it["area"] * 3.2)
            it["price_estimated"] = True
        else:
            it["price_total"] = it["price"]
            it["price_estimated"] = False
        if it.get("area"):
            it["ppsqm"] = round(it["price_total"] / it["area"], 2)

    # Abgelaufene entfernen
    cutoff = (datetime.now(timezone.utc) - timedelta(days=EXPIRE_DAYS)).isoformat()
    kept = [it for it in items.values() if it.get("last_seen", "") >= cutoff]
    kept.sort(key=lambda it: it["first_seen"], reverse=True)

    out = {
        "updated": run_at,
        "sources": status,
        "excluded": excluded,
        "items": kept,
    }
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    in_budget = sum(1 for it in kept if it["price_total"] <= 650 and not it.get("excluded"))
    print(f"\n✓ {len(kept)} Wohnungen gespeichert ({in_budget} ≤ 650 €). Ausgeschlossen: {excluded}")


if __name__ == "__main__":
    main()
