"""Map features: drawn, structured map objects (zones, lines, circles, texts...).

Conflict rule (ADR-001): last writer wins per object. Every change carries the
full object state with ``updated_at`` and ``updated_by``. A change applies only
if (updated_at, updated_by) is strictly newer than the stored pair. Create and
update are both upserts. Delete is a newer change that sets a tombstone, and a
change newer than the tombstone brings the object back (undo of a delete).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math

KINDS = {"point", "line", "arrow", "circle", "rectangle", "zone", "text", "freehand", "measure"}
POINT_KINDS = {"point", "text", "circle"}
POLYGON_KINDS = {"rectangle", "zone"}
ACTIONS = {"create", "update", "delete"}

MAX_POINTS = 5000
MAX_LABEL = 160
MAX_FUTURE_SKEW = timedelta(minutes=5)


class InvalidFeature(ValueError):
    """Payload that can never be applied: the operation is rejected."""


def parse_time(value) -> datetime:
    if isinstance(value, datetime):
        t = value
    elif isinstance(value, str):
        try:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidFeature("invalid_updated_at") from exc
    else:
        raise InvalidFeature("invalid_updated_at")
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def clamp_time(t: datetime, now: datetime) -> datetime:
    """A device clock far in the future must not win every conflict."""
    return now if t > now + MAX_FUTURE_SKEW else t


def _points(raw) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or not raw:
        raise InvalidFeature("invalid_points")
    if len(raw) > MAX_POINTS:
        raise InvalidFeature("too_many_points")
    points = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise InvalidFeature("invalid_points")
        lat, lon = item
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon)):
            raise InvalidFeature("invalid_points")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InvalidFeature("point_out_of_range")
        points.append((float(lat), float(lon)))
    return points


def validate_upsert(payload: dict, *, event_id: str, object_id: str) -> dict:
    """Checks a create/update payload and returns its canonical form."""
    if not isinstance(payload, dict):
        raise InvalidFeature("invalid_payload")
    if payload.get("id") != object_id or payload.get("event_id") != event_id:
        raise InvalidFeature("id_mismatch")
    kind = payload.get("kind")
    if kind not in KINDS:
        raise InvalidFeature("invalid_kind")
    points = _points(payload.get("points"))
    minimum = 1 if kind in POINT_KINDS else 3 if kind == "zone" else 2
    if len(points) < minimum:
        raise InvalidFeature("not_enough_points")
    radius = payload.get("radius_m")
    if kind == "circle":
        if not isinstance(radius, (int, float)) or not math.isfinite(radius) or not (0 < radius <= 500_000):
            raise InvalidFeature("invalid_radius")
        radius = float(radius)
    else:
        radius = None
    color = payload.get("color")
    if not isinstance(color, int) or not (0 <= color <= 0xFFFFFFFF):
        raise InvalidFeature("invalid_color")
    width = payload.get("stroke_width")
    if not isinstance(width, (int, float)) or not (0.5 <= width <= 30):
        raise InvalidFeature("invalid_stroke_width")
    label = payload.get("label") or ""
    if not isinstance(label, str) or len(label) > MAX_LABEL:
        raise InvalidFeature("invalid_label")
    updated_by = payload.get("updated_by") or payload.get("created_by")
    if not isinstance(updated_by, str) or not updated_by or len(updated_by) > 64:
        raise InvalidFeature("invalid_updated_by")
    created_by = payload.get("created_by") if isinstance(payload.get("created_by"), str) else updated_by
    return {
        "id": object_id,
        "event_id": event_id,
        "kind": kind,
        "points": [[lat, lon] for lat, lon in points],
        "radius_m": radius,
        "color": color,
        "stroke_width": float(width),
        "label": label.strip(),
        "created_by": created_by[:64],
        "updated_by": updated_by,
        "updated_at": parse_time(payload.get("updated_at")),
    }


def validate_delete(payload: dict, *, event_id: str, object_id: str) -> dict:
    if not isinstance(payload, dict):
        raise InvalidFeature("invalid_payload")
    if payload.get("id", object_id) != object_id or payload.get("event_id", event_id) != event_id:
        raise InvalidFeature("id_mismatch")
    updated_by = payload.get("updated_by")
    if not isinstance(updated_by, str) or not updated_by or len(updated_by) > 64:
        raise InvalidFeature("invalid_updated_by")
    return {"id": object_id, "event_id": event_id, "updated_by": updated_by,
            "updated_at": parse_time(payload.get("updated_at"))}


def geometry_wkt(data: dict) -> str:
    """PostGIS geometry of a canonical feature, in lon/lat order."""
    pts = [(lon, lat) for lat, lon in data["points"]]
    kind = data["kind"]
    if kind in POINT_KINDS:
        lon, lat = pts[0]
        return f"POINT({lon} {lat})"
    if kind == "rectangle":
        (lon1, lat1), (lon2, lat2) = pts[0], pts[1]
        ring = [(lon1, lat1), (lon2, lat1), (lon2, lat2), (lon1, lat2), (lon1, lat1)]
        return "POLYGON((" + ",".join(f"{x} {y}" for x, y in ring) + "))"
    if kind == "zone":
        ring = pts + [pts[0]]
        return "POLYGON((" + ",".join(f"{x} {y}" for x, y in ring) + "))"
    return "LINESTRING(" + ",".join(f"{x} {y}" for x, y in pts) + ")"


def is_newer(incoming_at: datetime, incoming_by: str, stored_at: datetime | None, stored_by: str | None) -> bool:
    """Total order on changes: time first, author as a deterministic tie-break."""
    if stored_at is None:
        return True
    return (incoming_at, incoming_by) > (stored_at, stored_by or "")


@dataclass
class Decision:
    status: str  # accepted | conflict
    tombstone: bool = False


def decide(action: str, change: dict, stored) -> Decision:
    """Applies ADR-001 to an incoming change against the stored row (or None)."""
    if stored is not None and not is_newer(change["updated_at"], change["updated_by"], stored.updated_at, stored.updated_by):
        return Decision("conflict")
    # A delete of an object this server never saw still stores a tombstone,
    # so a late create with an older timestamp cannot bring it back.
    return Decision("accepted", tombstone=action == "delete")


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def feature_dict(row) -> dict:
    """Client representation, used by the API, the change feed and realtime."""
    data = dict(row.data)
    data.update({
        "id": row.id, "event_id": row.event_id, "kind": row.kind,
        "updated_at": iso(row.updated_at), "updated_by": row.updated_by,
        "created_by": row.created_by, "revision": row.revision,
        "deleted": row.deleted_at is not None,
    })
    return data


def feature_geojson(row) -> dict:
    data = feature_dict(row)
    pts = [[lon, lat] for lat, lon in data["points"]]
    if row.kind in POINT_KINDS:
        geometry = {"type": "Point", "coordinates": pts[0]}
    elif row.kind == "rectangle":
        (lon1, lat1), (lon2, lat2) = pts[0], pts[1]
        geometry = {"type": "Polygon", "coordinates": [[[lon1, lat1], [lon2, lat1], [lon2, lat2], [lon1, lat2], [lon1, lat1]]]}
    elif row.kind == "zone":
        geometry = {"type": "Polygon", "coordinates": [pts + [pts[0]]]}
    else:
        geometry = {"type": "LineString", "coordinates": pts}
    properties = {
        "sarcade:kind": row.kind, "event_id": row.event_id,
        "stroke": "#%06x" % (data["color"] & 0xFFFFFF), "stroke-width": data["stroke_width"],
        "updated_at": data["updated_at"], "updated_by": data["updated_by"],
    }
    if data.get("label"):
        properties["name"] = data["label"]
    if row.kind == "circle":
        properties["radius_m"] = data["radius_m"]
    return {"type": "Feature", "id": row.id, "geometry": geometry, "properties": properties}


def logbook_summary(kind: str, label: str, action: str) -> str:
    names = {"point": "Point", "line": "Ligne", "arrow": "Flèche", "circle": "Cercle",
             "rectangle": "Rectangle", "zone": "Zone", "text": "Texte", "freehand": "Tracé libre",
             "measure": "Mesure"}
    what = names.get(kind, "Objet")
    if label:
        what += f" « {label} »"
    verb = {"create": "créé", "delete": "supprimé", "restore": "restauré"}.get(action, "modifié")
    return f"Objet cartographique {verb} : {what}"


def utcnow() -> datetime:
    return datetime.now(UTC)
