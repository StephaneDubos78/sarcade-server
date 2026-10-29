# SPDX-License-Identifier: AGPL-3.0-only
# © SDUBOS Consulting et contributeurs SARCADE
"""Deletion of a message for everyone (29 Oct 2026)."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sarcade.api import app as app_module
from sarcade.api.app import app
from sarcade.api.deps import get_db
from sarcade.db.base import Base
from sarcade.db.models import (AckRow, CommGroupRow, EventRow, LogbookRow, MessageRow, SecurityEventRow,
                               ServerSettingRow, SharedFileRow, SyncOperationRow)
from sarcade.messages import deletion


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):  # autoincrement keys on SQLite
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[t.__table__ for t in (
        EventRow, LogbookRow, MessageRow, AckRow, SyncOperationRow, SharedFileRow, ServerSettingRow,
        SecurityEventRow, CommGroupRow)])
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    session.add(EventRow(id="e1", name="Exercice", kind="exercise", status="active",
                         created_at=datetime(2026, 10, 29, tzinfo=UTC), version=0))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db, monkeypatch):
    async def _quiet(*a, **k):
        return None
    monkeypatch.setattr(app_module.manager, "broadcast", _quiet)
    monkeypatch.setattr(app_module.security_journal, "record", lambda *a, **k: None)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _iso(t):
    return t.isoformat().replace("+00:00", "Z")


def _send(client, mid, sender="TEL-01", when=None, attachments=None):
    when = when or datetime.now(UTC)
    p = {"id": mid, "event_id": "e1", "sender_id": sender, "recipient_ids": [], "priority": "routine",
         "body": "Véhicule repéré", "created_at": _iso(when), "attachments": attachments or []}
    op = {"operation_id": f"op-{mid}", "event_id": "e1", "object_id": mid, "object_type": "message",
          "action": "create", "client_time": _iso(when), "payload": p}
    return client.post("/api/v0.1/sync", json=[op]).json()[0]


def _delete(client, mid, actor, n=1):
    now = _iso(datetime.now(UTC))
    op = {"operation_id": f"del-{mid}-{n}", "event_id": "e1", "object_id": mid, "object_type": "message",
          "action": "delete", "client_time": now, "payload": {"deleted_by": actor}}
    return client.post("/api/v0.1/sync", json=[op]).json()[0]


def test_rules():
    now = datetime(2026, 10, 29, 12, tzinfo=UTC)
    row = SimpleNamespace(sender_id="TEL-01", created_at=now - timedelta(days=1))
    assert deletion.allowed(row, "TEL-01", False, now) == (True, False)
    assert deletion.allowed(row, "TEL-02", False, now) == (False, False)
    assert deletion.allowed(row, "TEL-02", True, now) == (True, True)
    old = SimpleNamespace(sender_id="TEL-01", created_at=now - timedelta(days=2, minutes=1))
    assert deletion.allowed(old, "TEL-01", False, now) == (False, False)
    assert deletion.allowed(old, "PCO", True, now) == (True, True)


def test_author_deletes_for_everyone(client, db):
    assert _send(client, "m1")["status"] == "accepted"
    assert _delete(client, "m1", "TEL-01")["status"] == "accepted"
    listed = client.get("/api/v0.1/events/e1/messages").json()[0]
    assert listed["deleted"] and listed["body"] == "" and not listed["deleted_by_pco"]
    changes = client.get("/api/v0.1/events/e1/sync/changes").json()["changes"]
    assert [c["action"] for c in changes] == ["create", "delete"]
    assert changes[0]["payload"]["body"] == "" and changes[1]["payload"]["deleted"]
    log = client.get("/api/v0.1/events/e1/logbook").json()
    assert log[0]["summary"] == deletion.DELETED_TEXT and log[-1]["kind"] == "message_deleted"
    # The original stays on the server, for the PCO.
    assert db.get(MessageRow, "m1").body == "Véhicule repéré"
    kept = client.get("/api/v0.1/events/e1/messages/deleted").json()
    assert kept[0]["body"] == "Véhicule repéré" and kept[0]["deleted_by"] == "TEL-01"
    # Deleting again is harmless.
    assert _delete(client, "m1", "TEL-01", 2)["status"] == "conflict"
    assert _delete(client, "m1", "TEL-01")["status"] == "duplicate"


def test_other_operator_and_late_author_are_refused(client):
    _send(client, "m2")
    r = _delete(client, "m2", "TEL-02")
    assert r["status"] == "rejected" and "2 jours" in r["reason"]
    _send(client, "m3", when=datetime.now(UTC) - timedelta(days=3))
    assert _delete(client, "m3", "TEL-01")["status"] == "rejected"
    assert _delete(client, "unknown", "TEL-01")["status"] == "rejected"
    assert not client.get("/api/v0.1/events/e1/messages").json()[0].get("deleted")


def test_pco_deletes_any_message(client):
    _send(client, "m4", when=datetime.now(UTC) - timedelta(days=10))
    assert _delete(client, "m4", "PCO")["status"] == "accepted"
    listed = client.get("/api/v0.1/events/e1/messages").json()[0]
    assert listed["deleted_by_pco"]
    assert client.get("/api/v0.1/events/e1/logbook").json()[0]["summary"] == deletion.DELETED_BY_PCO_TEXT


def test_photos_of_a_deleted_message_are_no_longer_served(client, db, tmp_path):
    path = tmp_path / "f1"
    path.write_bytes(b"jpeg")
    db.add(SharedFileRow(id="f1", event_id="e1", sender_id="TEL-01", name="p.jpg", mime_type="image/jpeg",
                         size_bytes=4, sha256="x", storage_path=str(path), created_at=datetime.now(UTC)))
    db.commit()
    att = [{"file_id": "f1", "name": "p.jpg", "mime_type": "image/jpeg", "size_bytes": 4}]
    _send(client, "m5", attachments=att)
    assert client.get("/api/v0.1/events/e1/files/f1/content").status_code == 200
    _delete(client, "m5", "TEL-01")
    assert client.get("/api/v0.1/events/e1/files/f1/content").status_code == 410
    assert client.get("/api/v0.1/events/e1/messages").json()[0]["attachments"] == []
