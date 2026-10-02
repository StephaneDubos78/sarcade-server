from datetime import UTC, datetime
import uuid

from fastapi import Depends, FastAPI, HTTPException
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from sarcade.db.models import EventRow, PositionRow, TeamRow
from sarcade.db.session import SessionLocal
from .schemas import EventCreate, EventOut, PositionCreate, TeamCreate, TeamOut

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
    row = EventRow(
        id=str(uuid.uuid4()),
        name=payload.name,
        kind=payload.kind,
        summary=payload.summary,
        status="draft",
        created_at=datetime.now(UTC),
        version=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/v0.1/events/{event_id}/teams", response_model=TeamOut, status_code=201)
def create_team(event_id: str, payload: TeamCreate, db: Session = Depends(get_db)):
    if db.get(EventRow, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    row = TeamRow(id=str(uuid.uuid4()), event_id=event_id, name=payload.name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/v0.1/positions", status_code=202)
def ingest_position(payload: PositionCreate, db: Session = Depends(get_db)):
    if db.get(PositionRow, payload.id) is not None:
        return {"status": "duplicate", "id": payload.id}
    if db.get(EventRow, payload.event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    row = PositionRow(
        id=payload.id,
        event_id=payload.event_id,
        device_id=payload.device_id,
        point=WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326),
        alt_m=payload.alt_m,
        accuracy_m=payload.accuracy_m,
        heading_deg=payload.heading_deg,
        speed_mps=payload.speed_mps,
        time=payload.time,
    )
    db.add(row)
    db.commit()
    return {"status": "accepted", "id": payload.id}
