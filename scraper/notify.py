"""E-Mail mit neuen Treffern – höchstens 2× täglich (07:00 und 18:00 Wiener Zeit), nur wenn es Neues gibt.

Einstellungen kommen aus Umgebungsvariablen (GitHub Secrets), nie aus dem Repo:
  NTFY_TOPIC     geheimes Thema für Push-Nachrichten über die ntfy-App (kostenlos, ohne Konto)
  MAIL_USER / MAIL_PASSWORD / MAIL_TO  optional: zusätzlich HTML-Mail über ein eigenes Gmail-Konto
  MAIL_HOST / MAIL_PORT      optional, Standard smtp.gmail.com:465

  python scraper/notify.py            # sendet nur im Zeitfenster
  python scraper/notify.py --preview  # schreibt mail-preview.html, sendet nichts
  python scraper/notify.py --force    # sendet sofort (Test)
"""
import html
import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from scoring import matches_default  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "docs", "data", "listings.json")
APP_URL = "https://andihaider.github.io/wien-wohnungsfinder/"
VIENNA = ZoneInfo("Europe/Vienna")
SLOTS = (7, 18)            # Uhrzeiten (Wien), zu denen gesammelt verschickt wird
SLOT_WINDOW_H = 3          # so lange nach dem Zeitpunkt darf noch nachgeholt werden
SOURCE_NAMES = {
    "willhaben": "willhaben", "derstandard": "DER STANDARD", "immoscout24": "ImmoScout24",
    "immowelt": "immowelt", "wggesucht": "WG-Gesucht", "immmo": "IMMMO",
}


def parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def current_slot(now):
    """Letzter fälliger Versandzeitpunkt, falls wir gerade im Zeitfenster sind."""
    local = now.astimezone(VIENNA)
    candidates = []
    for day in (local.date() - timedelta(days=1), local.date()):
        for h in SLOTS:
            candidates.append(datetime(day.year, day.month, day.day, h, tzinfo=VIENNA))
    past = [c for c in candidates if c <= local]
    slot = max(past)
    return slot if local - slot <= timedelta(hours=SLOT_WINDOW_H) else None


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
            out.append(f"{SOURCE_NAMES.get(k, k)} liefert seit {v['empty_streak']} Läufen keine Inserate – evtl. hat sich die Seite geändert.")
    return out


def eur(n):
    return "€ " + f"{round(n):,}".replace(",", ".")


def card_html(it):
    e = html.escape
    wg = it.get("category") == "wg"
    facts = ([f"{it['area']:g} m² Zimmer" if it.get("area") else "", f"{it['wg_size']}er WG" if it.get("wg_size") else ""]
             if wg else
             [f"{it['area']:g} m²" if it.get("area") else "", f"{it['rooms']:g} Zi." if it.get("rooms") else "",
              f"€ {it['ppsqm']:.1f}/m²".replace(".", ",") if it.get("ppsqm") else ""])
    facts = " · ".join(f for f in facts if f)
    note = "ca. gesamt" if it.get("price_estimated") else (it.get("price_note") or "")
    flags = " ".join(
        f'<span style="display:inline-block;font-size:12px;padding:2px 8px;margin:2px 2px 0 0;border-radius:99px;background:#d8efec;color:#0f766e">{e(f)}</span>'
        for f in (it.get("flags") or [])[:6])
    img = (f'<img src="{e(it["image"])}" alt="" width="560" style="width:100%;max-width:560px;height:auto;border-radius:12px 12px 0 0;display:block">'
           if it.get("image") else "")
    link = it["links"][0]["url"]
    contact = (f' &nbsp;·&nbsp; <a href="mailto:{e(it["email"])}" style="color:#0f766e">{e(it["email"])}</a>' if it.get("email") else "")
    return f"""
<div style="border:1px solid #e2e4df;border-radius:12px;margin:0 0 16px;background:#fff">
  {img}
  <div style="padding:12px 14px 14px">
    <div style="font-size:22px;font-weight:700">{eur(it['price_total'])} <span style="font-size:12px;font-weight:400;color:#69706b">{e(note)}</span>
      <span style="float:right;font-size:13px;font-weight:600;color:#fff;background:#0f766e;border-radius:99px;padding:2px 9px">{it.get('score', 0)} Punkte</span></div>
    <div style="color:#69706b;font-size:13px;margin-top:2px">{e(facts)}</div>
    <div style="font-size:15px;font-weight:600;margin:6px 0 2px">{e(it['title'])}</div>
    <div style="color:#69706b;font-size:13px">{e(it.get('district') or '')} {e(it['zip'])} · {e(it['links'][0]['label'])}</div>
    <div style="margin-top:6px">{flags}</div>
    <div style="margin-top:12px"><a href="{e(link)}" style="display:inline-block;background:#0f766e;color:#fff;text-decoration:none;font-weight:600;padding:9px 14px;border-radius:10px">Zum Inserat</a>{contact}</div>
  </div>
</div>"""


