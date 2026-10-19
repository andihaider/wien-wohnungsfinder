"""Sammelt alle Quellen, filtert, führt Duplikate zusammen und schreibt docs/data/listings.json."""
import hashlib
import json
import os
import re
import sys
import time
import traceback
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

from common import COLLECT_MAX_PRICE, DISTRICTS, Listing, check_alive  # noqa: E402
from scoring import FLAT_MAX_PRICE, matches_default, score  # noqa: E402
from sources import derstandard, gewofinder, immmo, immoscout, immowelt, makler, wggesucht, willhaben  # noqa: E402

SOURCES = {
    "willhaben": willhaben,
    "derstandard": derstandard,
    "immoscout24": immoscout,
    "immowelt": immowelt,
    "wggesucht": wggesucht,
    "makler": makler,
    "gewofinder": gewofinder,
    "immmo": immmo,
}
SOURCE_LABELS = {
    "willhaben": "willhaben", "derstandard": "DER STANDARD", "immoscout24": "ImmoScout24",
    "immowelt": "immowelt", "wggesucht": "WG-Gesucht", "immmo": "IMMMO",
    "makler": "Makler-Website", "gewofinder": "GEWOFinder",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "docs", "data", "listings.json")
SAVED_MARKER = os.path.join(ROOT, ".saved-this-run")   # sagt notify.py, ob diesmal gespeichert wurde

# Die Suche läuft alle 5 Min. Schnelle Quellen (willhaben: 1 Anfrage, ImmoScout24: 4) jedes Mal,
# schwere bzw. empfindliche seltener – sonst drohen Sperren. Minuten seit dem letzten VERSUCH.
SOURCE_INTERVAL_MIN = {"immoscout24": 15, "immowelt": 60, "immmo": 60, "makler": 60, "gewofinder": 120, "wggesucht": 240}
# Nach einem Fehlschlag (z. B. derStandard sperrt Cloud-Server) erst so viel später erneut versuchen
FAIL_RETRY_MIN = {"derstandard": 360}
SAVE_EVERY_MIN = 30         # ohne inhaltliche Änderung höchstens so oft speichern (GitHub Pages: ~10 Builds/Std.)

GONE = "nicht mehr online"
CHECK_LIMIT = 15            # direkte Link-Prüfungen pro Lauf
CHECK_EVERY_H = 3           # dasselbe Inserat höchstens alle 3 Std. direkt prüfen

ENRICH_MAX_PRICE = 750      # nur für diese Inserate Detailseiten laden
ENRICH_LIMIT = 60           # max. Detailseiten pro Lauf
EXPIRE_DAYS = 4             # Inserat verschwindet, wenn so lange nicht mehr gesehen

# Gründe, die gar nicht erst gespeichert werden (sonst wäre "Aussortiert" voller teurer Wohnungen)
SILENT_REASONS = {"kein Preis", "zu teuer", "falscher Bezirk"}

WG_RX = re.compile(
    r"WG-?Zimmer|Zimmer in (einer |der |unserer |meiner |netter |schöner )?(\d+er[- ]?)?(WG|Wohngemeinschaft)"
    r"|\bin (einer |der )?\d+er[- ]?WG\b|Wohngemeinschaft|Mitbewohner|\bWG\b", re.I)
WG_NOT = re.compile(
    r"WG[- ]?(geeignet|tauglich|fähig|eignung|gründung)|(geeignet|ideal|perfekt|passend|optimal)\s+(für|als)\s+(eine\s+)?WG"
    r"|(für|als)\s+(eine\s+)?(\d+er[- ]?)?WG\b", re.I)

