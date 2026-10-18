# Wohnungsfinder Wien

Durchsucht alle 30 Minuten (6–23 Uhr) Mietwohnungen und WG-Zimmer in Wien 4.–7. Bezirk
(Wieden, Margareten, Mariahilf, Neubau) auf willhaben, DER STANDARD, ImmoScout24, immowelt,
WG-Gesucht und IMMMO (inkl. Kurier Immo, Bazar, Wohnkrone) und zeigt die besten Treffer in einer
Handy-Web-App. Um 7 und 18 Uhr kommt eine E-Mail mit den neuen Treffern (nur wenn es welche gibt).

## Benachrichtigungen

Um 7 und 18 Uhr kommt eine Push-Nachricht über die kostenlose **ntfy**-App (iOS/Android), nur wenn es Neues gibt.
Das Thema ist geheim und liegt im GitHub-Secret `NTFY_TOPIC`; in der ntfy-App einfach dieses Thema abonnieren.
Optional zusätzlich HTML-Mail: Secrets `MAIL_USER`, `MAIL_PASSWORD` (Gmail-App-Passwort), `MAIL_TO`.

Test: `python scraper/notify.py --preview` erzeugt eine Vorschau, `--force` sendet sofort.

- **App:** `docs/` (wird über GitHub Pages ausgeliefert)
- **Suche:** `scraper/run.py`, läuft über `.github/workflows/suche.yml`
- **Daten:** `docs/data/listings.json`

Lokal ausführen:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scraper/run.py
python3 -m http.server 5190 --directory docs
```
