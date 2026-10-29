"""Rights checked by the server from the email verified by Cloudflare
Access (decision of 28 Oct 2026): the name of the terminal no longer gives
rights. First step: the lists « administrateurs » and « PCO », kept in the
server settings; rule: always at least one active administrator
(``SARCADE_ADMIN_EMAILS`` in the .env of the server as safety net)."""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

KEY = "roles"


class InvalidRoles(ValueError):
    pass


def _clean(emails) -> list[str]:
    if not isinstance(emails, list) or len(emails) > 500:
        raise InvalidRoles("invalid_value")
    out: list[str] = []
    for e in emails:
        if not isinstance(e, str):
            raise InvalidRoles("invalid_value")
        e = e.strip().lower()
        if not 3 <= len(e) <= 320 or "@" not in e or " " in e:
            raise InvalidRoles("invalid_email")
        if e not in out:
            out.append(e)
    return out


def env_admins() -> list[str]:
    return [e.strip().lower() for e in os.getenv("SARCADE_ADMIN_EMAILS", "").split(",") if e.strip()]


def stored(db: Session) -> dict:
    from sarcade.updates.service import get_value
    v = get_value(db, KEY, {}) or {}
    return {"admins": list(v.get("admins", [])), "pco": list(v.get("pco", []))}


def save(db: Session, admins, pco) -> dict:
    """New lists; refused if no administrator would remain."""
    from sarcade.updates.service import set_value
    a, p = _clean(admins), _clean(pco)
    if not a and not env_admins():
        raise InvalidRoles("last_admin")
    set_value(db, KEY, {"admins": a, "pco": p})
    return {"admins": a, "pco": p}


def roles_of(db: Session, email: str | None) -> list[str]:
    if not email:
        return []
    e = email.strip().lower()
    s = stored(db)
    out = []
    if e in s["admins"] or e in env_admins():
        out.append("admin")
    if e in s["pco"] or "admin" in out:
        out.append("pco")
    return out
