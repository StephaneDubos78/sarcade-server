"""Weather on the server: fetched hourly when Internet is available, cached
and served to the clients over the local network (note « Prévisions météo »).

Configuration (environment):

* ``SARCADE_WEATHER`` (default ``1``): hourly refresh of active events.
* ``SARCADE_OPEN_METEO_URL`` (default ``https://api.open-meteo.com``) and
  ``SARCADE_OPEN_METEO_API_KEY``: commercial use of Open-Meteo (SARCADE Pro)
  needs a subscription and the customer URL.
* ``SARCADE_METEOFRANCE_API_KEY``, ``SARCADE_VIGILANCE_URL``: Météo-France
  vigilance (portal key); ``SARCADE_DEPARTMENT``: default department.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import os

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sarcade.db.models import EventRow, LogbookRow, PositionRow, WeatherCacheRow
from sarcade.db.session import SessionLocal
from sarcade.events import settings as event_settings
from sarcade.realtime.manager import manager

from . import forecast as fc
from . import vigilance as vg

log = logging.getLogger("sarcade.weather")
REFRESH_SECONDS = 3600


class WeatherUnavailable(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


async def fetch_forecast(lat: float, lon: float, client: httpx.AsyncClient | None = None) -> dict:
    """Météo-France first, Open-Meteo as fallback."""
    base = _env("SARCADE_OPEN_METEO_URL", "https://api.open-meteo.com")
    key = _env("SARCADE_OPEN_METEO_API_KEY") or None
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    errors = []
    try:
        for provider in fc.ORDER:
            try:
                r = await client.get(fc.request_url(provider, lat, lon, base, key))
                r.raise_for_status()
                return fc.parse(provider, r.json(), datetime.now(UTC))
            except (httpx.HTTPError, ValueError, fc.InvalidForecast) as exc:
                errors.append(f"{provider}: {exc}")
    finally:
        if own:
            await client.aclose()
    raise WeatherUnavailable("; ".join(errors))


async def fetch_vigilance(department: str, client: httpx.AsyncClient | None = None) -> dict | None:
    key = _env("SARCADE_METEOFRANCE_API_KEY")
    if not key or not department:
        return None
    url = _env("SARCADE_VIGILANCE_URL", vg.DEFAULT_URL)
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        r = await client.get(url, headers={"apikey": key, "accept": "application/json"})
        r.raise_for_status()
        return vg.department_vigilance(r.json(), department)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("vigilance unavailable: %s", exc)
        return None
    finally:
        if own:
            await client.aclose()


def cache_get(db: Session, key: str) -> WeatherCacheRow | None:
    return db.get(WeatherCacheRow, key)


def cache_put(db: Session, key: str, data: dict, now: datetime) -> None:
    row = db.get(WeatherCacheRow, key)
    if row is None:
        db.add(WeatherCacheRow(key=key, data=data, fetched_at=now))
    else:
        row.data, row.fetched_at = data, now


def event_point(db: Session, event: EventRow) -> tuple[float, float] | None:
    """Forecast point set by the PCO, or the centre of recent positions."""
    s = event_settings.merged(event.settings)
    if s["weather_lat"] is not None and s["weather_lon"] is not None:
        return s["weather_lat"], s["weather_lon"]
    geom = func.ST_GeomFromWKB(func.ST_AsBinary(PositionRow.point))
    row = db.execute(select(func.avg(func.ST_Y(geom)), func.avg(func.ST_X(geom)))
                     .where(PositionRow.event_id == event.id)).first()
    if row and row[0] is not None:
        return float(row[0]), float(row[1])
    return None


def event_department(event: EventRow) -> str:
    return event_settings.merged(event.settings)["department"] or _env("SARCADE_DEPARTMENT")


async def refresh_event(event_id: str, client: httpx.AsyncClient | None = None) -> dict:
    """Fetches forecast and vigilance of an event, stores them, alerts the
    PCO when the vigilance turns orange or red."""
    db = SessionLocal()
    try:
        event = db.get(EventRow, event_id)
        if event is None:
            raise LookupError("event_not_found")
        point = event_point(db, event)
        department = event_department(event)
    finally:
        db.close()
    if point is None:
        raise WeatherUnavailable("no_forecast_point")
    forecast = await fetch_forecast(point[0], point[1], client)
    vigilance = await fetch_vigilance(department, client) if department else None
    now = datetime.now(UTC)
    alert = None
    db = SessionLocal()
    try:
        cache_put(db, f"event:{event_id}", forecast, now)
        if vigilance is not None:
            cache_put(db, f"vigilance:{event_id}", vigilance, now)
            previous = cache_get(db, f"alert:{event_id}")
            previous_color = (previous.data or {}).get("color_id", 1) if previous else 1
            if vg.is_alert(vigilance) and vigilance["color_id"] > previous_color:
                summary = (f"Vigilance {vigilance['color']} Météo-France sur le département {department}"
                           + (f" : {', '.join(vigilance['phenomena'])}" if vigilance["phenomena"] else ""))
                db.add(LogbookRow(event_id=event_id, kind="weather", object_id=None, actor_id="METEO",
                                  summary=summary, time=now))
                alert = {"event_id": event_id, "summary": summary, "vigilance": vigilance}
            cache_put(db, f"alert:{event_id}", {"color_id": vigilance["color_id"]}, now)
        db.commit()
    finally:
        db.close()
    await manager.broadcast(event_id, {"type": "weather.updated", "data": {"fetched_at": forecast["fetched_at"]}})
    if alert:
        await manager.broadcast(event_id, {"type": "weather.alert", "data": alert})
    return forecast


async def refresh_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            ids = [e.id for e in db.scalars(select(EventRow).where(EventRow.ended_at.is_(None)))]
        finally:
            db.close()
        for event_id in ids:
            try:
                await refresh_event(event_id)
            except (WeatherUnavailable, LookupError) as exc:
                log.info("weather not refreshed for %s: %s", event_id, exc)
            except Exception as exc:  # noqa: BLE001 - never crash the server
                log.warning("weather refresh failed for %s: %s", event_id, exc)
        await asyncio.sleep(REFRESH_SECONDS)


def start(tasks: list) -> None:
    if _env("SARCADE_WEATHER", "1").lower() in ("1", "true", "yes"):
        tasks.append(asyncio.create_task(refresh_loop()))