EXCLUDE_TITLE = [
    (r"tausch", "Wohnungstausch"),
    (r"kurzzeit|short[- ]?term|ferienwohnung|tageweise|wochenweise|monteur|airbnb", "Kurzzeitmiete"),
    (r"^\W*(reserviert|vergeben|vermietet)\b|\((reserviert|vergeben|vermietet)\)|\b(reserviert|vergeben|vermietet)\W*$",
     "reserviert/vergeben"),
    (r"studentenheim|wohnheim|heimplatz|doppelzimmer", "Wohnheim"),
    (r"\bnur\b.{0,30}?\bmieter(?:innen|\*innen|:innen)?\b", "nur für bestimmte Mieter"),
    (r"^\W*(suche|gesucht|wir suchen|ich suche)\b(?!.*nach(mieter|folger))", "Gesuch"),
]
NON_FLAT_RX = r"\b(Lager|Garage|Stellplatz|Parkplatz|Büro|Geschäftslokal|Gewerbe|Kellerabteil|Praxis|Ordination)"
FLAT_WORDS_RX = r"wohnung|zimmer|garconn|garçonn|apartment|appartement|loft|maisonette|dachgescho|studio|\bWG\b"
GEMEINDE_RX = r"gemeinde-?(bau|wohnung)|wiener wohnen|direktvergabe|wohn-?ticket"
# Nur für ganze Wohnungen: Bad/Küche muss in der Wohnung sein (in WGs ist Teilen normal)
EXCLUDE_DESC = [
    (r"WC am Gang|Gang[- ]?WC|Etagen[- ]?(WC|dusche)|Kategorie D|ohne (Bad|Dusche)|kein (Bad|Badezimmer)|Gemeinschafts(bad|küche|dusche)",
     "kein eigenes Bad/WC"),
    (r"ohne Küche|keine Küche", "keine Küche"),
]

FLAG_RULES = [
    (r"\bbefristet|befristung", "befristet"),
    (r"unbefristet", "unbefristet"),
    (r"möbliert|furnished", "möbliert"),
    (r"zwischenmiete|untermiete bis|\b\d+\s*months?\b|für \d+ monate\b|(november|dezember|jänner|januar)-untermiete", "Zwischenmiete"),
    (r"provisionsfrei|ohne provision|keine provision", "provisionsfrei"),
    (r"balkon", "Balkon"),
    (r"terrasse", "Terrasse"),
    (r"loggia", "Loggia"),
    (r"garten", "Garten"),
    (r"\blift\b|aufzug", "Lift"),
    (r"altbau", "Altbau"),
    (r"neubau|erstbezug", "Neubau/Erstbezug"),
    (r"saniert|renoviert", "saniert"),
    (r"genossenschaft", "Genossenschaft"),
    (r"flinta|frauen-?wg|mädl|mädels-?wg|\bnur (für )?(frauen|mädchen)|female only|women only|mitbewohnerin (gesucht|für)|suchen (eine )?mitbewohnerin", "nur Frauen/FLINTA*"),
    (r"(?<!keine )(?<!ohne )ablöse(?!frei)", "Ablöse"),
]