def build_mail(flats, wgs, probs):
    n = len(flats) + len(wgs)
    parts = []
    if flats:
        parts.append(f'<h2 style="font-size:17px;margin:18px 0 10px">🏠 Wohnungen ({len(flats)})</h2>' + "".join(card_html(i) for i in flats))
    if wgs:
        parts.append(f'<h2 style="font-size:17px;margin:18px 0 10px">👥 WG-Zimmer ({len(wgs)})</h2>' + "".join(card_html(i) for i in wgs))
    warn = ""
    if probs:
        warn = ('<div style="background:#fbeed7;color:#9a5b00;border-radius:10px;padding:10px 12px;font-size:13px;margin:12px 0">⚠︎ '
                + " ".join(html.escape(p) for p in probs) + "</div>")
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;background:#f4f5f2;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1c1f1d">
<div style="max-width:600px;margin:0 auto;padding:16px">
  <div style="font-size:20px;font-weight:700">Wohnungsfinder <span style="color:#0f766e">Wien</span></div>
  <div style="color:#69706b;font-size:13px">{n} neue Treffer seit der letzten Mail · 4.–7. Bezirk</div>
  {warn}
  {''.join(parts)}
  <p style="text-align:center;margin:20px 0"><a href="{APP_URL}" style="color:#0f766e;font-weight:600">Alle Treffer in der App ansehen →</a></p>
  <p style="color:#69706b;font-size:12px;text-align:center">Kriterien: Wohnungen bis 650 € gesamt, WG-Zimmer bis 600 € ab 15 m², ohne Gemeindebau.</p>
