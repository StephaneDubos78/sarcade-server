"""SARCADE Pro modules (note 11 « Architecture modulaire et SARCADE Pro »).

v0.1: modules enabled by ``SARCADE_PRO_MODULES`` (comma separated, e.g.
``siem,locate``). The signed licence file replaces this switch with the
Kanban card on Pro licences; the code stays open source (AGPL).
"""
import os

KNOWN = {"siem", "locate"}


def enabled_modules() -> set[str]:
    raw = os.getenv("SARCADE_PRO_MODULES", "")
    return {m.strip().lower() for m in raw.split(",") if m.strip().lower() in KNOWN}


def pro_enabled(module: str) -> bool:
    return module in enabled_modules()
