# Wohnungsfinder Wien

Durchsucht alle 30 Minuten (6–23 Uhr) Mietwohnungen und WG-Zimmer in Wien 4.–7. Bezirk
(Wieden, Margareten, Mariahilf, Neubau) auf willhaben, DER STANDARD, ImmoScout24, immowelt,
WG-Gesucht und IMMMO (inkl. Kurier Immo, Bazar, Wohnkrone) und zeigt die besten Treffer in einer
Handy-Web-App. Jeder neue passende Treffer kommt sofort als Push-Nachricht aufs Handy.

## Benachrichtigungen

Neue passende Treffer kommen sofort nach der Suche als Push über die kostenlose **ntfy**-App (iOS/Android).
Das Thema ist geheim und liegt im GitHub-Secret `NTFY_TOPIC`; in der ntfy-App einfach dieses Thema abonnieren.

Test: `python scraper/notify.py --preview` zeigt die Nachricht an, `--force` pusht sofort die aktuellen Top-Treffer.

- **App:** `docs/` (wird über GitHub Pages ausgeliefert)
- **Suche:** `scraper/run.py`, läuft über `.github/workflows/suche.yml`
- **Daten:** `docs/data/listings.json`

Lokal ausführen:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scraper/run.py
python3 -m http.server 5190 --directory docs
```