</div></body></html>"""
    if flats:
        top = max(flats, key=lambda i: i.get("score", 0))
        subj = f"🏠 {n} neue Treffer – z. B. {eur(top['price_total'])}, {(top.get('area') or 0):g} m², {top.get('district', '')}"
    elif wgs:
        top = max(wgs, key=lambda i: i.get("score", 0))
        subj = f"👥 {n} neue WG-Zimmer – z. B. {eur(top['price_total'])}, {(top.get('area') or 0):g} m², {top.get('district', '')}"
    else:
        subj = "⚠︎ Wohnungsfinder: eine Quelle funktioniert nicht"
    return subj, body


def text_mail(flats, wgs, probs):
    """Kompakte Text-Version (ntfy.sh erlaubt max. ~4 KB pro Nachricht)."""
    def line(it):
        wg = it.get("category") == "wg"
        area = f"{(it.get('area') or 0):g} m²".replace(".", ",") + (" Zimmer" if wg else "") if it.get("area") else ""
        extra = f"{it['wg_size']}er WG" if wg and it.get("wg_size") else ""
        facts = " · ".join(x for x in [eur(it["price_total"]) + (" ca." if it.get("price_estimated") else ""), area, extra,
                                        (it.get("district") or it["zip"])] if x)
        return f"• {facts}\n  {it['title'][:70]}\n  {it['links'][0]['url']}"
    parts = []
    if probs:
        parts.append("⚠ " + " ".join(probs))
    if flats:
        parts.append(f"🏠 WOHNUNGEN ({len(flats)})\n" + "\n".join(line(i) for i in flats[:8]))
    if wgs:
        parts.append(f"👥 WG-ZIMMER ({len(wgs)})\n" + "\n".join(line(i) for i in wgs[:8]))
    parts.append("Alle Treffer in der App: " + APP_URL)
    text = "\n\n".join(parts)
    return text[:3900]


def send_push(topic, subject, text, top_url=""):
    """Push aufs Handy über die ntfy-App (kostenlos, ohne Konto). Das Thema ist geheim (GitHub-Secret)."""
    actions = [{"action": "view", "label": "App öffnen", "url": APP_URL, "clear": True}]
    if top_url:
        actions.insert(0, {"action": "view", "label": "Bester Treffer", "url": top_url})
    payload = {"topic": topic, "title": subject, "message": text, "click": APP_URL,
               "tags": ["house"], "actions": actions}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"  📲 Push verschickt (HTTP {r.status}): {subject}")
    return True


def send(subject, body, text="", top_url=""):
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        send_push(topic, subject, text, top_url)
    user, pw = os.environ.get("MAIL_USER"), os.environ.get("MAIL_PASSWORD")
    to = os.environ.get("MAIL_TO") or user
    if not (user and pw):
        if not topic:
            print("  (weder NTFY_TOPIC noch Mail-Zugang gesetzt – keine Benachrichtigung)")
        return bool(topic)
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, f"Wohnungsfinder <{user}>", to
    msg.attach(MIMEText("Neue Treffer: " + APP_URL, "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))
    host, port = os.environ.get("MAIL_HOST", "smtp.gmail.com"), int(os.environ.get("MAIL_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"  ✉︎ Mail gesendet an {to.split('@')[0][:2]}…: {subject}")
    return True


def main():
    preview, force = "--preview" in sys.argv, "--force" in sys.argv
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    slot = current_slot(now)
    last = parse(data.get("last_digest"))
    if not (preview or force):
        if not slot:
            print("Mail: nicht im Versandfenster (07:00/18:00).")
            return
        if last and last >= slot:
            print("Mail: für dieses Zeitfenster schon erledigt.")
            return

    since = last or (now - timedelta(hours=12))
    fresh = [it for it in data["items"] if parse(it["first_seen"]) > since and matches_default(it)]
    flats = sorted([i for i in fresh if i.get("category") != "wg"], key=lambda i: -i.get("score", 0))
    wgs = sorted([i for i in fresh if i.get("category") == "wg"], key=lambda i: -i.get("score", 0))
    # Warnungen nur morgens mitschicken (max. 1× am Tag), damit keine Warn-Flut entsteht
    probs = problems(data) if (force or preview or (slot and slot.hour == SLOTS[0])) else []
    print(f"Mail: {len(flats)} Wohnungen, {len(wgs)} WG-Zimmer neu seit {since.isoformat(timespec='minutes')}; Warnungen: {len(probs)}")

    if preview:
        subject, body = build_mail(flats, wgs, probs)
        out = os.path.join(ROOT, "mail-preview.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"  Vorschau: {out}\n  Betreff: {subject}\n--- Text-Version ({len(text_mail(flats, wgs, probs).encode())} Bytes) ---\n{text_mail(flats, wgs, probs)}")
        return

    if force and not (flats or wgs):
        # Testmodus: aktuelle Top-Treffer schicken, damit man sieht, wie die Nachricht aussieht
        current = sorted([i for i in data["items"] if matches_default(i)], key=lambda i: -i.get("score", 0))
        flats = [i for i in current if i.get("category") != "wg"][:3]
        wgs = [i for i in current if i.get("category") == "wg"][:3]
    if flats or wgs or probs:
        subject, body = build_mail(flats, wgs, probs)
        if force:
            subject = "TEST – " + subject
        try:
            best = max(flats or wgs, key=lambda i: i.get("score", 0)) if (flats or wgs) else None
            send(subject, body, text_mail(flats, wgs, probs), best["links"][0]["url"] if best else "")
        except Exception as e:  # Mail-Probleme dürfen die Suche nie blockieren
            detail = e.read()[:300].decode(errors="replace") if hasattr(e, "read") else ""
            print(f"  ! Mail fehlgeschlagen: {type(e).__name__}: {e} {detail}")
    else:
        print("  nichts Neues – keine Mail.")
    if force:
        return  # Test zählt nicht als Zusammenfassung
    data["last_digest"] = now.replace(microsecond=0).isoformat()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
