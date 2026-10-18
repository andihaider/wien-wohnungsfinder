"""IMMMO: Meta-Suche über viele Portale und Makler-Websites (auch Basis von Kurier Immo, Bazar, Wohnkrone)."""
import hashlib
import re

from bs4 import BeautifulSoup

from common import COLLECT_MAX_PRICE, Listing, get, parse_number, zip_from_text

BASE = "https://www.immmo.at/immo/Wohnung-mieten/Wien"
SLUGS = {"1040": "Wien-4-Wieden", "1050": "Wien-5-Margareten", "1060": "Wien-6-Mariahilf", "1070": "Wien-7-Neubau"}

# Diese Portale scrapen wir schon direkt – von IMMMO nehmen wir nur die anderen Anbieter.
SKIP_HOSTS = ("willhaben.at", "immobilienscout24.at", "immowelt.at", "derstandard.at")


# Ob der letzte Abruf alle Inserate erfasst hat (dann heißt "fehlt in der Suche" = offline)
STATE = {"complete": True}


def fetch():
    STATE["complete"] = True
    out = []
    for zip_, slug in SLUGS.items():
        for page in range(1, 13):
            r = get(f"{BASE}/{slug}" + (f"/{page}" if page > 1 else ""))
            if not r:
                STATE["complete"] = False
                break
            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select("li.wrapper-result")
            for li in items:
                host = li.get("data-hostname") or ""
                a = li.select_one("p.result-link a")
                if not a:
                    continue
                href = a["href"]
                price = parse_number((li.select_one("p.price") or {}).get_text() if li.select_one("p.price") else None)
                if host.endswith(SKIP_HOSTS) or price is None or price > COLLECT_MAX_PRICE:
                    continue
                details = li.select_one("p.result-details")
                dtext = details.get_text(" ", strip=True) if details else ""
                parts = [p.strip() for p in dtext.split("/")]
                area = next((parse_number(p) for p in parts if "m²" in p), None)
                rooms = next((parse_number(p) for p in parts if "Zimmer" in p), None)
                img = li.select_one("img")
                desc_el = li.select_one(".wrapper-result-description-text")
                desc = desc_el.get_text(" ", strip=True) if desc_el else ""
                tags = [t.get_text(strip=True).lstrip("#") for t in li.select("p.result-tags span > span")]
                tags = [t.get_text(" ", strip=True).replace("#", "").strip() for t in li.select("p.result-tags > span")] or tags
                h3 = li.select_one("h3")
                uid = li.get("data-realestateuid") or hashlib.md5(href.encode()).hexdigest()[:12]
                out.append(Listing(
                    source="immmo",
                    source_id=uid,
                    url=href,
                    title=a.get_text(" ", strip=True),
                    price=price,
                    price_note="",
                    zip=zip_from_text(dtext) or zip_,
                    area=area,
                    rooms=rooms,
                    address=dtext.split("/")[0].strip(),
                    image=(img.get("data-src") or img.get("src") or "") if img else "",
                    description=re.sub(r"\s*\[Mehr\]\s*$", "", desc),
                    published="",
                    advertiser=host.replace("www.", ""),
                    private=("Privat" in (h3.get_text() if h3 else "")),
                    tags=[t for t in tags if t] + (["provisionsfrei"] if li.select_one(".free-of-commission") else []),
                ))
            if len(items) < 12:
                break
            if page == 12:
                STATE["complete"] = False  # Seitenlimit erreicht
    return out


def enrich(l: Listing):
    pass  # externe Seiten sind zu unterschiedlich – hier führt der Button direkt zum Anbieter
