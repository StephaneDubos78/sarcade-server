"""Event operations run by the PCO: settings, end of event, device last contact.

See « Synchronisation client-serveur » and « Suivi de position » in the vault.
Authentication is not in place yet (ADR-002): actor ids are declared.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sarcade.updates import service as updates_service
from sarcade.aprs import callsigns as calls
from sarcade.db.models import DeviceRow, EventRow, LogbookRow
from sarcade.events import settings as event_settings
from sarcade.realtime.manager import manager

from .deps import get_db

router = APIRouter(prefix="/api/v0.1")


class SettingsPatch(BaseModel):
    actor_id: str = Field(min_length=1, max_length=64)
    settings: dict


class CloseEvent(BaseModel):
    actor_id: str = Field(min_length=1, max_length=64)


class Heartbeat(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    pending_count: int | None = Field(default=None, ge=0)
    oldest_pending_at: datetime | None = None
    tracking_enabled: bool | None = None
    tracking_interval_s: int | None = Field(default=None, ge=1, le=86400)
    callsign: str | None = Field(default=None, max_length=16)
    aprs_tx_consent: bool | None = None


def clean_battery(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if 0 <= value <= 100 else None


def utc(value: datetime | None) -> datetime | None:
    """Times are always returned in UTC, whatever the database session zone."""
    return value.astimezone(UTC) if value is not None else None


def event_dict(row: EventRow) -> dict:
    return {
        "id": row.id, "name": row.name, "kind": row.kind, "status": row.status,
        "summary": row.summary, "created_at": utc(row.created_at), "version": row.version,
        "ended_at": utc(row.ended_at), "settings": event_settings.merged(row.settings),
    }


def device_dict(row: DeviceRow, settings: dict, now: datetime) -> dict:
    return {
        "event_id": row.event_id, "device_id": row.device_id, "label": row.label,
        "platform": row.platform, "app_version": row.app_version,
        "battery_pct": row.battery_pct, "pending_count": row.pending_count,
        "oldest_pending_at": utc(row.oldest_pending_at),
        "tracking_enabled": row.tracking_enabled, "tracking_interval_s": row.tracking_interval_s,
        "callsign": row.callsign, "aprs_tx_consent": row.aprs_tx_consent,
        "last_contact_at": utc(row.last_contact_at), "last_position_at": utc(row.last_position_at),
        "status": event_settings.device_status(row.last_contact_at, settings, now),
    }


def touch_device(db: Session, event_id: str, device_id: str, now: datetime, *,
                 position_time: datetime | None = None, battery_pct: int | None = None) -> DeviceRow:
    """Records a contact from a device (heartbeat, position, sync)."""
    row = db.get(DeviceRow, (event_id, device_id))
    if row is None:
        row = DeviceRow(event_id=event_id, device_id=device_id)
        db.add(row)
    row.last_contact_at = now
    if position_time is not None and (row.last_position_at is None or position_time > row.last_position_at):
        row.last_position_at = position_time
    if battery_pct is not None:
        row.battery_pct = battery_pct
    return row


def _event_or_404(db: Session, event_id: str) -> EventRow:
    row = db.get(EventRow, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return row


@router.get("/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    return event_dict(_event_or_404(db, event_id))


@router.patch("/events/{event_id}/settings")
async def update_settings(event_id: str, payload: SettingsPatch, db: Session = Depends(get_db)):
    row = _event_or_404(db, event_id)
    if row.ended_at is not None:
        raise HTTPException(status_code=409, detail="event_closed")
    try:
        new = event_settings.apply_patch(row.settings, payload.settings)
    except event_settings.InvalidSettings as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    now = datetime.now(UTC)
    for line in event_settings.logbook_summaries(row.settings, new):
        db.add(LogbookRow(event_id=event_id, kind="settings", object_id=event_id,
                          actor_id=payload.actor_id, summary=line, time=now))
    row.settings = new
    row.version = (row.version or 0) + 1
    db.commit()
    data = event_dict(row)
    await manager.broadcast(event_id, {"type": "event.settings.updated", "data": data})
    return data


@router.post("/events/{event_id}/close")
async def close_event(event_id: str, payload: CloseEvent, db: Session = Depends(get_db)):
    """End of event: clients stop position tracking automatically."""
    row = _event_or_404(db, event_id)
    if row.ended_at is None:
        row.ended_at = datetime.now(UTC)
        row.status = "closed"
        row.version = (row.version or 0) + 1
        db.add(LogbookRow(event_id=event_id, kind="event", object_id=event_id,
                          actor_id=payload.actor_id, summary="Fin de l'événement", time=row.ended_at))
        db.commit()
        await manager.broadcast(event_id, {"type": "event.closed", "data": event_dict(row)})
    return event_dict(row)


@router.post("/events/{event_id}/devices/{device_id}/heartbeat")
async def heartbeat(event_id: str, device_id: str, payload: Heartbeat, db: Session = Depends(get_db)):
    """Periodic contact from a client. The answer carries what the device
    must apply: event settings (low-bandwidth mode, tracking policy), the
    tracking interval within the PCO bounds, and the end of the event."""
    if not 1 <= len(device_id) <= 64:
        raise HTTPException(status_code=422, detail="invalid_device_id")
    event = _event_or_404(db, event_id)
    now = datetime.now(UTC)
    row = touch_device(db, event_id, device_id, now, battery_pct=payload.battery_pct)
    if payload.callsign is not None:
        if payload.callsign.strip():
            try:
                row.callsign = calls.normalize(payload.callsign)
            except calls.InvalidCallsign:
                raise HTTPException(status_code=422, detail="invalid_callsign")
        else:
            row.callsign = None
    for field in ("label", "platform", "app_version", "pending_count",
                  "oldest_pending_at", "tracking_enabled", "aprs_tx_consent"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    settings = event_settings.merged(event.settings)
    interval = event_settings.clamp_interval(payload.tracking_interval_s, settings)
    row.tracking_interval_s = interval
    client_update = updates_service.evaluate_client(db, device_id, payload.platform, payload.app_version, now,
                                                    in_active_event=event.ended_at is None)
    db.commit()
    await manager.broadcast(event_id, {"type": "device.updated", "data": device_dict(row, settings, now)})
    return {
        "server_time": now, "event_status": event.status, "ended_at": utc(event.ended_at),
        "settings": settings, "tracking_interval_s": interval,
        "tracking_required": settings["tracking_required"] and event.ended_at is None,
        "client_update": client_update,
    }


@router.get("/events/{event_id}/devices")
def list_devices(event_id: str, db: Session = Depends(get_db)):
    """PCO view of the last contact of each device, late devices first."""
    event = _event_or_404(db, event_id)
    now = datetime.now(UTC)
    settings = event_settings.merged(event.settings)
    rows = db.scalars(select(DeviceRow).where(DeviceRow.event_id == event_id)).all()
    devices = [device_dict(r, settings, now) for r in rows]
    order = {"late": 0, "unknown": 1, "ok": 2}
    epoch = datetime.min.replace(tzinfo=UTC)
    devices.sort(key=lambda d: (order[d["status"]], d["last_contact_at"] or epoch))
    return devices
