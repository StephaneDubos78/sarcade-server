from geoalchemy2.shape import to_shape

from sarcade.db.models import POIRow, PositionRow, ReferenceSiteRow


def position_dict(row: PositionRow) -> dict:
    p = to_shape(row.point)
    return {
        "id": row.id, "event_id": row.event_id, "device_id": row.device_id,
        "lat": p.y, "lon": p.x, "alt_m": row.alt_m,
        "accuracy_m": row.accuracy_m, "heading_deg": row.heading_deg,
        "speed_mps": row.speed_mps, "time": row.time,
    }


def poi_dict(row: POIRow) -> dict:
    p = to_shape(row.point)
    return {
        "id": row.id, "event_id": row.event_id, "kind": row.kind,
        "label": row.label, "lat": p.y, "lon": p.x,
        "created_at": row.created_at, "version": row.version,
    }


def reference_site_dict(row: ReferenceSiteRow) -> dict:
    p = to_shape(row.point)
    return {
        "id": row.id,
        "category": row.category,
        "subtype": row.subtype,
        "name": row.name,
        "callsign": row.callsign,
        "lat": p.y,
        "lon": p.x,
        "alt_m": row.alt_m,
        "access": row.access,
        "clearance": row.clearance,
        "mode": row.mode,
        "rx_mhz": row.rx_mhz,
        "tx_mhz": row.tx_mhz,
        "ctcss_rx": row.ctcss_rx,
        "ctcss_tx": row.ctcss_tx,
        "offset": row.offset,
        "description": row.description,
        "verified_at": row.verified_at,
        "source": row.source,
        "source_layer": row.source_layer,
        "status": row.status,
    }
