"""Integration check of APRS: callsign groups, filtering by event, attachment
to a SARCADE operator, deduplication between radio and APRS-IS.

Lines are pushed as the Gateway would do (POST /api/v0.1/aprs/frames).
Usage: SARCADE_URL=http://localhost:8000 python demo/verify_aprs.py
"""
import os
import sys
import uuid

import httpx

BASE = os.getenv("SARCADE_URL", "http://localhost:8000")
API = f"{BASE}/api/v0.1"
c = httpx.Client(timeout=10)


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


suffix = uuid.uuid4().hex[:4].upper()
group = c.post(f"{API}/aprs/groups", json={"actor_id": "ADMIN", "name": f"ADRASEC 78 {suffix}",
                                           "callsigns": ["f4jpo", "F1ABC-9"]}).json()
check(group["callsigns"] == ["F4JPO", "F1ABC-9"], "callsign group created and normalised")
check(c.post(f"{API}/aprs/groups", json={"actor_id": "ADMIN", "name": "x", "callsigns": ["pas valide"]}).status_code == 422,
      "invalid callsign refused")

event = c.post(f"{API}/events", json={"name": "CI APRS", "kind": "exercise"}).json()["id"]
E = f"{API}/events/{event}"
r = c.patch(f"{E}/settings", json={"actor_id": "PCO", "settings": {"aprs_groups": [group["id"]],
                                                                   "aprs_callsigns": ["F5XYZ"]}})
check(r.status_code == 200, "the event follows the group, the PCO adds a callsign")
check(sorted(c.get(f"{E}/aprs/callsigns").json()["callsigns"]) == ["F1ABC-9", "F4JPO", "F5XYZ"],
      "followed callsigns of the event")

c.post(f"{E}/devices/TEL-01/heartbeat", json={"label": "Équipe 1", "callsign": "F4JPO"})


def push(via, *lines):
    return c.post(f"{API}/aprs/frames", json={"via": via, "lines": list(lines)}).json()


tag = suffix.lower()
pos_jpo = f"F4JPO-9>APRS,WIDE1-1:!4848.07N/00208.07E>{tag}"
check(push("rf", pos_jpo)["stored"] == 1, "F4JPO-9 heard on radio is stored (all SSIDs of F4JPO)")
check(push("is", f"F4JPO-9>APRS,TCPIP*,qAC,T2FRANCE:!4848.07N/00208.07E>{tag}")["stored"] == 0,
      "the same packet from APRS-IS is a duplicate")
check(push("rf", f"F1ABC-7>APRS:!4849.00N/00209.00E>{tag}")["stored"] == 0, "F1ABC-7 ignored (only F1ABC-9 selected)")
check(push("is", f"F9ZZZ>APRS:!4849.00N/00209.00E>{tag}")["stored"] == 0, "unselected station neither shown nor stored")
check(push("is", f"F5XYZ>APRS:!4850.00N/00210.00E>{tag}")["stored"] == 1, "callsign added by the PCO is stored")
check(push("rf", "F4JPO-9>APRS::F1ABC    :Bonjour")["stored"] == 0, "non-position packets ignored")

latest = {p["device_id"]: p for p in c.get(f"{E}/positions/latest").json()}
check(set(latest) == {"TEL-01", "aprs:F5XYZ"}, "only selected stations have positions")
check(latest["TEL-01"]["source"] == "aprs", "F4JPO's APRS position attaches to his SARCADE device")
devices = {d["device_id"]: d for d in c.get(f"{E}/devices").json()}
check(devices["TEL-01"]["callsign"] == "F4JPO" and devices["TEL-01"]["last_position_at"],
      "the device shows its callsign and last position")

c.post(f"{E}/close", json={"actor_id": "PCO"})
check(push("rf", f"F4JPO-9>APRS:!4851.00N/00211.00E>{tag}x")["stored"] == 0, "closed events stop following APRS")

status = c.get(f"{API}/aprs/status").json()
check("aprs_is" in status and "radio" in status, "link status available")
c.delete(f"{API}/aprs/groups/{group['id']}")
print("aprs: all checks passed")
