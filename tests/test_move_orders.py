"""Move order of the PCO to an operator (decision of 29 Oct 2026)."""
import pytest

from sarcade.features.service import InvalidFeature
from sarcade.routes import service as r

E, OID = "evt-1", "order-1"


def order(**kw):
    p = {"id": OID, "event_id": E, "target_id": "TEL-02", "status": "sent",
         "destination": {"lat": 48.78, "lon": 2.02, "label": "Point haut"}, "note": "Prendre la Yagi",
         "created_by": "PCO", "updated_by": "PCO", "updated_at": "2026-10-29T10:00:00Z"}
    p.update(kw)
    return p


def test_valid_order():
    d = r.validate_move_order(order(), event_id=E, object_id=OID)
    assert d["target_id"] == "TEL-02" and d["status"] == "sent" and d["destination"]["label"] == "Point haut"
    assert "Point haut" in r.move_order_text(d) and "Prendre la Yagi" in r.move_order_text(d)


@pytest.mark.parametrize("kw", [{"target_id": ""}, {"status": "lost"}, {"destination": {"lat": 99, "lon": 2}},
                                {"note": "x" * 201}])
def test_invalid_orders(kw):
    with pytest.raises(InvalidFeature):
        r.validate_move_order(order(**kw), event_id=E, object_id=OID)


def test_only_the_pco_gives_an_order():
    new = r.validate_move_order(order(), event_id=E, object_id=OID)
    assert r.move_order_allowed(None, None, new, "PCO", "create", pco=True)
    assert not r.move_order_allowed(None, None, new, "TEL-03", "create", pco=False)


def test_the_operator_only_answers():
    before = r.validate_move_order(order(), event_id=E, object_id=OID)
    answer = dict(before, status="accepted", updated_by="TEL-02")
    assert r.move_order_allowed(before, "PCO", answer, "TEL-02", "update", pco=False)
    assert not r.move_order_allowed(before, "PCO", dict(answer, status="cancelled"), "TEL-02", "update", pco=False)
    moved = dict(answer, destination={"lat": 48.0, "lon": 2.0, "label": "ailleurs"})
    assert not r.move_order_allowed(before, "PCO", moved, "TEL-02", "update", pco=False)
    assert not r.move_order_allowed(before, "PCO", answer, "TEL-03", "update", pco=False)
    assert not r.move_order_allowed(before, "PCO", answer, "TEL-02", "delete", pco=False)
    assert r.move_order_allowed(before, "PCO", dict(before, status="cancelled"), "PCO", "update", pco=True)
