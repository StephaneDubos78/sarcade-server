from datetime import UTC, datetime
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sarcade.db.models import EventRow, POIRow, PositionRow, SyncOperationRow, TeamRow
from sarcade.db.session import SessionLocal
from sarcade.realtime.manager import manager
from .schemas import EventCreate, EventOut, POICreate, POIOut, PositionCreate, PositionOut, SyncOperationIn, SyncResultOut, TeamCreate, TeamOut
from .serializers import poi_dict, position_dict
from sarcade.sync.service import record_operation

app = FastAPI(title="SARCADE Server", version="0.1.0-dev")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "sarcade-server"}


@app.post("/api/v0.1/events", response_model=EventOut, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    row = EventRow(id=str(uuid.uuid4()), name=payload.name, kind=payload.kind, summary=payload.summary,
                   status="draft", created_at=datetime.now(UTC), version=0)
    db.add(row); db.commit(); db.refresh(row)
    return row


@app.post("/api/v0.1/events/{event_id}/teams", response_model=TeamOut, status_code=201)
def create_team(event_id: str, payload: TeamCreate, db: Session = Depends(get_db)):
    if db.get(EventRow, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    row = TeamRow(id=str(uuid.uuid4()), event_id=event_id, name=payload.name)
    db.add(row); db.commit(); db.refresh(row)
    return row


@app.post("/api/v0.1/positions", status_code=202)
async def ingest_position(payload: PositionCreate, db: Session = Depends(get_db)):
    if db.get(PositionRow, payload.id) is not None:
        return {"status": "duplicate", "id": payload.id}
    if db.get(EventRow, payload.event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    row = PositionRow(id=payload.id, event_id=payload.event_id, device_id=payload.device_id,
        point=WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326), alt_m=payload.alt_m,
        accuracy_m=payload.accuracy_m, heading_deg=payload.heading_deg,
        speed_mps=payload.speed_mps, time=payload.time)
    db.add(row); db.commit(); db.refresh(row)
    data = position_dict(row)
    await manager.broadcast(payload.event_id, {"type": "position.updated", "data": data})
    return {"status": "accepted", "id": payload.id}


@app.get("/api/v0.1/events/{event_id}/positions/latest", response_model=list[PositionOut])
def latest_positions(event_id: str, db: Session = Depends(get_db)):
    if db.get(EventRow, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    ranked = select(PositionRow.id, func.row_number().over(
        partition_by=PositionRow.device_id, order_by=PositionRow.time.desc()).label("rn")
    ).where(PositionRow.event_id == event_id).subquery()
    rows = db.scalars(select(PositionRow).join(ranked, PositionRow.id == ranked.c.id).where(ranked.c.rn == 1)).all()
    return [position_dict(row) for row in rows]


@app.get("/api/v0.1/events/{event_id}/devices/{device_id}/positions", response_model=list[PositionOut])
def position_history(event_id: str, device_id: str, limit: int = Query(500, ge=1, le=5000), db: Session = Depends(get_db)):
    rows = db.scalars(select(PositionRow).where(
        PositionRow.event_id == event_id, PositionRow.device_id == device_id
    ).order_by(PositionRow.time.desc()).limit(limit)).all()
    return [position_dict(row) for row in reversed(rows)]


@app.post("/api/v0.1/events/{event_id}/pois", response_model=POIOut, status_code=201)
async def create_poi(event_id: str, payload: POICreate, db: Session = Depends(get_db)):
    if db.get(EventRow, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if db.get(POIRow, payload.id) is not None:
        raise HTTPException(status_code=409, detail="poi_already_exists")
    row = POIRow(id=payload.id, event_id=event_id, kind=payload.kind, label=payload.label,
        point=WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326),
        created_at=datetime.now(UTC), version=0)
    db.add(row); db.commit(); db.refresh(row)
    data = poi_dict(row)
    await manager.broadcast(event_id, {"type": "poi.created", "data": data})
    return data


@app.get("/api/v0.1/events/{event_id}/pois", response_model=list[POIOut])
def list_pois(event_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(POIRow).where(POIRow.event_id == event_id).order_by(POIRow.created_at)).all()
    return [poi_dict(row) for row in rows]


@app.websocket("/api/v0.1/events/{event_id}/ws")
async def event_websocket(websocket: WebSocket, event_id: str):
    await manager.connect(event_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(event_id, websocket)


@app.post("/api/v0.1/sync", response_model=list[SyncResultOut])
def synchronize(operations: list[SyncOperationIn], db: Session = Depends(get_db)):
    results = []
    for op in operations:
        status, cursor = record_operation(
            db, event_id=op.event_id, operation_id=op.operation_id,
            object_id=op.object_id, object_type=op.object_type,
            action=op.action, payload=op.payload, client_time=op.client_time,
        )
        results.append({
            "operation_id": op.operation_id,
            "status": status,
            "server_time": datetime.now(UTC),
            "sync_cursor": str(cursor) if cursor else None,
        })
    db.commit()
    return results


@app.get("/api/v0.1/events/{event_id}/sync/changes")
def sync_changes(event_id: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000), db: Session = Depends(get_db)):
    rows = db.scalars(select(SyncOperationRow).where(
        SyncOperationRow.event_id == event_id, SyncOperationRow.seq > after
    ).order_by(SyncOperationRow.seq).limit(limit)).all()
    return {
        "changes": [{"cursor": str(r.seq), "operation_id": r.operation_id, "object_id": r.object_id,
                     "object_type": r.object_type, "action": r.action, "payload": r.payload,
                     "server_time": r.server_time} for r in rows],
        "next_cursor": str(rows[-1].seq) if rows else str(after),
    }
