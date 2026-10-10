from datetime import datetime
import uuid

from geoalchemy2 import Geography
from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def new_id() -> str:
    return str(uuid.uuid4())


class OrganizationRow(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Operational settings set by the PCO (sarcade.events.settings).
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamRow(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PositionRow(Base):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    point = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    alt_m: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    # "device" (phone or PC), later "aprs".
    source: Mapped[str] = mapped_column(String(16), default="device", nullable=False)


class POIRow(Base):
    __tablename__ = "pois"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(160))
    point = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)



class SyncOperationRow(Base):
    __tablename__ = "sync_operations"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    client_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class MessageRow(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class AckRow(Base):
    __tablename__ = "acks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class LogbookRow(Base):
    __tablename__ = "logbook"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SharedFileRow(Base):
    __tablename__ = "shared_files"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReferenceSiteRow(Base):
    __tablename__ = "reference_sites"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_layer", "source_object_id",
            name="uq_reference_site_source_object",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subtype: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    callsign: Mapped[str | None] = mapped_column(String(64))
    point = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    alt_m: Mapped[float | None] = mapped_column(Float)
    access: Mapped[str | None] = mapped_column(Text)
    clearance: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(64))
    rx_mhz: Mapped[float | None] = mapped_column(Float)
    tx_mhz: Mapped[float | None] = mapped_column(Float)
    ctcss_rx: Mapped[str | None] = mapped_column(String(32))
    ctcss_tx: Mapped[str | None] = mapped_column(String(32))
    offset: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_layer: Mapped[str] = mapped_column(String(128), nullable=False)
    source_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_properties: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MapFeatureRow(Base):
    """Drawn map object. ``data`` holds the client representation (points in
    lat/lon order, style, label); ``geom`` mirrors it for spatial queries."""
    __tablename__ = "map_features"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    geom = mapped_column(Geography(geometry_type="GEOMETRY", srid=4326), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DeviceRow(Base):
    """Last contact of a device in an event: feeds the PCO view of devices
    that no longer report (« vue du dernier contact »)."""
    __tablename__ = "devices"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(120))
    platform: Mapped[str | None] = mapped_column(String(32))
    app_version: Mapped[str | None] = mapped_column(String(32))
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    pending_count: Mapped[int | None] = mapped_column(Integer)
    oldest_pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tracking_enabled: Mapped[bool | None] = mapped_column()
    tracking_interval_s: Mapped[int | None] = mapped_column(Integer)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_position_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommGroupRow(Base):
    """Communication group; ``data`` holds the canonical client fields."""
    __tablename__ = "comm_groups"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
