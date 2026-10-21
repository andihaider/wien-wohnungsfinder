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
VIENNA = ZoneInfo("Europe/Vienna")
QUIET_FROM, QUIET_UNTIL = (23, 0), (6, 0)    # Nachtruhe: keine Suche, keine Pushes; um 6:00 wird alles nachgeholt


def in_quiet_hours(now):
    t = now.astimezone(VIENNA)
    minutes = t.hour * 60 + t.minute
    return minutes >= QUIET_FROM[0] * 60 + QUIET_FROM[1] or minutes < QUIET_UNTIL[0] * 60 + QUIET_UNTIL[1]


def is_morning_catchup(now, since):
    """Erster Versand nach der Nachtruhe: der letzte Push war vor heute 6:00."""
    t = now.astimezone(VIENNA)
    wake = t.replace(hour=QUIET_UNTIL[0], minute=QUIET_UNTIL[1], second=0, microsecond=0)
    return since.astimezone(VIENNA) < wake <= t
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


MAX_SINGLE = 10             # bis zu so vielen Einzel-Pushes pro Lauf, der Rest kommt gesammelt
SHOW_FLAGS = ("provisionsfrei", "unbefristet", "Balkon", "Terrasse", "Loggia", "Garten", "Altbau", "Lift",
              "befristet", "Ablöse", "möbliert", "Genossenschaft")


def level(score):
    """Priorität, Emoji und ntfy-Tag nach Punktzahl. 5 = höchste Stufe (lautester Ton, kann "Nicht stören" durchbrechen)."""
    if score >= 60:      # etwa die besten 20 %
        return 5, "🔥", "fire"
    if score >= 40:
        return 4, "✨", "sparkles"
    return 3, "🏠", "house"


def listing_msg(it, kind="new"):
    """Eine Push-Nachricht für genau eine Wohnung (neu / Preis gesenkt / wieder online)."""
    sc = it.get("score", 0)
    prio, emoji, tag = level(sc)
    label = "WG-Zimmer" if it.get("category") == "wg" else "Wohnung"
    if kind == "drop":
        d = it["price_drop"]
        head = f"💸 Preis gesenkt {eur(d['from'])} → {eur(d['to'])}"
    elif kind == "back":
        head = f"🔁 Wieder online ({label})"
    else:
        head = f"{emoji} " + ("Neues WG-Zimmer" if label == "WG-Zimmer" else "Neue Wohnung")
    flags = [f for f in it.get("flags") or [] if f in SHOW_FLAGS]
    lines = [it["title"][:140]]
    if flags:
        lines.append(" · ".join(flags))
    if it.get("eigenmittel"):
        lines.append(f"+ {eur(it['eigenmittel'])} Eigenmittel (einmalig)")
    lines.append(f"{sc} Punkte · {it['links'][0]['label']}" + (f" · {it['advertiser'][:40]}" if it.get("advertiser") else ""))
    url = it["links"][0]["url"]
    return {
        "title": f"{head}: {facts(it)}",
        "message": "\n".join(lines),
        "click": url,
        "priority": prio,
        "tags": [tag],
        "actions": [
            {"action": "view", "label": "Jetzt anfragen", "url": f"{APP_URL}#anfrage={it['id']}", "clear": True},
            {"action": "view", "label": "Inserat öffnen", "url": url},
        ],
    }


def batch_msg(items):
    """Sammel-Nachricht für alles, was über MAX_SINGLE hinausgeht."""
    lines = [f"• {facts(i)} ({i.get('score', 0)} Pkt)\n  {i['links'][0]['url']}" for i in items[:12]]
    if len(items) > 12:
        lines.append(f"… und {len(items) - 12} weitere in der App")
    return {"title": f"🏠 {len(items)} weitere Treffer", "message": "\n".join(lines)[:3800], "click": APP_URL,
            "priority": 3, "tags": ["house"], "actions": [{"action": "view", "label": "App öffnen", "url": APP_URL}]}


def info_msg(title, text):
    return {"title": title, "message": text, "click": APP_URL, "priority": 4, "tags": ["warning"],
            "actions": [{"action": "view", "label": "App öffnen", "url": APP_URL}]}


