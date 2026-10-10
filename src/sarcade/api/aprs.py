"""APRS API: callsign groups, lines pushed by the Gateway, link status."""
from __future__ import annotations

from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sarcade.aprs import callsigns as calls
from sarcade.aprs.links import handle_line
from sarcade.aprs.service import event_callsigns, runtime
from sarcade.db.models import AprsGroupRow, EventRow

from .deps import get_db

router = APIRouter(prefix="/api/v0.1")


class GroupIn(BaseModel):
    actor_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    callsigns: list[str] = Field(default_factory=list)


class FramesIn(BaseModel):
    via: str = Field(pattern="^(rf|is)$")
    lines: list[str] = Field(max_length=500)


def group_dict(row: AprsGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "callsigns": row.callsigns or [],
            "created_at": row.created_at.astimezone(UTC), "updated_at": row.updated_at.astimezone(UTC),
            "updated_by": row.updated_by}


def _clean(payload: GroupIn) -> list[str]:
    try:
        return calls.normalize_list(payload.callsigns)
    except calls.InvalidCallsign as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/aprs/groups")
def list_groups(db: Session = Depends(get_db)):
    return [group_dict(r) for r in db.scalars(select(AprsGroupRow).order_by(AprsGroupRow.name))]


@router.post("/aprs/groups", status_code=201)
def create_group(payload: GroupIn, db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    row = AprsGroupRow(id=str(uuid.uuid4()), name=payload.name.strip(), callsigns=_clean(payload),
                       created_at=now, updated_at=now, updated_by=payload.actor_id)
    db.add(row)
    db.commit()
    return group_dict(row)


@router.put("/aprs/groups/{group_id}")
def update_group(group_id: str, payload: GroupIn, db: Session = Depends(get_db)):
    row = db.get(AprsGroupRow, group_id)
    if row is None:
        raise HTTPException(status_code=404, detail="aprs_group_not_found")
    row.name, row.callsigns = payload.name.strip(), _clean(payload)
    row.updated_at, row.updated_by = datetime.now(UTC), payload.actor_id
    db.commit()
    return group_dict(row)


@router.delete("/aprs/groups/{group_id}", status_code=204)
def delete_group(group_id: str, db: Session = Depends(get_db)):
    row = db.get(AprsGroupRow, group_id)
    if row is None:
        raise HTTPException(status_code=404, detail="aprs_group_not_found")
    db.delete(row)
    db.commit()


@router.get("/events/{event_id}/aprs/callsigns")
def followed_callsigns(event_id: str, db: Session = Depends(get_db)):
    event = db.get(EventRow, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return {"callsigns": event_callsigns(db, event)}


@router.post("/aprs/frames")
async def push_frames(payload: FramesIn):
    """Decoded TNC2 lines pushed by the Gateway (for instance from a radio
    modem without KISS TCP). Only selected stations are stored."""
    stored = 0
    for line in payload.lines:
        stored += await handle_line(line, payload.via)
    return {"received": len(payload.lines), "stored": stored}


@router.get("/aprs/status")
def status():
    def link(s):
        return {"enabled": s.enabled, "connected": s.connected, "detail": s.detail,
                "last_packet_at": s.last_packet_at, "packets": s.packets}
    return {"aprs_is": link(runtime.aprs_is), "radio": link(runtime.radio),
            "filter": runtime.filter, "stored_positions": runtime.stored}
