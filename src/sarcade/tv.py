"""Display on a Smart TV or a big screen (« Affichage sur Smart TV et grand
écran », validated on 29 Oct 2026). The TV opens tv.sarcade.org (no
Cloudflare Access: a TV cannot sign in), shows a short code and a QR code;
a PCO approves it from a phone for an event; the TV then receives a token
that only reads that event. Pure logic and small stores, testable alone."""
from __future__ import annotations

import hashlib
import math
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
CODE_TTL_S = 600
TOKEN_TTL_S = 24 * 3600
MAX_PENDING = 200
REQUESTS_PER_MINUTE = 10


@dataclass
class Pairing:
    pair_id: str
    code: str
    created: float
    event_id: str | None = None
    token: str | None = None
    approved_by: str | None = None


@dataclass
class Store:
    pairings: dict[str, Pairing] = field(default_factory=dict)
    by_code: dict[str, str] = field(default_factory=dict)
    hits: dict[str, list[float]] = field(default_factory=dict)

    def allowed(self, client: str, now: float | None = None) -> bool:
        """At most REQUESTS_PER_MINUTE codes per minute and client address."""
        now = now or time.time()
        recent = [t for t in self.hits.get(client, []) if now - t < 60]
        if len(recent) >= REQUESTS_PER_MINUTE:
            self.hits[client] = recent
            return False
        self.hits[client] = [*recent, now]
        return True

    def _purge(self, now: float) -> None:
        for pid, p in list(self.pairings.items()):
            if now - p.created > CODE_TTL_S:
                self.pairings.pop(pid, None)
                self.by_code.pop(p.code, None)

    def new(self, now: float | None = None) -> Pairing:
        now = now or time.time()
        self._purge(now)
        if len(self.pairings) >= MAX_PENDING:
            raise OverflowError("too_many_pairings")
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        while code in self.by_code:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        p = Pairing(pair_id=secrets.token_urlsafe(18), code=code, created=now)
        self.pairings[p.pair_id] = p
        self.by_code[code] = p.pair_id
        return p

    def approve(self, code: str, event_id: str, now: float | None = None,
                approved_by: str | None = None) -> Pairing | None:
        now = now or time.time()
        self._purge(now)
        pid = self.by_code.get(code.strip().upper().replace(" ", ""))
        p = self.pairings.get(pid) if pid else None
        if p is None or p.token is not None:
            return None
        p.event_id, p.token, p.approved_by = event_id, secrets.token_urlsafe(32), approved_by
        return p

    def status(self, pair_id: str, now: float | None = None) -> Pairing | None:
        self._purge(now or time.time())
        return self.pairings.get(pair_id)


store = Store()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def valid_display(displays: list[dict], token: str, now: float | None = None) -> dict | None:
    """The display of this token: not revoked, not expired."""
    now = now or time.time()
    h = token_hash(token)
    for d in displays:
        if d.get("hash") == h and not d.get("revoked") and d.get("expires", 0) > now:
            return d
    return None


def snapshot(event: dict, positions: list[dict], messages: list[dict]) -> dict:
    """What a TV may show: positions and the general messages only (never
    the direct chats or channels). The logbook is no longer shown on the TV
    (decision of the porteur, 29 Oct 2026)."""
    public = [m for m in messages if not m.get("recipient_ids")]
    return {"event": {"id": event["id"], "name": event.get("name", "")},
            "positions": positions, "messages": public[-12:]}


# --- SOS banner (29 Oct 2026) -----------------------------------------------
# The app sends « 🆘 DÉTRESSE — <who> — position … » (immediate) and
# « Fin de détresse — <who> » (urgent), see distress.body / distress.endBody.

ALERT_WINDOW = timedelta(minutes=10)
END_PREFIXES = ("fin de détresse", "end of distress")


def is_distress(m: dict) -> bool:
    return m.get("priority") == "immediate" and str(m.get("body") or "").lstrip().startswith("🆘")


def is_distress_end(m: dict) -> bool:
    return str(m.get("body") or "").strip().lower().startswith(END_PREFIXES)


def open_distress(messages: list[dict]) -> dict[str, dict]:
    """Distress not closed yet, by sender: the last « 🆘 » message of a sender
    not followed by a « Fin de détresse » of the same sender. General
    messages only, in chronological order."""
    out: dict[str, dict] = {}
    for m in sorted((m for m in messages if not m.get("recipient_ids")),
                    key=lambda m: _time(m.get("created_at")) or datetime.min.replace(tzinfo=UTC)):
        who = m.get("sender_id")
        if is_distress(m):
            out[who] = m
        elif is_distress_end(m):
            out.pop(who, None)
    return out


