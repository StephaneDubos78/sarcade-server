"""Integration check of event operations: PCO settings, device last contact,
position battery and source, end of event.

Usage: SARCADE_URL=http://localhost:8000 python demo/verify_event_operations.py
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx

BASE = os.getenv("SARCADE_URL", "http://localhost:8000")
c = httpx.Client(timeout=10)


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


event = c.post(f"{BASE}/api/v0.1/events", json={"name": "CI opérations", "kind": "exercise"}).json()["id"]
E = f"{BASE}/api/v0.1/events/{event}"

ev = c.get(E).json()
check(ev["settings"]["low_bandwidth"] is False and ev["settings"]["tracking_default_interval_s"] == 30,
      "default settings exposed on the event")

r = c.patch(f"{E}/settings", json={"actor_id": "PCO", "settings": {"low_bandwidth": True, "tracking_required": True,
                                                                   "tracking_min_interval_s": 30}})
check(r.status_code == 200 and r.json()["settings"]["low_bandwidth"] is True, "PCO imposes low-bandwidth mode")
r = c.patch(f"{E}/settings", json={"actor_id": "PCO", "settings": {"tracking_default_interval_s": 45}})
check(r.status_code == 422, "invalid interval rejected")

hb = c.post(f"{E}/devices/TEL-01/heartbeat", json={"label": "Équipe 1", "platform": "android",
            "battery_pct": 80, "pending_count": 3, "tracking_enabled": True, "tracking_interval_s": 10})
check(hb.status_code == 200, "heartbeat accepted")
body = hb.json()
check(body["settings"]["low_bandwidth"] is True and body["tracking_required"] is True,
      "heartbeat returns the settings to apply")
check(body["tracking_interval_s"] == 30, "tracking interval clamped to the PCO minimum")

pid = str(uuid.uuid4())
now = datetime.now(timezone.utc)
r = c.post(f"{BASE}/api/v0.1/sync", json=[{
    "operation_id": str(uuid.uuid4()), "event_id": event, "object_id": pid, "object_type": "position",
    "action": "create", "client_time": iso(now),
    "payload": {"id": pid, "event_id": event, "device_id": "TEL-02", "lat": 48.8, "lon": 2.1,
                "time": iso(now), "battery_pct": 42}}])
check(r.json()[0]["status"] == "accepted", "position with battery level synchronised")
latest = {p["device_id"]: p for p in c.get(f"{E}/positions/latest").json()}
check(latest["TEL-02"]["battery_pct"] == 42 and latest["TEL-02"]["source"] == "device",
      "battery level and source kept on the position")

devices = {d["device_id"]: d for d in c.get(f"{E}/devices").json()}
check(set(devices) == {"TEL-01", "TEL-02"}, "both devices listed for the PCO")
check(devices["TEL-01"]["pending_count"] == 3 and devices["TEL-01"]["status"] == "ok",
      "pending items and status reported")
check(devices["TEL-02"]["last_position_at"] is not None and devices["TEL-02"]["battery_pct"] == 42,
      "position updates the device last contact")

closed = c.post(f"{E}/close", json={"actor_id": "PCO"}).json()
check(closed["status"] == "closed" and closed["ended_at"], "event closed")
again = c.post(f"{E}/close", json={"actor_id": "PCO"}).json()
check(again["ended_at"] == closed["ended_at"], "closing twice keeps the first end time")
hb = c.post(f"{E}/devices/TEL-01/heartbeat", json={"tracking_enabled": True}).json()
check(hb["ended_at"] and hb["tracking_required"] is False, "devices learn the end of the event")
r = c.patch(f"{E}/settings", json={"actor_id": "PCO", "settings": {"low_bandwidth": False}})
check(r.status_code == 409, "settings frozen after the end of the event")

log = [x["summary"] for x in c.get(f"{E}/logbook").json()]
for line in ("Mode liaison faible activé par le PCO", "Suivi de position imposé par le PCO", "Fin de l'événement"):
    check(line in log, f"logbook: {line}")
print("event operations: all checks passed")
