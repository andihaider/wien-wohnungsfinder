# Wohnungsfinder Wien

Durchsucht 2× täglich Mietwohnungen in Wien 4.–7. Bezirk (Wieden, Margareten, Mariahilf, Neubau)
auf willhaben, DER STANDARD, ImmoScout24, immowelt und IMMMO (inkl. Kurier Immo, Bazar, Wohnkrone)
und zeigt die besten Treffer in einer Handy-Web-App.

- **App:** `docs/` (wird über GitHub Pages ausgeliefert)
- **Suche:** `scraper/run.py`, läuft über `.github/workflows/suche.yml`
- **Daten:** `docs/data/listings.json`

Lokal ausführen:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scraper/run.py
python3 -m http.server 5190 --directory docs
```
