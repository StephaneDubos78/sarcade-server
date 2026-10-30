"""Integration check of the server block of « Paramètres › Diagnostic »
(lot 5): state, components, resources read from /proc in the container.

Usage: SARCADE_URL=http://localhost:8000 python demo/verify_diagnostics.py
"""
import os
import sys

import httpx

BASE = os.getenv("SARCADE_URL", "http://localhost:8000")
API = f"{BASE}/api/v0.1"
c = httpx.Client(timeout=30)


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok   {msg}")


r = c.get(f"{API}/diagnostics/server")
check(r.status_code == 200, "diagnostics answer (local network, no Access)")
d = r.json()
check(d["status"] in ("ok", "degraded", "down"), f"general state: {d['status']}")
check(d["components"]["database"] == "green", "database green")
check(set(d["components"]) >= {"realtime", "tunnel", "wakeup", "aprs", "weather"}, "every component listed")
check(d["uptime_s"] >= 0 and d["version"], "version and uptime")
res = d["resources"]
check(res["memory"] and 0 < res["memory"]["pct"] <= 100, "memory read from /proc/meminfo")
check(res["disk"] and res["disk"]["total_gb"] > 0, "disk seen from the container")
check(res["cpu_pct"] is None or 0 <= res["cpu_pct"] <= 100, "processor from /proc/stat")
cl = c.get(f"{API}/diagnostics/client").json()
check(cl["ip"] and cl["via_cloudflare"] is False, f"client address seen by the server: {cl['ip']}")
print("diagnostics: all checks passed")
