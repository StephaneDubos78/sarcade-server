"""Stand-in for Open-Meteo and the Météo-France vigilance, for the demo stack
and the CI (no Internet). Serves plausible data around the current time."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from urllib.parse import urlparse


def forecast(path):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    n = 96
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]
    hourly = {"time": times, "temperature_2m": [9 + (i % 24) / 3 for i in range(n)],
              "apparent_temperature": [7.0] * n, "precipitation": [0.2] * n,
              "wind_speed_10m": [18.0] * n, "wind_gusts_10m": [55.0] * n,
              "wind_direction_10m": [240] * n, "weather_code": [95 if 14 <= i % 24 <= 17 else 3 for i in range(n)],
              "cloud_cover": [75] * n}
    if path == "/v1/forecast":
        hourly["precipitation_probability"] = [40] * n
        hourly["visibility"] = [12000] * n
    days = [(start + timedelta(days=d)) for d in range(4)]
    return {"latitude": 48.8, "longitude": 2.1, "elevation": 110.0, "hourly": hourly,
            "daily": {"time": [d.strftime("%Y-%m-%d") for d in days],
                      "sunrise": [(d + timedelta(hours=6, minutes=5)).strftime("%Y-%m-%dT%H:%M") for d in days],
                      "sunset": [(d + timedelta(hours=17, minutes=10)).strftime("%Y-%m-%dT%H:%M") for d in days]}}


VIGILANCE = {"product": {"periods": [{"echeance": "J", "timelaps": {"domain_ids": [
    {"domain_id": "78", "max_color_id": 3, "phenomenon_items": [
        {"phenomenon_id": "3", "phenomenon_max_color_id": 3}]},
    {"domain_id": "92", "max_color_id": 1, "phenomenon_items": []}]}}]}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/v1/meteofrance", "/v1/forecast"):
            body = forecast(path)
        elif path == "/vigilance" and self.headers.get("apikey"):
            body = VIGILANCE
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Handler).serve_forever()