def _hours_since(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classify(l: Listing) -> str:
    if l.category == "wg":
        return "wg"
    t = l.title or ""
    return "wg" if WG_RX.search(t) and not WG_NOT.search(t) else "wohnung"


def exclusion_reason(l: Listing):
    t, d = l.title or "", l.description or ""
    if l.price is None or l.price < 100:
        return "kein Preis"
    if l.price > COLLECT_MAX_PRICE:
        return "zu teuer"
    if l.zip not in DISTRICTS:
        return "falscher Bezirk"
    if re.search(GEMEINDE_RX, t + " " + d, re.I):
        return "Gemeindebau (Wohn-Ticket nötig)"
    if re.search(NON_FLAT_RX, t, re.I) and not re.search(FLAT_WORDS_RX, t, re.I):
        return "keine Wohnung"
    for rx, why in EXCLUDE_TITLE:
        if re.search(rx, t, re.I):
            return why
    if l.category == "wohnung":
        if l.area is not None and l.area < 15:
            return "zu klein"
        for rx, why in EXCLUDE_DESC:
            if re.search(rx, d, re.I):
                return why
    return None


def flags_for(l: Listing):
    text = " ".join([l.title or "", l.description or "", " ".join(l.tags or [])]).lower()
    flags = [name for rx, name in FLAG_RULES if re.search(rx, text, re.I)]
    if "unbefristet" in flags and "befristet" in flags:
        flags.remove("befristet")
    if l.private:
        flags.append("privat")
    if "flatbee" in (l.url or ""):
        flags.append("Bezahlportal")
    return flags


def same_flat(a: dict, l: Listing) -> bool:
    if a.get("category", "wohnung") != l.category or a["zip"] != l.zip or not a.get("price") or not l.price:
        return False
    if abs(a["price"] - l.price) > max(5, 0.02 * l.price):
        return False
    if a.get("area") and l.area:
        return abs(a["area"] - l.area) <= 1.5
    return False


def mark_gone(items, status, run_at):
    """Inserate, die nicht mehr online sind, als "nicht mehr online" aussortieren.

    1. Eine Quelle hat diesmal ALLE Inserate geliefert und das Inserat fehlt darin → offline.
    2. Sonst (z. B. WG-Gesucht liest nur die neuesten Seiten) → Link direkt prüfen.
    Taucht es später wieder auf, hebt die normale Logik den Ausschluss automatisch auf.
    """
    complete = {n: bool(st.get("ok") and st.get("count") and not st.get("skipped")
                        and getattr(SOURCES[n], "STATE", {}).get("complete"))
                for n, st in status.items()}
    wg_ran = bool(status.get("wggesucht", {}).get("count")) and not status.get("wggesucht", {}).get("skipped")
    checks, gone = 0, 0
    skipped = {n for n, st in status.items() if st.get("skipped")}
    for it in items.values():
        if it.get("last_seen") == run_at or it.get("excluded"):
            continue
        srcs = {l["source"] for l in it["links"]}
        if srcs & skipped:
            continue  # Quelle wurde diesmal nicht abgefragt – fehlt also nicht wirklich
        # IMMMO-Inserate von Portalen, die IMMMO diesmal übersprungen hat, sagen nichts aus
        skipped_host = "immmo" in srcs and any(h in (it.get("advertiser") or "") for h in immmo.SKIP_HOSTS)
        if not skipped_host and all(complete.get(s) for s in srcs):
            it["excluded"], it["gone_at"] = GONE, run_at
            gone += 1
            continue
        if checks >= CHECK_LIMIT or it.get("price_total", 9999) > COLLECT_MAX_PRICE:
            continue
        if it.get("checked_at") and _hours_since(it["checked_at"]) < CHECK_EVERY_H:
            continue
        link = it["links"][0]
        if link["source"] == "wggesucht" and not wg_ran:
            continue  # WG-Gesucht nur prüfen, wenn es diesmal ohnehin abgefragt wurde (Captcha-Schutz)
        checks += 1
        it["checked_at"] = run_at
        if check_alive(link["url"], link["source"]) is False:
            it["excluded"], it["gone_at"] = GONE, run_at
            gone += 1
    print(f"  Verfügbarkeit: {gone} nicht mehr online, {checks} Links direkt geprüft")


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"items": []}


