"""Server state of the updates: administration settings, check of a new
server version, minimal client version, client packages distributed by
the local server."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from importlib import metadata
import logging
import os

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sarcade.db.models import ClientDeviceRow, DeviceRow, EventRow, ServerSettingRow
from sarcade.security import journal

from . import policy

log = logging.getLogger("sarcade.updates")
DEFAULT_RELEASES_URL = "https://api.github.com/repos/StephaneDubos78/sarcade-server/releases/latest"
CLIENT_PLATFORMS = ("windows", "appimage", "apk")


def installed_version() -> str:
    v = os.getenv("SARCADE_VERSION")
    if v:
        return v
    try:
        return metadata.version("sarcade-server")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def get_value(db: Session, key: str, default=None):
    row = db.get(ServerSettingRow, key)
    return row.value if row is not None else default


def set_value(db: Session, key: str, value, now: datetime | None = None) -> None:
    row = db.get(ServerSettingRow, key)
    now = now or datetime.now(UTC)
    if row is None:
        db.add(ServerSettingRow(key=key, value=value, updated_at=now))
    else:
        row.value, row.updated_at = value, now


def admin_settings(db: Session) -> dict:
    return policy.validate(get_value(db, "admin", {}) or {})


def client_organization(db: Session) -> dict:
    """Settings of the organisation applied by the clients: navigation app
    and HTTPS address the clients switch to (docs/https-v0.1.md)."""
    from sarcade import tls
    t = tls.state()
    return {"navigation": admin_settings(db)["navigation"],
            "https": {"url": t["https_url"], "root_certificate_url": t["root_certificate_url"]}}


def merge_patch(current: dict, patch: dict) -> dict:
    out = dict(current)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **value}
        else:
            out[key] = value
    return out


def active_events(db: Session, now: datetime) -> list[str]:
    """Events not closed with activity (device contact or creation) in the
    last 24 hours."""
    last_contact = (select(DeviceRow.event_id, func.max(DeviceRow.last_contact_at).label("last"))
                    .group_by(DeviceRow.event_id).subquery())
    rows = db.execute(select(EventRow.id, EventRow.created_at, EventRow.ended_at, last_contact.c.last)
                      .outerjoin(last_contact, last_contact.c.event_id == EventRow.id)
                      .where(EventRow.ended_at.is_(None))).all()
    out = []
    for event_id, created_at, ended_at, last in rows:
        activity = max(t for t in (created_at, last) if t is not None) if (created_at or last) else None
        if policy.event_is_active(ended_at, activity, now):
            out.append(event_id)
    return out


def device_in_active_event(db: Session, device_id: str, now: datetime) -> bool:
    rows = db.execute(select(DeviceRow.last_contact_at).join(EventRow, EventRow.id == DeviceRow.event_id)
                      .where(DeviceRow.device_id == device_id, EventRow.ended_at.is_(None))).all()
    return any(policy.event_is_active(None, last, now) for (last,) in rows)


# --- Minimal client version -------------------------------------------------

def evaluate_client(db: Session, device_id: str, platform: str | None, app_version: str | None, now: datetime,
                    in_active_event: bool | None = None, source_ip: str | None = None) -> dict:
    """Invitation, then obligation 2 hours later, deferred to the end of the
    active event. Each step goes to the security journal once."""
    min_version = admin_settings(db)["clients"]["min_version"]
    row = db.get(ClientDeviceRow, device_id)
    if row is None:
        row = ClientDeviceRow(device_id=device_id, deferred_logged=False, refused_logged=False)
        db.add(row)
    row.platform = platform or row.platform
    row.app_version = app_version or row.app_version
    row.last_check_at = now
    if not policy.is_older(row.app_version, min_version):
        if row.invited_at is not None:
            journal.record(db, "update", "client_updated", "success", device_id=device_id, source_ip=source_ip,
                           details={"version": row.app_version, "platform": row.platform})
        row.invited_at = row.invited_for = None
        row.deferred_logged = row.refused_logged = False
        return {"status": "ok", "min_version": min_version, "deadline": None}
    if row.invited_at is None or row.invited_for != min_version:
        row.invited_at, row.invited_for = now, min_version
        row.deferred_logged = row.refused_logged = False
        journal.record(db, "update", "client_invited", "info", device_id=device_id, source_ip=source_ip,
                       details={"version": row.app_version, "min_version": min_version, "platform": row.platform})
    if in_active_event is None:
        in_active_event = device_in_active_event(db, device_id, now)
    status, deadline = policy.client_status(app_version=row.app_version, min_version=min_version,
                                            invited_at=row.invited_at, now=now, in_active_event=in_active_event)
    if status == "deferred" and not row.deferred_logged:
        row.deferred_logged = True
        journal.record(db, "update", "client_obligation_deferred", "deferred", device_id=device_id,
                       source_ip=source_ip, details={"version": row.app_version, "min_version": min_version})
    if status == "required" and not row.refused_logged:
        row.refused_logged = True
        journal.record(db, "update", "client_refused_outdated", "refused", device_id=device_id,
                       source_ip=source_ip, details={"version": row.app_version, "min_version": min_version})
    package = (get_value(db, "client_packages", {}) or {}).get(platform or "")
    return {"status": status, "min_version": min_version, "deadline": journal.iso(deadline) if deadline else None,
            "package": package_info(platform, package) if package else None}


def package_info(platform: str, package: dict) -> dict:
    return {"platform": platform, "version": package["version"], "sha256": package["sha256"],
            "size": package["size"], "url": f"/api/v0.1/clients/{platform}/package",
            "uploaded_at": package["uploaded_at"]}


# --- New server version -----------------------------------------------------

async def check_latest(client: httpx.AsyncClient | None = None) -> dict:
    url = os.getenv("SARCADE_RELEASES_URL", DEFAULT_RELEASES_URL)
    now = datetime.now(UTC)
    status = {"checked_at": journal.iso(now), "available": None, "url": None, "error": None}
    try:
        own = client is None
        client = client or httpx.AsyncClient(timeout=20, headers={"Accept": "application/vnd.github+json"})
        try:
            r = await client.get(url)
        finally:
            if own:
                await client.aclose()
        if r.status_code == 200:
            data = r.json()
            tag = str(data.get("tag_name", "")).strip()
            status["available"] = tag.lstrip("vV") or None
            status["url"] = data.get("html_url")
        else:
            status["error"] = f"http_{r.status_code}"
    except (httpx.HTTPError, ValueError) as exc:
        status["error"] = type(exc).__name__
    from sarcade.db.session import SessionLocal
    db = SessionLocal()
    try:
        previous = get_value(db, "update_status", {}) or {}
        set_value(db, "update_status", status, now)
        if status["available"] and status["available"] != previous.get("available") \
                and policy.is_older(installed_version(), status["available"]):
            journal.record(db, "update", "server_version_available", "info", actor="SARCADE",
                           details={"installed": installed_version(), "available": status["available"]})
        db.commit()
    finally:
        db.close()
    return status


async def check_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            await check_latest()
        except Exception as exc:  # noqa: BLE001
            log.warning("update check failed: %s", exc)
        await asyncio.sleep(24 * 3600)


async def retention_loop() -> None:
    from sarcade.db.session import SessionLocal
    while True:
        db = SessionLocal()
        try:
            n = journal.purge(db, admin_settings(db)["journal_retention_days"])
            db.commit()
            if n:
                log.info("security journal: %s entries past retention removed", n)
        except Exception as exc:  # noqa: BLE001
            log.warning("journal retention failed: %s", exc)
        finally:
            db.close()
        await asyncio.sleep(24 * 3600)


def start(tasks: list) -> None:
    tasks.append(asyncio.create_task(retention_loop()))
    if os.getenv("SARCADE_UPDATE_CHECK", "1") != "0":
        tasks.append(asyncio.create_task(check_loop()))
