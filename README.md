# Wohnungsfinder Wien

Durchsucht alle 30 Minuten (6–23 Uhr) Mietwohnungen und WG-Zimmer in Wien 4.–7. Bezirk
(Wieden, Margareten, Mariahilf, Neubau) auf willhaben, DER STANDARD, ImmoScout24, immowelt,
WG-Gesucht und IMMMO (inkl. Kurier Immo, Bazar, Wohnkrone) und zeigt die besten Treffer in einer
Handy-Web-App. Um 7 und 18 Uhr kommt eine E-Mail mit den neuen Treffern (nur wenn es welche gibt).

## E-Mail einrichten

Es reicht ein GitHub-Secret `MAIL_TO` mit der Empfängeradresse (*Settings → Secrets and variables → Actions*).
Verschickt wird dann kostenlos und ohne Konto über ntfy.sh als Text-Mail.
Optional für HTML-Mails mit Fotos: zusätzlich `MAIL_USER` + `MAIL_PASSWORD` (Gmail-App-Passwort).

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
