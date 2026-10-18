# Wohnungsfinder Wien

Durchsucht alle 5 Minuten (6–23 Uhr, schwere Quellen seltener) Mietwohnungen und WG-Zimmer in Wien 4.–7. Bezirk
(Wieden, Margareten, Mariahilf, Neubau) auf willhaben, DER STANDARD, ImmoScout24, immowelt,
WG-Gesucht und IMMMO (inkl. Kurier Immo, Bazar, Wohnkrone), dazu direkt auf Makler-Websites
(Brezina, TICON, ARWAG, Siedlungsunion) und bei Genossenschaften über GEWOFinder
(Sozialbau, GESIBA, Wien-Süd, ÖSW, ÖVW, BWSG, EBG, Familienwohnbau, Frieden, Neues Leben, Heimat Österreich, WBV-GPA, GEWOG) und zeigt die besten Treffer in einer
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

## Weitere Makler ergänzen

Makler mit justimmo-Website (Links wie `/objekt/12345`) lassen sich in `scraper/sources/makler.py`
mit einer Zeile in `JUSTIMMO` hinzufügen: Name + URL der Mietwohnungs-Liste.

## Zuverlässiger Zeitplan (cron-job.org)

GitHub führt geplante Läufe (`schedule`) oft stark verzögert oder gar nicht aus. Deshalb stößt
cron-job.org die Suche alle 30 Minuten über die GitHub-Schnittstelle an:

- URL: `https://api.github.com/repos/andihaider/wien-wohnungsfinder/actions/workflows/suche.yml/dispatches`
- Methode: `POST`, Body: `{"ref":"main"}`
- Header: `Authorization: Bearer <Fine-grained Token>`, `Accept: application/vnd.github+json`,
  `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`
- Token: Fine-grained, nur dieses Repo, Berechtigung *Actions: Read and write*
- Antwort bei Erfolg: `204 No Content`

Der GitHub-eigene Zeitplan bleibt als Reserve aktiv.
