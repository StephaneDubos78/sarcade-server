"""Firebase Cloud Messaging, HTTP v1 API, with the service account placed
by the operator (SARCADE_FCM_SERVICE_ACCOUNT: path of the JSON file)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import jwt

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def load_account() -> dict | None:
    """Service account, or None when not configured (Android not woken)."""
    value = (os.getenv("SARCADE_FCM_SERVICE_ACCOUNT") or "").strip()
    if not value:
        return None
    try:
        text = value if value.startswith("{") else Path(value).read_text(encoding="utf-8")
        account = json.loads(text)
        for field in ("client_email", "private_key", "project_id"):
            if not account.get(field):
                return None
        return account
    except (OSError, ValueError):
        return None


class AccessToken:
    def __init__(self):
        self.value: str | None = None
        self.expires = 0.0

    async def get(self, client: httpx.AsyncClient, account: dict) -> str:
        if self.value and time.time() < self.expires - 120:
            return self.value
        now = int(time.time())
        token_uri = account.get("token_uri") or "https://oauth2.googleapis.com/token"
        assertion = jwt.encode({"iss": account["client_email"], "scope": SCOPE, "aud": token_uri,
                                "iat": now, "exp": now + 3600}, account["private_key"], algorithm="RS256")
        r = await client.post(token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                               "assertion": assertion}, timeout=15)
        r.raise_for_status()
        body = r.json()
        self.value = body["access_token"]
        self.expires = time.time() + float(body.get("expires_in", 3600))
        return self.value


def message(token: str, data: dict[str, str], high: bool) -> dict:
    """Data message only (no notification block): the application decides
    what to show after its synchronisation."""
    return {"message": {"token": token, "data": data,
                        "android": {"priority": "high" if high else "normal", "ttl": "3600s"}}}


def is_gone(status: int, body: str) -> bool:
    """Token no longer valid: removed from the server."""
    return status == 404 or (status == 400 and "UNREGISTERED" in body) or "registration-token-not-registered" in body