def push(topic, msg):
    payload = dict(msg, topic=topic)
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"  📲 Push (Prio {msg.get('priority')}, HTTP {r.status}): {msg['title']}")


def main():
    preview, force = "--preview" in sys.argv, "--force" in sys.argv
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    # Übergang vom alten 2×-täglich-Versand; beim allerersten Mal nicht alles auf einmal pushen
    since = parse(data.get("last_push")) or parse(data.get("last_digest")) or now

    after = lambda iso: bool(iso) and parse(iso) > since
    fresh = [it for it in data["items"] if after(it["first_seen"]) and matches_default(it)]
    new_ids = {it["id"] for it in fresh}
    drops = [it for it in data["items"] if it["id"] not in new_ids and matches_default(it)
             and after((it.get("price_drop") or {}).get("at"))]
    back = [it for it in data["items"] if it["id"] not in new_ids and matches_default(it) and after(it.get("back_at"))]
    if force and not fresh:
        # Test: aktuelle Top-Treffer schicken, damit man sieht, wie die Nachrichten aussehen
        fresh = sorted([i for i in data["items"] if matches_default(i)], key=lambda i: -i.get("score", 0))[:3]

    last_prob = parse(data.get("last_problem_push"))
    probs = problems(data) if (force or not last_prob or now - last_prob > timedelta(hours=PROBLEM_PUSH_EVERY_H)) else []
    print(f"Push: {len(fresh)} neu, {len(drops)} Preis gesenkt, {len(back)} wieder online seit "
          f"{since.isoformat(timespec='minutes')}; Warnungen: {len(probs)}")

    events = sorted([(it, "new") for it in fresh] + [(it, "drop") for it in drops] + [(it, "back") for it in back],
                    key=lambda e: -e[0].get("score", 0))
    if in_quiet_hours(now) and not (preview or force):
        # Nachts nichts schicken und last_push NICHT weiterschieben → alles wird um 6:00 nachgeholt
        print(f"  Nachtruhe bis 6:00: {len(events)} Treffer gesammelt, werden morgens geschickt")
        return
    morning = is_morning_catchup(now, since) and not (preview or force)

    messages = []
    gap = None if (preview or force) else search_gap_minutes()
    if gap and gap > MAX_GAP_MIN:
        print(f"  ! Pause zwischen zwei Suchläufen: {gap:.0f} Min.")
        messages.append(info_msg(f"⚠︎ Wohnungssuche hatte {gap:.0f} Min. Pause",
                                 "Zwischen zwei Suchläufen lagen mehr als 20 Minuten. Die Suche läuft jetzt wieder – "
                                 "falls das öfter passiert, cron-job.org und GitHub Actions prüfen."))
    if morning and events:
        print(f"  Morgen-Nachlieferung: {len(events)} Treffer aus der Nacht")
    # Sammel-Nachricht zuerst, dann die schwächeren, die beste zuletzt –
    # so liegt die wichtigste Nachricht oben in der Mitteilungsliste
    listing_msgs = []
    if len(events) > MAX_SINGLE:
        listing_msgs.append(batch_msg([it for it, _ in events[MAX_SINGLE:]]))
    for it, kind in reversed(events[:MAX_SINGLE]):
        m = listing_msg(it, kind)
        if morning:
            m["title"] = "🌅 Über Nacht – " + m["title"]
        listing_msgs.append(m)
    messages += listing_msgs
    if probs:
        messages.append(info_msg("⚠︎ Wohnungsfinder: eine Quelle funktioniert nicht", " ".join(probs)))
        if not (force or preview):
            data["last_problem_push"] = now.replace(microsecond=0).isoformat()

    topic = os.environ.get("NTFY_TOPIC")
    sent = False
    for msg in messages:
        if force:
            msg["title"] = "TEST – " + msg["title"]
        if preview:
            print(f"--- [Prio {msg['priority']}] {msg['title']}\n{msg['message']}\n(Klick → {msg['click']}; "
                  f"Buttons: {[x['label'] for x in msg['actions']]})")
            continue
        if not topic:
            print("  (NTFY_TOPIC nicht gesetzt – keine Push-Nachricht)")
            break
        try:
            push(topic, msg)
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
