"""Integration check of the TV screen, lot 4 (30 Oct 2026): pairing with the
public address noted, codes of the same network offered to PCO only (none
without a checked email), messages column of one screen at once, view with
the opacity per layer and its sender, probable zone and crossings computed
by the server, colours of the beacons, default view.

Usage: SARCADE_URL=http://localhost:8000 python demo/verify_tv.py
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx

BASE = os.getenv("SARCADE_URL", "http://localhost:8000")
API = f"{BASE}/api/v0.1"
c = httpx.Client(timeout=10)
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def check(cond, msg):
    if not cond:
        print(f"::error::FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


event = c.post(f"{API}/events", json={"name": "CI TV", "kind": "exercise"}).json()["id"]
E = f"{API}/events/{event}"
IP = {"cf-connecting-ip": "203.0.113.7"}

p = c.post(f"{API}/tv/pair", headers=IP).json()
check(len(p["code"]) == 6, "the TV gets a code")
check(c.get(f"{API}/tv/nearby", headers=IP).json() == [], "same network: nothing offered without a checked PCO email")
check(c.post(f"{API}/tv/approve", json={"code": p["code"], "event_id": event}).status_code == 200, "code approved")
token = c.get(f"{API}/tv/pair/{p['pair_id']}").json()["token"]
TV = {"authorization": f"Display {token}"}
[d] = c.get(f"{E}/displays").json()
check(d["messages"] is True and d["revoked"] is False, "screen listed, messages shown by default")

# Three bearings of the exercise beacon crossing near (48.80, 2.10).
for lat, lon, az in ((48.75, 2.10, 0), (48.80, 2.03, 90), (48.75, 2.04, 38)):
    fid = str(uuid.uuid4())
    r = c.post(f"{API}/sync", json=[{"operation_id": str(uuid.uuid4()), "event_id": event, "object_id": fid,
                                      "object_type": "map_feature", "action": "create", "client_time": NOW,
                                      "payload": {"id": fid, "event_id": event, "kind": "bearing", "points": [[lat, lon]],
                                                  "color": 0, "stroke_width": 2, "label": "121,375 MHz · Exercice",
                                                  "created_by": "TEL-01", "updated_by": "TEL-01", "updated_at": NOW,
                                                  "bearing": {"azimuth_deg": az, "length_m": 10000, "cone_deg": 5,
                                                              "search": "121,375 MHz · Exercice", "exercise": True}}}])
    check(r.status_code == 200 and r.json()[0]["status"] == "accepted", f"bearing {az}° accepted")

s = c.get(f"{API}/tv/state", headers=TV).json()
check(len(s["bearings"]) == 3 and all(b["color"] == "#1E88E5" and b["cone_deg"] == 5 for b in s["bearings"]),
      "bearings in the colour of the exercise beacon, with their cone")
[z] = s["zones"]
check(len(z["crossings"]) == 3 and abs(z["lat"] - 48.80) < 0.01 and z["label"].endswith("3 relevés"),
      "probable zone computed by the server")
check(s["view"] is None and s["default_base"]["tile_url"].startswith("https://"), "default view: base map of the event")

check(c.put(f"{E}/displays/{d['id']}/messages", json={"messages": False}).status_code == 200, "messages hidden on the screen")
check(c.get(f"{API}/tv/state", headers=TV).json()["options"]["messages"] is False, "applied at once, without a view")

view = {"lat": 48.8, "lon": 2.1, "zoom": 13, "from": "PCO-Web", "messages": True,
        "layers": {"bearings": True}, "opacity": {"aprs": 0.4, "high": 0.3, "relay": 0.6, "brg": 0.5}}
check(c.put(f"{E}/displays/{d['id']}/view", json={"view": view}).status_code == 200, "view sent")
s = c.get(f"{API}/tv/state", headers=TV).json()
check(s["view"]["from"] == "PCO-Web" and s["options"]["opacity"]["aprs"] == 0.4 and s["options"]["opacity"]["relay"] == 0.6,
      "view with its sender and one opacity per layer")
check(s["options"]["messages"] is True, "the view carries the messages column")
view["layers"] = {"bearings": False}
c.put(f"{E}/displays/{d['id']}/view", json={"view": view})
check(c.get(f"{API}/tv/state", headers=TV).json()["zones"] == [], "zone follows the bearings layer")
check(c.put(f"{E}/displays/{d['id']}/view", json={"view": None}).json() == {"view": None}, "back to the default view")
page = c.get(f"{BASE}/tv").text
check("Outils › Afficher sur une TV" in page and 'id="legend"' in page, "TV page: new instructions and legend")
print("TV lot 4 verified")
