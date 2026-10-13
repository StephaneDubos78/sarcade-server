"""Integration check of map feature synchronisation (ADR-001).

Runs against a live server: create, retransmission, newer and stale updates,
change feed, delete, undo of a delete, invalid payloads, GeoJSON and logbook.
Usage: SARCADE_URL=http://localhost:8000 python demo/verify_map_features.py
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE = os.getenv("SARCADE_URL", "http://localhost:8000")
c = httpx.Client(timeout=10)
T0 = datetime.now(timezone.utc).replace(microsecond=0)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


event = c.post(f"{BASE}/api/v0.1/events", json={"name": "CI objets", "kind": "exercise"}).json()["id"]
fid = str(uuid.uuid4())


def feature(at, by="TERRAIN-01", **kw):
    f = {"id": fid, "event_id": event, "kind": "zone",
         "points": [[48.70, 2.00], [48.71, 2.00], [48.71, 2.01]],
         "radius_m": None, "color": 0xFFE53935, "stroke_width": 4, "label": "Secteur A",
         "created_by": "TERRAIN-01", "updated_by": by, "updated_at": iso(at)}
    f.update(kw)
    return f


def op(action, payload, opid=None):
    return {"operation_id": opid or str(uuid.uuid4()), "event_id": event, "object_id": fid,
            "object_type": "map_feature", "action": action, "client_time": iso(T0), "payload": payload}


def sync(*ops):
    r = c.post(f"{BASE}/api/v0.1/sync", json=list(ops))
    r.raise_for_status()
    return [x["status"] for x in r.json()]


def listing(**params):
    r = c.get(f"{BASE}/api/v0.1/events/{event}/map-features", params=params)
    r.raise_for_status()
    return r.json()


create = op("create", feature(T0))
check(sync(create) == ["accepted"], "creation accepted")
check(sync(create) == ["duplicate"], "retransmission is a duplicate")
check(len(listing()) == 1 and listing()[0]["revision"] == 1, "one feature, revision 1")

newer = op("update", feature(T0 + timedelta(seconds=30), by="PCO", label="Secteur A Nord", color=0xFF1E88E5))
stale = op("update", feature(T0 + timedelta(seconds=10), by="TERRAIN-02", label="Ancienne version"))
check(sync(newer, stale) == ["accepted", "conflict"], "newer update wins, stale one is a conflict")
f = listing()[0]
check(f["label"] == "Secteur A Nord" and f["updated_by"] == "PCO" and f["revision"] == 2, "stored state is the newest")

feed = c.get(f"{BASE}/api/v0.1/events/{event}/sync/changes", params={"after": 0}).json()["changes"]
labels = [ch["payload"].get("label") for ch in feed if ch["object_type"] == "map_feature"]
check(labels == ["Secteur A", "Secteur A Nord"], "change feed holds accepted states only, in order")
check(all("revision" in ch["payload"] for ch in feed), "feed payload is the server state")

delete = op("delete", {"id": fid, "event_id": event, "updated_by": "PCO", "updated_at": iso(T0 + timedelta(seconds=60))})
check(sync(delete) == ["accepted"], "delete accepted")
check(listing() == [], "deleted feature is hidden")
check(listing(include_deleted=True)[0]["deleted"] is True, "tombstone kept")

late = op("update", feature(T0 + timedelta(seconds=45), by="TERRAIN-02", label="Trop tard"))
check(sync(late) == ["conflict"], "edit older than the delete does not resurrect")
undo = op("update", feature(T0 + timedelta(seconds=90), by="PCO", label="Secteur A Nord"))
check(sync(undo) == ["accepted"], "newer change after delete (undo) accepted")
check(len(listing()) == 1, "feature restored")

# A device two days ahead would win every conflict for two days. Its time is
# clamped to the server clock, older than the last edit (T0+90 s), so it loses,
# and a correct device editing later still wins.
future = op("update", feature(T0 + timedelta(days=2), by="TERRAIN-03", label="Horloge fausse"))
check(sync(future) == ["conflict"], "far-future clock clamped, cannot override a newer edit")
later = op("update", feature(T0 + timedelta(seconds=120), by="TERRAIN-01", label="Secteur A Nord"))
check(sync(later) == ["accepted"], "correct device still wins afterwards")

bad = op("create", feature(T0, kind="zone", points=[[48.7, 2.0]]), opid=str(uuid.uuid4()))
check(sync(bad) == ["rejected"], "invalid geometry rejected")
other = dict(op("create", feature(T0)), event_id="unknown-event")
check(sync(other) == ["rejected"], "unknown event rejected")

gj = c.get(f"{BASE}/api/v0.1/events/{event}/map-features.geojson")
gj.raise_for_status()
geo = gj.json()
coords = geo["features"][0]["geometry"]["coordinates"][0]
check(gj.headers["content-type"].startswith("application/geo+json"), "GeoJSON media type")
check(coords[0] == [2.0, 48.7] and coords[0] == coords[-1], "GeoJSON polygon closed, lon/lat order")

log = [x["summary"] for x in c.get(f"{BASE}/api/v0.1/events/{event}/logbook").json() if x["kind"] == "map_feature"]
check(log == ["Objet cartographique créé : Zone « Secteur A »",
              "Objet cartographique supprimé : Zone « Secteur A Nord »",
              "Objet cartographique restauré : Zone « Secteur A Nord »"], "logbook: create, delete, restore")

print("PASS: map feature synchronisation follows ADR-001")