def _due(name, prev):
    """Soll die Quelle in diesem Lauf abgefragt werden?

    Uhrzeitbasiert statt über gespeicherte Zeitstempel, weil nicht jeder Lauf speichert:
    eine Quelle mit 30-Min.-Abstand läuft im Fenster :00–:05 und :30–:35 (UTC-Minuten seit 1970).
    Sicherheitsnetz: wurde das Fenster verpasst, läuft sie, sobald der letzte Versuch zu lange her ist.
    """
    if os.environ.get("FORCE_ALL"):
        return True  # zum Testen: alle Quellen abfragen
    interval = SOURCE_INTERVAL_MIN.get(name) or 0
    if prev and prev.get("last_attempt_ok") is False and name in FAIL_RETRY_MIN:
        interval = max(interval, FAIL_RETRY_MIN[name])
    if not interval:
        return True
    if int(time.time() // 60) % interval < 5:
        return True
    last = prev.get("last_try") or prev.get("last_ok")
    return not last or _hours_since(last) * 60 >= interval + 10


def fetch_all(prev_sources):
    status, collected = {}, []
    for name, mod in SOURCES.items():
        print(f"→ {name}")
        prev = prev_sources.get(name) or {}
        if not _due(name, prev):
            print("  übersprungen (seltener abgefragt, um Sperren zu vermeiden)")
            status[name] = dict(prev, skipped=True)
            continue
        if name == "immmo" and not status.get("derstandard", {}).get("count"):
            # derStandard blockt Cloud-Server – dann deren Inserate über IMMMO mitnehmen
            immmo.SKIP_HOSTS = tuple(h for h in immmo.SKIP_HOSTS if h != "derstandard.at")
            print("  (derStandard direkt nicht erreichbar – nehme derStandard-Inserate über IMMMO)")
        try:
            res = mod.fetch()
            seen, uniq = set(), []
            for l in res:
                if l.key not in seen:
                    seen.add(l.key)
                    uniq.append(l)
            collected += [(name, l) for l in uniq]
            st = {"ok": True, "count": len(uniq), "last_ok": now_iso() if uniq else prev.get("last_ok"), "last_try": now_iso(),
                  "last_attempt_ok": bool(uniq) or name in ("makler", "gewofinder")}
            print(f"  {len(uniq)} Inserate")
        except Exception as e:  # eine kaputte Quelle soll den Rest nicht stoppen
            if type(e).__name__ == "Blocked":
                print(f"  {e}")
            else:
                traceback.print_exc()
            msg = str(e) if type(e).__name__ == "Blocked" else f"{type(e).__name__}: {e}"
            st = {"ok": False, "count": 0, "error": msg[:200], "last_ok": prev.get("last_ok"), "last_try": now_iso(),
                  "last_attempt_ok": False}
        prev_streak = prev.get("empty_streak", 0)
        raw = getattr(mod, "STATE", {}).get("raw")
        if raw is not None and st["ok"]:
            st["raw"] = raw   # Makler/Genossenschaften: 0 Treffer in den gesuchten Bezirken ist normal, 0 Inserate insgesamt nicht
        st["empty_streak"] = prev_streak + 1 if not (st.get("raw") if raw is not None else st["count"]) else 0
        status[name] = st
    if not status["derstandard"]["count"] and status["immmo"]["count"]:
        status["derstandard"]["via"] = "immmo"
    return status, collected


def main():
    if os.path.exists(SAVED_MARKER):
        os.remove(SAVED_MARKER)
    data = load()
    items = {it["id"]: it for it in data.get("items", [])}
    key_to_item = {k: it["id"] for it in items.values() for k in it.get("keys", [])}
    run_at = now_iso()
    status, collected = fetch_all(data.get("sources") or {})

    excluded_counts = {}
    run_ok, run_why = set(), {}
    enrich_budget = ENRICH_LIMIT
    for name, l in collected:
        l.category = classify(l)
        why = exclusion_reason(l)
        if why in SILENT_REASONS:
            continue

        item_id = key_to_item.get(l.key)
        if not item_id:
            item_id = next((iid for iid, it in items.items() if same_flat(it, l)), None)
        is_new_key = l.key not in key_to_item

        if item_id is None:
            item_id = hashlib.sha1(l.key.encode()).hexdigest()[:12]
            items[item_id] = {
                "id": item_id, "keys": [], "links": [], "first_seen": run_at, "category": l.category,
                "title": l.title, "price": l.price, "price_note": l.price_note, "zip": l.zip,
                "district": DISTRICTS.get(l.zip, ""), "area": l.area, "rooms": l.rooms,
                "address": l.address, "image": l.image, "description": "", "published": l.published,
                "advertiser": l.advertiser, "email": "", "phone": "", "tags": [], "flags": [],
            }
        it = items[item_id]
        it.setdefault("category", l.category)
        # Ausschluss, der erst auf der Detailseite erkannt wurde, bleibt bestehen
        why = why or (it.get("key_excl") or {}).get(l.key)
        key_to_item[l.key] = item_id
        if l.key not in it["keys"]:
            it["keys"].append(l.key)
        if not any(x["source"] == name for x in it["links"]):
            it["links"].append({"source": name, "label": l.source_label or SOURCE_LABELS[name], "url": l.url})
        it["last_seen"] = run_at

        if not why and is_new_key and l.price <= ENRICH_MAX_PRICE and enrich_budget > 0 and not it.get("email"):
            enrich_budget -= 1
            try:
                SOURCES[name].enrich(l)
            except Exception:
                traceback.print_exc()
            why = exclusion_reason(l)
            if why:
                it.setdefault("key_excl", {})[l.key] = why

        if why:
            run_why.setdefault(item_id, why)
            excluded_counts[why] = excluded_counts.get(why, 0) + 1
        else:
            run_ok.add(item_id)

        # Felder ergänzen – bessere Werte gewinnen
        prev_total = it.get("price_total")
        if l.price_note == "Gesamtmiete" and it.get("price_note") != "Gesamtmiete":
            it["price"], it["price_note"], it["price_key"] = l.price, l.price_note, l.key
        elif it.get("price_key", it["keys"][0]) == l.key and l.price and abs(l.price - (it.get("price") or 0)) >= 1:
            it["price"] = l.price          # Preis hat sich im Inserat geändert
        for k in ("area", "rooms", "image", "address", "advertiser", "published", "wg_size", "eigenmittel"):
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
        if prev_total and it["price_total"] < prev_total - max(5, 0.03 * prev_total):
            it["price_drop"] = {"from": prev_total, "to": it["price_total"], "at": run_at}
            print(f"  Preis gesenkt: {prev_total} → {it['price_total']} € – {it['title'][:50]}")

    # Ausschluss pro Lauf neu bewerten: sobald eine Quelle das Inserat "sauber" liefert, gilt es
    for iid in run_ok | set(run_why):
        if iid in run_ok:
            if items[iid].get("excluded") == GONE:
                items[iid]["back_at"] = run_at   # war offline, ist wieder da
            items[iid].pop("excluded", None)
        else:
            items[iid]["excluded"] = run_why[iid]

    mark_gone(items, status, run_at)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=EXPIRE_DAYS)).isoformat()
    kept = [it for it in items.values() if it.get("last_seen", "") >= cutoff]
    for it in kept:
        it["score"] = score(it)
    kept.sort(key=lambda it: it["first_seen"], reverse=True)

    fingerprint = hashlib.sha1(json.dumps(sorted(
        (it["id"], it.get("price_total"), it.get("excluded"), it.get("email"), len(it.get("links", [])))
        for it in kept), ensure_ascii=False).encode()).hexdigest()[:16]
    saved_at = data.get("updated")
    changed = fingerprint != data.get("fingerprint")
    if not changed and saved_at and _hours_since(saved_at) * 60 < SAVE_EVERY_MIN and os.path.exists(DATA_FILE):
        print(f"\n= Keine inhaltliche Änderung – nicht gespeichert (zuletzt vor {round(_hours_since(saved_at) * 60)} Min.)")
        return

    out = {
        "updated": run_at,
        "fingerprint": fingerprint,
        "sources": status,
        "excluded": excluded_counts,
        "last_push": data.get("last_push") or data.get("last_digest"),
        "last_problem_push": data.get("last_problem_push"),
        "items": kept,
    }
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    open(SAVED_MARKER, "w").close()

    # gezählt wird, was die App mit Standard-Einstellungen zeigt (ohne Bezahlportale, Zwischenmieten usw.)
    flats = [it for it in kept if it["category"] == "wohnung" and matches_default(it)]
    wgs = [it for it in kept if it["category"] == "wg" and matches_default(it)]
    print(f"\n✓ {len(kept)} gespeichert: {len(flats)} passende Wohnungen ≤ {FLAT_MAX_PRICE} €, {len(wgs)} passende WG-Zimmer "
          f"(ohne Bezahlportale/Zwischenmieten). "
          f"Aussortiert: {excluded_counts}")


if __name__ == "__main__":
    main()
