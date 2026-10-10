"""Network links: APRS-IS (Internet) and KISS TCP modem (local radio).

Configuration (environment):

* ``SARCADE_APRS_IS=1`` enables APRS-IS; ``SARCADE_APRS_IS_HOST`` /
  ``SARCADE_APRS_IS_PORT`` (default ``rotate.aprs2.net:14580``). The login is
  read-only (passcode -1): the server never sends to APRS-IS.
* ``SARCADE_KISS_HOST`` / ``SARCADE_KISS_PORT`` (default port 8001) enable
  the radio link to a software modem such as Dire Wolf.
* ``SARCADE_APRS_CALLSIGN``: ADRASEC callsign, required to transmit on radio.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import os

from sarcade.db.session import SessionLocal
from sarcade.realtime.manager import manager

from . import callsigns as calls
from . import kiss
from .service import all_followed_callsigns, ingest, runtime, server_callsign

log = logging.getLogger("sarcade.aprs")


def _store(line: str, via: str):
    db = SessionLocal()
    try:
        results = ingest(db, line, via, datetime.now(UTC), runtime.dedup)
        db.commit()
        return results
    finally:
        db.close()


async def handle_line(line: str, via: str) -> int:
    """Ingests one TNC2 line and broadcasts the stored positions."""
    status = runtime.aprs_is if via == "is" else runtime.radio
    status.packets += 1
    status.last_packet_at = datetime.now(UTC)
    results = await asyncio.to_thread(_store, line, via)
    runtime.stored += len(results)
    for event_id, position in results:
        await manager.broadcast(event_id, {"type": "position.updated", "data": position})
    return len(results)


def _current_filter() -> str:
    db = SessionLocal()
    try:
        return calls.budlist_filter(all_followed_callsigns(db))
    finally:
        db.close()


async def aprs_is_loop() -> None:
    host = os.getenv("SARCADE_APRS_IS_HOST", "rotate.aprs2.net")
    port = int(os.getenv("SARCADE_APRS_IS_PORT", "14580"))
    login = server_callsign() or "N0CALL"
    runtime.aprs_is.enabled = True
    backoff = 5
    while True:
        try:
            current = await asyncio.to_thread(_current_filter)
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(f"user {login} pass -1 vers SARCADE 0.1 filter {current}\r\n".encode())
            await writer.drain()
            runtime.aprs_is.connected, runtime.aprs_is.detail = True, f"{host}:{port}"
            runtime.filter = current
            backoff = 5
            loop = asyncio.get_running_loop()
            next_check = loop.time() + 60
            while True:
                raw = await asyncio.wait_for(reader.readline(), timeout=90)
                if not raw:
                    raise ConnectionError("closed")
                if loop.time() >= next_check:
                    next_check = loop.time() + 60
                    wanted = await asyncio.to_thread(_current_filter)
                    if wanted != current:
                        writer.write(f"#filter {wanted}\r\n".encode())
                        await writer.drain()
                        current = runtime.filter = wanted
                line = raw.decode("utf-8", "replace").strip()
                if line and not line.startswith("#"):
                    await handle_line(line, "is")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep retrying, never crash the server
            runtime.aprs_is.connected, runtime.aprs_is.detail = False, str(exc) or type(exc).__name__
            log.warning("APRS-IS link down: %s", runtime.aprs_is.detail)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)


async def kiss_loop() -> None:
    host = os.getenv("SARCADE_KISS_HOST", "")
    port = int(os.getenv("SARCADE_KISS_PORT", "8001"))
    runtime.radio.enabled = True
    runtime.tx_queue = asyncio.Queue(maxsize=100)
    backoff = 5
    while True:
        writer_task = None
        try:
            reader, writer = await asyncio.open_connection(host, port)
            runtime.radio.connected, runtime.radio.detail = True, f"{host}:{port}"
            backoff = 5

            async def send_frames():
                while True:
                    frame = await runtime.tx_queue.get()
                    writer.write(frame)
                    await writer.drain()

            writer_task = asyncio.create_task(send_frames())
            decoder = kiss.KissDecoder()
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    raise ConnectionError("closed")
                for frame in decoder.feed(chunk):
                    try:
                        line = kiss.ax25_to_tnc2(frame)
                    except kiss.InvalidFrame:
                        continue
                    await handle_line(line, "rf")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            runtime.radio.connected, runtime.radio.detail = False, str(exc) or type(exc).__name__
            log.warning("APRS radio link down: %s", runtime.radio.detail)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
        finally:
            if writer_task is not None:
                writer_task.cancel()


def start(loop_tasks: list) -> None:
    """Starts the configured links (called at server startup)."""
    if os.getenv("SARCADE_APRS_IS", "").lower() in ("1", "true", "yes"):
        loop_tasks.append(asyncio.create_task(aprs_is_loop()))
    if os.getenv("SARCADE_KISS_HOST"):
        loop_tasks.append(asyncio.create_task(kiss_loop()))
