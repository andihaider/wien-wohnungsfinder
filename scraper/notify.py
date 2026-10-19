"""Push-Nachricht über die ntfy-App, sobald ein neuer passender Treffer auftaucht.

Läuft nach jeder Suche (alle 30 Min.). Das Thema kommt aus dem GitHub-Secret NTFY_TOPIC, nie aus dem Repo.

  python scraper/notify.py            # pusht neue Treffer seit dem letzten Push
  python scraper/notify.py --preview  # zeigt die Nachricht nur an
  python scraper/notify.py --force    # Test: pusht die aktuellen Top-Treffer
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from scoring import matches_default  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "docs", "data", "listings.json")
APP_URL = "https://andihaider.github.io/wien-wohnungsfinder/"
PROBLEM_PUSH_EVERY_H = 24   # Warnungen über kaputte Quellen höchstens 1× am Tag
MAX_GAP_MIN = 20            # tagsüber mehr Pause zwischen zwei Suchläufen → Alarm-Push
SOURCE_NAMES = {
    "willhaben": "willhaben", "derstandard": "DER STANDARD", "immoscout24": "ImmoScout24",
    "immowelt": "immowelt", "wggesucht": "WG-Gesucht", "immmo": "IMMMO",
}


def parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def problems(data):
    out = []
    for k, v in (data.get("sources") or {}).items():
        if v.get("via"):
            continue
        if k == "wggesucht":
            last = parse(v.get("last_ok"))
            if not last or datetime.now(timezone.utc) - last > timedelta(hours=24):
                out.append("WG-Gesucht liefert seit über 24 Std. nichts (Captcha-Prüfung).")
        elif v.get("empty_streak", 0) >= 2:
            out.append(f"{SOURCE_NAMES.get(k, k)} liefert seit {v['empty_streak']} Läufen keine Inserate.")
    return out


def search_gap_minutes():
    """Minuten seit dem letzten erfolgreichen Suchlauf vor diesem (über die GitHub-Schnittstelle).

    Gibt None zurück, wenn das nicht prüfbar ist oder die Pause die normale Nachtruhe (23–6 Uhr) war.
    """
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return None
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/workflows/suche.yml/runs?status=success&per_page=1",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        runs = json.load(urllib.request.urlopen(req, timeout=20)).get("workflow_runs") or []
    except Exception as e:
        print(f"  (Pausen-Check nicht möglich: {type(e).__name__})")
        return None
    if not runs:
        return None
    prev = parse(runs[0]["updated_at"])
    now = datetime.now(timezone.utc)
    vienna = ZoneInfo("Europe/Vienna")
    if prev.astimezone(vienna).hour >= 22 or now.astimezone(vienna).hour < 7:
        return None   # Nachtpause bzw. erster Lauf am Morgen
    return (now - prev).total_seconds() / 60


def eur(n):
    return "€ " + f"{round(n):,}".replace(",", ".")


def facts(it):
    wg = it.get("category") == "wg"
    area = (f"{it['area']:g} m²".replace(".", ",") + (" Zimmer" if wg else "")) if it.get("area") else ""
    extra = f"{it['wg_size']}er WG" if wg and it.get("wg_size") else ""
    price = eur(it["price_total"]) + (" ca." if it.get("price_estimated") else "")
    return " · ".join(x for x in [price, area, extra, it.get("district") or it["zip"]] if x)


def build(flats, wgs, probs):
    """Titel, Text, Klick-Ziel und Treffer der Push-Nachricht."""
    items = sorted(flats + wgs, key=lambda i: -i.get("score", 0))
    if len(items) == 1:
        it = items[0]
        kind = "WG-Zimmer" if it.get("category") == "wg" else "Wohnung"
        title = f"Neue {kind}: {facts(it)}"
        text = f"{it['title'][:120]}\n{it['links'][0]['label']} · {it.get('score', 0)} Punkte"
        return title, text, it["links"][0]["url"], items
    if items:
        n_f, n_w = len(flats), len(wgs)
        what = " + ".join(x for x in [f"{n_f} Wohnung{'en' if n_f > 1 else ''}" if n_f else "",
                                      f"{n_w} WG-Zimmer" if n_w else ""] if x)
        title = f"{what} neu – z. B. {facts(items[0])}"
        lines = [f"• {facts(i)}\n  {i['title'][:70]}\n  {i['links'][0]['url']}" for i in items[:8]]
        if len(items) > 8:
            lines.append(f"… und {len(items) - 8} weitere in der App")
        return title, "\n".join(lines)[:3800], APP_URL, items
    return "⚠︎ Wohnungsfinder: eine Quelle funktioniert nicht", " ".join(probs), APP_URL, []


def push(topic, title, text, click, items):
    actions = [{"action": "view", "label": "App öffnen", "url": APP_URL, "clear": True}]
    if items:
        actions.insert(0, {"action": "view", "label": "Zum Inserat", "url": items[0]["links"][0]["url"]})
    best = max((i.get("score", 0) for i in items), default=0)
    payload = {"topic": topic, "title": title, "message": text, "click": click, "tags": ["house"],
               "actions": actions, "priority": 4 if best >= 50 else 3}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"  📲 Push verschickt (HTTP {r.status}): {title}")


def main():
    preview, force = "--preview" in sys.argv, "--force" in sys.argv
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    # Übergang vom alten 2×-täglich-Versand; beim allerersten Mal nicht alles auf einmal pushen
    since = parse(data.get("last_push")) or parse(data.get("last_digest")) or now

    fresh = [it for it in data["items"] if parse(it["first_seen"]) > since and matches_default(it)]
    if force and not fresh:
        # Test: aktuelle Top-Treffer schicken, damit man sieht, wie die Nachricht aussieht
        fresh = sorted([i for i in data["items"] if matches_default(i)], key=lambda i: -i.get("score", 0))[:4]
    flats = [i for i in fresh if i.get("category") != "wg"]
    wgs = [i for i in fresh if i.get("category") == "wg"]

    last_prob = parse(data.get("last_problem_push"))
    probs = problems(data) if (force or not last_prob or now - last_prob > timedelta(hours=PROBLEM_PUSH_EVERY_H)) else []
    print(f"Push: {len(flats)} Wohnungen, {len(wgs)} WG-Zimmer neu seit {since.isoformat(timespec='minutes')}; "
          f"Warnungen: {len(probs)}")

    messages = []
    gap = None if (preview or force) else search_gap_minutes()
    if gap and gap > MAX_GAP_MIN:
        print(f"  ! Pause zwischen zwei Suchläufen: {gap:.0f} Min.")
        messages.append((f"⚠︎ Wohnungssuche hatte {gap:.0f} Min. Pause",
                         "Zwischen zwei Suchläufen lagen mehr als 20 Minuten. Die Suche läuft jetzt wieder – "
                         "falls das öfter passiert, cron-job.org und GitHub Actions prüfen.", APP_URL, []))
    if flats or wgs:
        messages.append(build(flats, wgs, []))
    if probs:
        messages.append(build([], [], probs))
        if not (force or preview):
            data["last_problem_push"] = now.replace(microsecond=0).isoformat()

    topic = os.environ.get("NTFY_TOPIC")
    sent = False
    for title, text, click, items in messages:
        if force:
            title = "TEST – " + title
        if preview:
            print(f"--- {title}\n{text}\n(Klick → {click})")
            continue
        if not topic:
            print("  (NTFY_TOPIC nicht gesetzt – keine Push-Nachricht)")
            break
        try:
            push(topic, title, text, click, items)
            sent = True
        except Exception as e:  # Push-Probleme dürfen die Suche nie blockieren
            print(f"  ! Push fehlgeschlagen: {type(e).__name__}: {e}")

    if preview or force:
        return  # Test/Vorschau zählt nicht als Push
    if not sent and not os.path.exists(os.path.join(ROOT, ".saved-this-run")):
        return  # Suche hat diesmal nichts gespeichert (keine Änderung) – dann auch hier nichts schreiben
    data["last_push"] = now.replace(microsecond=0).isoformat()
    data.pop("last_digest", None)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