def alert_state(messages: list[dict], now: datetime, cleared_at: float | None = None) -> dict:
    """Red banner of a TV and the small SOS reminder of its top bar.

    - ``alert``: the last general immediate message of the last 10 minutes,
      unless it was cleared on this screen (``cleared_at``, epoch seconds)
      or it is a distress already closed by a « Fin de détresse » ;
    - ``sos``: senders whose distress is not closed (kept after a clear)."""
    public = [m for m in messages if not m.get("recipient_ids")]
    still = open_distress(public)
    alert = None
    for m in public:
        t = _time(m.get("created_at"))
        if m.get("priority") != "immediate" or t is None or now - t > ALERT_WINDOW:
            continue
        if cleared_at is not None and t.timestamp() <= cleared_at:
            continue
        if is_distress(m) and still.get(m.get("sender_id")) is not m:
            continue
        if alert is None or t >= _time(alert.get("created_at")):
            alert = m
    return {"alert": {k: alert.get(k) for k in ("sender_id", "body", "created_at")} if alert else None,
            "sos": sorted(still)}


def clean_view(view: dict | None, now: float | None = None) -> dict | None:
    """View copied from a phone: centre, zoom, base map. The tile address is
    used by the public TV page, so only an https template is accepted."""
    if view is None:
        return None
    if not isinstance(view, dict):
        raise ValueError("invalid_view")

    def num(key, lo, hi):
        v = view.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError(f"invalid_{key}")
        return float(v)

    def text(key, maximum):
        v = view.get(key) or ""
        if not isinstance(v, str) or len(v) > maximum:
            raise ValueError(f"invalid_{key}")
        return v.strip()

    url = text("tile_url", 300) or None
    if url is not None and not (url.startswith("https://") and all(t in url for t in ("{z}", "{x}", "{y}"))
                                and not any(ch in url for ch in "\"'<> ")):
        raise ValueError("invalid_tile_url")
    return {"lat": num("lat", -90, 90), "lon": num("lon", -180, 180), "zoom": round(num("zoom", 1, 20), 2),
            "basemap": text("basemap", 40), "tile_url": url, "attribution": text("attribution", 200),
            **clean_display_options(view),
            "rev": int((now if now is not None else time.time()) * 1000)}



# --- « Envoyer ma vue », step 2: layers, opacities, messages panel --------

DEFAULT_LAYERS = {"operators": True, "aprs": True, "offline": True, "drawings": True, "bearings": True,
                  "highpoints": False, "relays": False}
DEFAULT_OPACITY = {"ops": 1.0, "draw": 1.0, "brg": 1.0, "ref": 1.0}
# Same threshold as the « opérateurs actifs » counter of the TV page.
OFFLINE_AFTER = timedelta(minutes=10)


def clean_display_options(view: dict) -> dict:
    """Layers, opacities and messages panel of a view; unknown keys are
    dropped, missing keys take the defaults."""
    layers = view.get("layers")
    if layers is None:
        layers = {}
    if not isinstance(layers, dict):
        raise ValueError("invalid_layers")
    out_layers = {}
    for key, default in DEFAULT_LAYERS.items():
        v = layers.get(key, default)
        if not isinstance(v, bool):
            raise ValueError("invalid_layers")
        out_layers[key] = v
    opacity = view.get("opacity")
    if opacity is None:
        opacity = {}
    if not isinstance(opacity, dict):
        raise ValueError("invalid_opacity")
    out_opacity = {}
    for key, default in DEFAULT_OPACITY.items():
        v = opacity.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0.1 <= v <= 1:
            raise ValueError("invalid_opacity")
        out_opacity[key] = round(float(v), 2)
    messages = view.get("messages", True)
    if not isinstance(messages, bool):
        raise ValueError("invalid_messages")
    return {"layers": out_layers, "opacity": out_opacity, "messages": messages}


def display_options(view: dict | None) -> dict:
    """Options of a stored view (or the defaults: automatic framing, or a
    view stored before step 2)."""
    try:
        return clean_display_options(view or {})
    except ValueError:
        return clean_display_options({})


def _time(value) -> datetime | None:
    if isinstance(value, datetime):
        t = value
    elif isinstance(value, str):
        try:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t


def apply_view(snap: dict, view: dict | None, now: datetime, *, weather: dict | None = None,
               drawings: list | None = None, bearings: list | None = None,
               references: list | None = None) -> dict:
    """Keeps in the snapshot only what the layers of the view show."""
    opts = display_options(view)
    layers = opts["layers"]

    def shown(p: dict) -> bool:
        if p.get("source") == "aprs":
            return layers["aprs"]
        if not layers["operators"]:
            return False
        t = _time(p.get("time"))
        return layers["offline"] or (t is not None and now - t <= OFFLINE_AFTER)

    out = dict(snap)
    out["positions"] = [p for p in snap.get("positions", []) if shown(p)]
    # « messages » only hides the panel: the immediate-message banner stays.
    out["options"] = opts
    out["weather"] = weather
    if drawings is not None:
        out["drawings"] = drawings if layers["drawings"] else []
    if bearings is not None:
        out["bearings"] = bearings if layers["bearings"] else []
    if references is not None:
        out["references"] = [r for r in references
                             if (r.get("category") == "HIGH_POINT" and layers["highpoints"])
                             or (r.get("category") == "RELAY" and layers["relays"])]
    return out


