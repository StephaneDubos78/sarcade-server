"""Smart TV display: pairing, token, what is shown, TV address (29 Oct 2026)."""
from sarcade import tv
from sarcade.api import tv as api


def test_pairing_code_approved_once():
    s = tv.Store()
    p = s.new(now=1000)
    assert len(p.code) == 6 and set(p.code) <= set(tv.CODE_ALPHABET)
    assert s.approve(p.code.lower(), "evt", now=1010).token
    assert s.approve(p.code, "evt", now=1011) is None          # once
    q = s.new(now=1000)
    assert s.approve(q.code, "evt", now=1000 + tv.CODE_TTL_S + 1) is None  # expired


def test_rate_limit_per_client():
    s = tv.Store()
    assert all(s.allowed("1.2.3.4", now=50) for _ in range(tv.REQUESTS_PER_MINUTE))
    assert not s.allowed("1.2.3.4", now=55)
    assert s.allowed("5.6.7.8", now=55)
    assert s.allowed("1.2.3.4", now=200)


def test_token_valid_until_revoked_or_expired():
    d = {"hash": tv.token_hash("tok"), "expires": 2000, "revoked": False}
    assert tv.valid_display([d], "tok", now=1000) is d
    assert tv.valid_display([d], "other", now=1000) is None
    assert tv.valid_display([d], "tok", now=3000) is None
    assert tv.valid_display([{**d, "revoked": True}], "tok", now=1000) is None


def test_tv_shows_general_messages_only():
    s = tv.snapshot({"id": "e", "name": "Exercice"}, [], [
        {"recipient_ids": [], "body": "à tous"}, {"recipient_ids": ["user:PCO"], "body": "privé"},
        {"recipient_ids": ["group:x"], "body": "canal"}], [])
    assert [m["body"] for m in s["messages"]] == ["à tous"]


def test_tv_address_exposes_the_display_only():
    assert api.tv_host_allows("/tv")
    assert api.tv_host_allows("/api/v0.1/tv/pair")
    assert api.tv_host_allows("/api/v0.1/tv/pair/abc")
    assert api.tv_host_allows("/api/v0.1/tv/state")
    assert not api.tv_host_allows("/api/v0.1/tv/approve")
    assert not api.tv_host_allows("/tv/approve")
    assert not api.tv_host_allows("/api/v0.1/events")
    assert not api.tv_host_allows("/")


def test_tv_logbook_hides_acks_and_messages():
    s = tv.snapshot({"id": "e", "name": "Exercice"}, [], [], [
        {"kind": "ack", "summary": "received: 5411"}, {"kind": "message", "summary": "message privé"},
        {"kind": "display", "summary": "Écran d'affichage appairé"}, {"kind": "settings", "summary": "Seuil modifié"}])
    assert [r["summary"] for r in s["logbook"]] == ["Écran d'affichage appairé", "Seuil modifié"]
    assert all("kind" not in r for r in s["logbook"])


def test_any_operator_pairs_a_tv():
    """Decision of 29 Oct 2026: approving or revoking a TV is not a PCO right."""
    import inspect
    from types import SimpleNamespace
    for fn in (api.approve, api.revoke_display, api.list_displays):
        assert "require_pco" not in inspect.getsource(fn)
    req = SimpleNamespace(state=SimpleNamespace(access=SimpleNamespace(email="op@x.fr")))
    assert api._actor(req) == "op@x.fr"
    assert api._actor(SimpleNamespace(state=SimpleNamespace())) == "opérateur"


def test_tv_logo_is_served_on_the_tv_address():
    assert api.tv_host_allows("/tv/logo.png")
    assert api._LOGO.is_file()
