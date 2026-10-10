"""Operational settings of an event, set by the PCO.

Covers the low-bandwidth mode (see « Synchronisation client-serveur » in the
vault) and the position tracking policy (« Suivi de position », Beacon in
English). Pure functions: validation, logbook summaries and device status, so
that the rules are testable without a database.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# Intervals offered to operators, in seconds (10 s to 10 min).
TRACKING_INTERVALS = (10, 30, 60, 120, 300, 600)

DEFAULT_SETTINGS: dict = {
    # Low-bandwidth mode, imposed by the PCO: grouped sending, no photos.
    "low_bandwidth": False,
    "low_bandwidth_interval_s": 60,
    # Alert when items wait in a device outbox, and stale device threshold.
    "sync_alert_minutes": 5,
    # Position tracking: operator choice, may be required by the PCO.
    "tracking_required": False,
    "tracking_default_interval_s": 30,
    "tracking_min_interval_s": 10,
    "tracking_max_interval_s": 600,
    # APRS (note « APRS »): callsign groups followed by the event, callsigns
    # added by the PCO for the event, local radio transmission of positions.
    "aprs_groups": [],
    "aprs_callsigns": [],
    "aprs_tx_rf": False,
}

_BOOL_KEYS = {"low_bandwidth", "tracking_required", "aprs_tx_rf"}
_LIST_KEYS = {"aprs_groups", "aprs_callsigns"}
_INT_RANGES = {
    "low_bandwidth_interval_s": (15, 3600),
    "sync_alert_minutes": (1, 120),
}
_INTERVAL_KEYS = {"tracking_default_interval_s", "tracking_min_interval_s", "tracking_max_interval_s"}


class InvalidSettings(ValueError):
    pass


def merged(stored: dict | None) -> dict:
    """Stored settings completed with the defaults (older events)."""
    result = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_SETTINGS.items()}
    result.update({k: v for k, v in (stored or {}).items() if k in DEFAULT_SETTINGS})
    return result


def apply_patch(stored: dict | None, patch: dict) -> dict:
    """Returns the new settings, or raises InvalidSettings."""
    if not isinstance(patch, dict) or not patch:
        raise InvalidSettings("empty_patch")
    result = merged(stored)
    for key, value in patch.items():
        if key not in DEFAULT_SETTINGS:
            raise InvalidSettings(f"unknown_setting:{key}")
        if key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise InvalidSettings(f"invalid_value:{key}")
        elif key in _LIST_KEYS:
            value = _clean_list(key, value)
        elif key in _INTERVAL_KEYS:
            if isinstance(value, bool) or value not in TRACKING_INTERVALS:
                raise InvalidSettings(f"invalid_value:{key}")
        else:
            low, high = _INT_RANGES[key]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise InvalidSettings(f"invalid_value:{key}")
        result[key] = value
    if not (result["tracking_min_interval_s"] <= result["tracking_default_interval_s"]
            <= result["tracking_max_interval_s"]):
        raise InvalidSettings("inconsistent_tracking_bounds")
    return result


def _clean_list(key: str, value) -> list[str]:
    if key == "aprs_callsigns":
        from sarcade.aprs.callsigns import InvalidCallsign, normalize_list
        try:
            return normalize_list(value)
        except InvalidCallsign as exc:
            raise InvalidSettings(f"invalid_value:{key}") from exc
    if not isinstance(value, list) or len(value) > 50 or not all(
            isinstance(v, str) and 0 < len(v) <= 64 for v in value):
        raise InvalidSettings(f"invalid_value:{key}")
    return list(dict.fromkeys(value))


def clamp_interval(requested: int | None, settings: dict) -> int:
    """Interval actually used by a device: the operator's choice within the
    bounds set by the PCO, or the event default."""
    s = merged(settings)
    if requested is None:
        return s["tracking_default_interval_s"]
    return max(s["tracking_min_interval_s"], min(s["tracking_max_interval_s"], int(requested)))


def _duration(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds >= 60 and seconds % 60 == 0 else f"{seconds} s"


def logbook_summaries(old: dict | None, new: dict) -> list[str]:
    """French logbook lines describing what the PCO changed."""
    before, after = merged(old), merged(new)
    lines = []
    if before["low_bandwidth"] != after["low_bandwidth"]:
        lines.append("Mode liaison faible activé par le PCO" if after["low_bandwidth"]
                     else "Mode liaison faible levé par le PCO")
    if after["low_bandwidth"] and before["low_bandwidth_interval_s"] != after["low_bandwidth_interval_s"]:
        lines.append(f"Liaison faible : envoi groupé toutes les {_duration(after['low_bandwidth_interval_s'])}")
    if before["tracking_required"] != after["tracking_required"]:
        lines.append("Suivi de position imposé par le PCO" if after["tracking_required"]
                     else "Suivi de position laissé au choix des opérateurs")
    bounds = ("tracking_min_interval_s", "tracking_default_interval_s", "tracking_max_interval_s")
    if any(before[k] != after[k] for k in bounds):
        lines.append(
            "Suivi de position : fréquence de "
            f"{_duration(after['tracking_min_interval_s'])} à {_duration(after['tracking_max_interval_s'])}, "
            f"{_duration(after['tracking_default_interval_s'])} par défaut")
    if before["aprs_groups"] != after["aprs_groups"] or before["aprs_callsigns"] != after["aprs_callsigns"]:
        lines.append(f"APRS : {len(after['aprs_groups'])} groupe(s) d'indicatifs et "
                     f"{len(after['aprs_callsigns'])} indicatif(s) ajouté(s) suivis")
    if before["aprs_tx_rf"] != after["aprs_tx_rf"]:
        lines.append("APRS : émission radio locale des positions activée par le PCO" if after["aprs_tx_rf"]
                     else "APRS : émission radio locale des positions arrêtée")
    if before["sync_alert_minutes"] != after["sync_alert_minutes"]:
        lines.append(f"Alerte de synchronisation après {after['sync_alert_minutes']} min")
    return lines


def device_status(last_contact_at: datetime | None, settings: dict, now: datetime) -> str:
    """« ok », « late » (beyond the alert threshold) or « unknown »."""
    if last_contact_at is None:
        return "unknown"
    limit = timedelta(minutes=merged(settings)["sync_alert_minutes"])
    return "late" if now - last_contact_at > limit else "ok"
