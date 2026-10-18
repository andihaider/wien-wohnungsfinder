"""Bewertung und Standard-Kriterien – gleiche Logik wie in docs/app.js (dort mit deinen App-Einstellungen)."""
from datetime import datetime, timezone

# Standard-Kriterien (für die Push-Nachricht; in der App pro Handy einstellbar)
FLAT_MAX_PRICE = 650
WG_MAX_PRICE = 600
WG_MIN_ROOM = 15      # m²
WG_MAX_PEOPLE = 4     # "4er WG" inkl. dir


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _hours(iso):
    if not iso:
        return 1e9
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 3600
    except ValueError:
        return 1e9


def _has(it, f):
    return f in (it.get("flags") or [])


def _fresh_points(it):
    age = min(_hours(it.get("first_seen")), _hours(it.get("published")))
    return 15 if age < 24 else 9 if age < 72 else 4 if age < 168 else 0


def score(it, flat_max=FLAT_MAX_PRICE, wg_max=WG_MAX_PRICE):
    price, area = it.get("price_total") or 0, it.get("area") or 0
    s = 0.0
    if it.get("category") == "wg":
        s += 30 * _clamp((wg_max - price) / (wg_max * 0.35))           # günstiger
        s += 30 * _clamp((area - 12) / 13)                             # Zimmer 12 m² → 0, 25 m² → voll
        size = it.get("wg_size")
        s += {2: 10, 3: 7, 4: 3}.get(size, 0)                           # kleine WG = ruhiger
        s += _fresh_points(it)
        if any(_has(it, f) for f in ("Balkon", "Terrasse", "Loggia", "Garten")):
            s += 6
        if _has(it, "Altbau") or _has(it, "saniert") or _has(it, "Neubau/Erstbezug"):
            s += 4
        if _has(it, "unbefristet"):
            s += 3
        if _has(it, "befristet"):
            s -= 5
    else:
        s += 25 * _clamp((flat_max - price) / (flat_max * 0.35))
        if it.get("ppsqm"):
            s += 30 * _clamp((20 - it["ppsqm"]) / 10)
        s += 20 * _clamp((area - 25) / 30)
        s += _fresh_points(it)
        if _has(it, "provisionsfrei"):
            s += 5
        if any(_has(it, f) for f in ("Balkon", "Terrasse", "Loggia", "Garten")):
            s += 5
        if _has(it, "unbefristet"):
            s += 4
        if _has(it, "Lift"):
            s += 2
        if it.get("email"):
            s += 3
        if _has(it, "befristet"):
            s -= 5
        if _has(it, "Ablöse"):
            s -= 4
        if it.get("price_estimated"):
            s -= 3
    if _has(it, "Bezahlportal"):
        s -= 15
    if _has(it, "Zwischenmiete"):
        s -= 10
    if it.get("eigenmittel"):
        s -= min(12, it["eigenmittel"] / 2500)   # z. B. 15.000 € Eigenmittel → −6
    return round(_clamp(s, 0, 100))


def matches_default(it):
    """Würde die Wohnung/das Zimmer mit den Standard-Einstellungen angezeigt?"""
    if it.get("excluded") or _has(it, "Bezahlportal") or _has(it, "Zwischenmiete"):
        return False
    if it.get("category") == "wg":
        return (it["price_total"] <= WG_MAX_PRICE and (it.get("area") or 0) >= WG_MIN_ROOM
                and (it.get("wg_size") or 0) <= WG_MAX_PEOPLE)
    return it["price_total"] <= FLAT_MAX_PRICE
