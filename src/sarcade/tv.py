"""Display on a Smart TV or a big screen (« Affichage sur Smart TV et grand
écran », validated on 29 Oct 2026). The TV opens tv.sarcade.org (no
Cloudflare Access: a TV cannot sign in), shows a short code and a QR code;
a PCO approves it from a phone for an event; the TV then receives a token
that only reads that event. Pure logic and small stores, testable alone."""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field

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

    def approve(self, code: str, event_id: str, now: float | None = None) -> Pairing | None:
        now = now or time.time()
        self._purge(now)
        pid = self.by_code.get(code.strip().upper().replace(" ", ""))
        p = self.pairings.get(pid) if pid else None
        if p is None or p.token is not None:
            return None
        p.event_id, p.token = event_id, secrets.token_urlsafe(32)
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


# Logbook lines never shown on a TV: acknowledgements are technical traces
# (« received: <id> »), and message lines would repeat the messages panel
# and could reveal direct chats or channels. Device versions and contact
# lines are technical, for the PCO only.
TV_HIDDEN_LOG_KINDS = frozenset({"ack", "message", "device_version", "contact"})


def snapshot(event: dict, positions: list[dict], messages: list[dict], logbook: list[dict]) -> dict:
    """What a TV may show: positions, the general messages only (never the
    direct chats or channels), the last operational logbook lines."""
    public = [m for m in messages if not m.get("recipient_ids")]
    log = [{k: v for k, v in r.items() if k != "kind"} for r in logbook
           if r.get("kind") not in TV_HIDDEN_LOG_KINDS]
    return {"event": {"id": event["id"], "name": event.get("name", "")},
            "positions": positions, "messages": public[-12:], "logbook": log[-12:]}


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
            "rev": int((now if now is not None else time.time()) * 1000)}