# Colours of the searches (bearings), stable for a given search name.
SEARCH_COLORS = ("#ff4d5e", "#3dd6f5", "#ffb020", "#3ddc84", "#c77dff", "#ff8c1a", "#4d8dff", "#f06bc4")


def search_color(search: str) -> str:
    if not search:
        return SEARCH_COLORS[0]
    return SEARCH_COLORS[int(hashlib.sha1(search.encode()).hexdigest(), 16) % len(SEARCH_COLORS)]


def tv_drawing(feature: dict) -> dict:
    """Map feature as drawn by the TV (no author, no history)."""
    keep = ("id", "kind", "points", "radius_m", "color", "stroke_width", "label", "opacity")
    return {k: feature.get(k) for k in keep if feature.get(k) is not None}


def tv_bearing(feature: dict) -> dict | None:
    b = feature.get("bearing") or {}
    points = feature.get("points") or []
    if not points or b.get("azimuth_deg") is None:
        return None
    search = b.get("search") or ""
    return {"id": feature.get("id"), "lat": points[0][0], "lon": points[0][1],
            "azimuth_deg": b["azimuth_deg"], "length_m": b.get("length_m", 10_000),
            "search": search, "label": feature.get("label") or "", "exercise": bool(b.get("exercise")),
            "color": search_color(search)}


# --- Weather in the top bar -------------------------------------------------

VIGILANCE = {2: "yellow", 3: "orange", 4: "red"}


def _icon(code, cloud, night: bool) -> str:
    code = int(code) if isinstance(code, (int, float)) and not isinstance(code, bool) else None
    if code in (95, 96, 99):
        return "storm"
    if code is not None and (71 <= code <= 77 or code in (85, 86)):
        return "snow"
    if code in (45, 48):
        return "fog"
    if code is not None and (51 <= code <= 67 or 80 <= code <= 82):
        return "rain"
    if code == 3:
        return "cloud"
    if code in (1, 2):
        clear = False
    elif code == 0:
        clear = True
    elif isinstance(cloud, (int, float)):
        if cloud >= 70:
            return "cloud"
        clear = cloud < 25
    else:
        clear = True
    if night:
        return "moon" if clear else "moon_cloud"
    return "sun" if clear else "sun_cloud"


def is_night(forecast: dict, now: datetime) -> bool:
    """Between sunset and sunrise, from the sun times of the forecast."""
    days = []
    for d in forecast.get("daily") or []:
        rise, sset = _time(d.get("sunrise")), _time(d.get("sunset"))
        if rise and sset:
            days.append((rise, sset))
    if not days:
        return False
    return not any(rise <= now < sset for rise, sset in days)


def weather_now(forecast: dict | None, vigilance: dict | None, now: datetime) -> dict | None:
    """Temperature and icon of the current hour, vigilance colour; None
    without a forecast for this hour."""
    if not forecast:
        return None
    hour = now.replace(minute=0, second=0, microsecond=0)
    current = None
    for h in forecast.get("hourly") or []:
        t = _time(h.get("time"))
        if t is not None and hour <= t + timedelta(hours=1) and t <= now and (current is None or t > current[0]):
            current = (t, h)
    if current is None:
        return None
    h = current[1]
    temp = h.get("temperature_c")
    if isinstance(temp, bool) or not isinstance(temp, (int, float)):
        return None
    color = (vigilance or {}).get("color_id")
    out = {"temp_c": round(float(temp), 1), "icon": _icon(h.get("weather_code"), h.get("cloud_cover_pct"), is_night(forecast, now)),
           "vigilance": VIGILANCE.get(color) if isinstance(color, int) else None}
    out.update(sun_times(forecast, now))
    return out


def sun_times(forecast: dict, now: datetime) -> dict:
    """Sunrise and sunset of the day, ISO in UTC (shown in local time by the
    TV, 29 Oct 2026: they replace the weather icon); empty when unknown."""
    days = []
    for d in forecast.get("daily") or []:
        rise, sset = _time(d.get("sunrise")), _time(d.get("sunset"))
        if rise and sset:
            days.append((rise, sset))
    if not days:
        return {}
    rise, sset = min(days, key=lambda d: abs((d[0] - now).total_seconds()))
    return {"sunrise": rise.isoformat(), "sunset": sset.isoformat()}


@dataclass
class WeatherCache:
    """Weather of each event computed at most every 10 minutes: the TV polls
    every 10 s, the forecast changes every hour."""
    ttl_s: float = 600
    entries: dict = field(default_factory=dict)

    def get(self, event_id: str, compute, now: float | None = None):
        now = now if now is not None else time.time()
        hit = self.entries.get(event_id)
        if hit is not None and now - hit[0] < self.ttl_s:
            return hit[1]
        value = compute()
        self.entries[event_id] = (now, value)
        return value


weather_cache = WeatherCache()
