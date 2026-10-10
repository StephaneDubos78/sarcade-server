"""Météo-France weather vigilance (department colour map).

Public data under Licence Ouverte 2.0, available only through the
Météo-France API portal with a key (``SARCADE_METEOFRANCE_API_KEY``).
The parser is deliberately tolerant: the structure is ``product.periods[]
.timelaps.domain_ids[]`` with, per department, a maximum colour and the
colour of each phenomenon. To be confirmed with a real key.
"""
from __future__ import annotations

DEFAULT_URL = "https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours"

COLORS = {1: "verte", 2: "jaune", 3: "orange", 4: "rouge"}
PHENOMENA = {
    "1": "vent violent", "2": "pluie-inondation", "3": "orages", "4": "crues",
    "5": "neige-verglas", "6": "canicule", "7": "grand froid", "8": "avalanches",
    "9": "vagues-submersion",
}


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _domains(period: dict) -> list:
    timelaps = period.get("timelaps") or {}
    if isinstance(timelaps, dict):
        return timelaps.get("domain_ids") or []
    if isinstance(timelaps, list):  # some versions: list of time slots
        items = []
        for slot in timelaps:
            items.extend((slot or {}).get("domain_ids") or [])
        return items
    return []


def department_vigilance(data: dict, department: str) -> dict | None:
    """Vigilance of today (first period) for one department, or None."""
    product = (data or {}).get("product") or data or {}
    periods = product.get("periods") or []
    if not periods:
        return None
    period = periods[0]
    wanted = department.upper().lstrip("0") or "0"
    best = None
    for domain in _domains(period):
        if str(domain.get("domain_id", "")).upper().lstrip("0") != wanted:
            continue
        color = _int(domain.get("max_color_id"))
        phenomena = []
        for item in domain.get("phenomenon_items") or []:
            c = _int(item.get("phenomenon_max_color_id"))
            color = max(color, c)
            if c >= 2:
                phenomena.append(PHENOMENA.get(str(item.get("phenomenon_id")), "autre"))
        if best is None or color > best["color_id"]:
            best = {"department": department.upper(), "color_id": color, "color": COLORS.get(color, "inconnue"),
                    "phenomena": phenomena, "begin": period.get("begin_validity_time"),
                    "end": period.get("end_validity_time")}
    return best


def is_alert(vigilance: dict | None) -> bool:
    """Orange or red vigilance: alert the PCO (decision of 10 Oct 2026)."""
    return bool(vigilance) and vigilance["color_id"] >= 3
