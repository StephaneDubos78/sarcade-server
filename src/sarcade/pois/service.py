# SPDX-License-Identifier: AGPL-3.0-only
# © SDUBOS Consulting et contributeurs SARCADE
"""Points of interest: rename and delete by synchronisation (decision of
29 Oct 2026, option A). Everyone changes his own points, the PCO all of them;
a deletion is written in the logbook and propagated to the other clients."""
from datetime import UTC, datetime

from geoalchemy2.shape import to_shape

from sarcade.groups.service import is_pco

ACTIONS = ("create", "update", "delete")
MAX_LABEL = 160
# Shape of the icon (card « Points d'intérêt, création claire et icônes »,
# 30 Oct 2026): a simple set; None = the default pin (older points).
ICONS = ("pin", "gathering", "command_post", "danger", "parking", "water", "helipad",
         "vehicle", "viewpoint", "medical", "radio", "shelter", "flag")


class InvalidPoi(ValueError):
    pass


def can_edit(created_by: str | None, actor: str | None, pco: bool = False) -> bool:
    """The author or the PCO (a point without author: the PCO only)."""
    if not actor:
        return False
    return pco or is_pco(actor) or (created_by is not None and actor == created_by)


def clean_color(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise InvalidPoi("invalid_color")
    return value


def clean_icon(value) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value not in ICONS:
        raise InvalidPoi("invalid_icon")
    return value


def clean_label(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidPoi("invalid_label")
    value = value.strip()
    if len(value) > MAX_LABEL:
        raise InvalidPoi("invalid_label")
    return value or None


def actor_of(payload: dict) -> str | None:
    for key in ("updated_by", "created_by"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:64]
    return None


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def state(row) -> dict:
    """JSON state of a point, as journaled in the change feed and broadcast."""
    p = to_shape(row.point)
    out = {"id": row.id, "event_id": row.event_id, "kind": row.kind, "label": row.label,
           "lat": p.y, "lon": p.x, "created_at": _iso(row.created_at), "version": row.version,
           "created_by": row.created_by, "color": row.color, "icon": row.icon,
           "updated_by": row.updated_by, "updated_at": _iso(row.updated_at)}
    if row.deleted_at is not None:
        out["deleted"] = True
        out["deleted_at"] = _iso(row.deleted_at)
    return out


def logbook_summary(label: str | None, action: str) -> str:
    name = f" « {label} »" if label else ""
    return {"delete": f"Point d'intérêt{name} supprimé", "update": f"Point d'intérêt modifié{name}"}.get(
        action, f"Point d'intérêt{name} créé")
