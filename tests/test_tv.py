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


def test_tv_address_alone_opens_the_display():
    from fastapi.testclient import TestClient
    from sarcade.api.app import app
    c = TestClient(app)
    r = c.get("/", headers={"host": "tv.sarcade.org"})
    assert r.status_code == 200 and "SARCADE" in r.text and "sarcade_tv_token" in r.text
    assert c.get("/api/v0.1/events", headers={"host": "tv.sarcade.org"}).status_code == 404



def test_view_sent_by_a_phone_is_checked():
    v = tv.clean_view({"lat": 48.8, "lon": 2.1, "zoom": 14.333, "basemap": "ign",
                       "tile_url": "https://data.geopf.fr/wmts/{z}/{x}/{y}", "attribution": "IGN"}, now=1)
    assert v == {"lat": 48.8, "lon": 2.1, "zoom": 14.33, "basemap": "ign",
                 "tile_url": "https://data.geopf.fr/wmts/{z}/{x}/{y}", "attribution": "IGN", "rev": 1000,
                 "layers": tv.DEFAULT_LAYERS, "opacity": tv.DEFAULT_OPACITY, "messages": True}
    assert tv.clean_view(None) is None
    import pytest
    for bad in ({"lat": 99, "lon": 2, "zoom": 10}, {"lat": 1, "lon": 2, "zoom": 30},
                {"lat": 1, "lon": 2, "zoom": 10, "tile_url": "http://x/{z}/{x}/{y}"},
                {"lat": 1, "lon": 2, "zoom": 10, "tile_url": 'https://x/{z}/{x}/{y}"><script>'},
                {"lat": 1, "lon": 2, "zoom": 10, "tile_url": "javascript:alert(1)"}):
        with pytest.raises(ValueError):
            tv.clean_view(bad)


# --- Step 2 of « Envoyer ma vue », weather in the top bar (29 Oct 2026) -----

from datetime import UTC, datetime, timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

VIEW = {"lat": 48.8, "lon": 2.1, "zoom": 12}


def test_view_layers_opacity_and_messages():
    v = tv.clean_view({**VIEW, "layers": {"aprs": False, "relays": True, "nope": True},
                       "opacity": {"draw": 0.5, "brg": 1}, "messages": False, "extra": 1}, now=1)
    assert v["layers"] == {**tv.DEFAULT_LAYERS, "aprs": False, "relays": True}
    assert v["opacity"] == {"ops": 1.0, "draw": 0.5, "brg": 1.0, "ref": 1.0}
    assert v["messages"] is False and "extra" not in v
    d = tv.clean_view(VIEW, now=1)
    assert d["layers"] == {"operators": True, "aprs": True, "offline": True, "drawings": True,
                           "bearings": True, "highpoints": False, "relays": False}
    assert d["messages"] is True
    # Automatic framing (no view) and views stored before step 2: defaults.
    assert tv.display_options(None)["layers"] == tv.DEFAULT_LAYERS
    assert tv.display_options({"lat": 1})["opacity"] == tv.DEFAULT_OPACITY


@pytest.mark.parametrize("extra", [{"layers": []}, {"layers": {"aprs": "non"}}, {"opacity": {"ops": 0}},
                                   {"opacity": {"ref": 1.5}}, {"opacity": {"draw": True}}, {"opacity": 1},
                                   {"messages": "oui"}])
def test_invalid_view_options(extra):
    with pytest.raises(ValueError):
        tv.clean_view({**VIEW, **extra})


NOW = datetime(2026, 10, 29, 14, 20, tzinfo=UTC)


def test_hidden_layers_are_respected():
    old = (NOW - timedelta(minutes=30)).isoformat()
    snap = {"positions": [{"device_id": "A", "source": "device", "time": NOW}, {"device_id": "B", "source": "device", "time": old},
                          {"device_id": "aprs:F4X", "source": "aprs", "time": NOW}],
            "messages": [{"body": "x"}]}
    drawings, bearings = [{"kind": "zone"}], [{"azimuth_deg": 10}]
    refs = [{"category": "HIGH_POINT", "name": "PH"}, {"category": "RELAY", "name": "R"}]
    out = tv.apply_view(snap, None, NOW, drawings=drawings, bearings=bearings, references=refs)
    assert [p["device_id"] for p in out["positions"]] == ["A", "B", "aprs:F4X"]
    assert out["drawings"] == drawings and out["bearings"] == bearings and out["references"] == []
    view = tv.clean_view({**VIEW, "layers": {"offline": False, "aprs": False, "drawings": False, "bearings": False,
                                             "highpoints": True}, "messages": False})
    out = tv.apply_view(snap, view, NOW, drawings=drawings, bearings=bearings, references=refs)
    assert [p["device_id"] for p in out["positions"]] == ["A"]
    assert out["drawings"] == [] and out["bearings"] == [] and [r["name"] for r in out["references"]] == ["PH"]
    assert out["options"]["messages"] is False and out["messages"] == [{"body": "x"}]   # banner kept
    view = tv.clean_view({**VIEW, "layers": {"operators": False}})
    assert [p["device_id"] for p in tv.apply_view(snap, view, NOW)["positions"]] == ["aprs:F4X"]
    assert "drawings" not in tv.apply_view(snap, view, NOW)                # unchanged: not sent again


def test_bearing_for_the_tv():
    f = {"id": "b1", "points": [[48.8, 2.1]], "label": "",
         "bearing": {"azimuth_deg": 45, "length_m": 8000, "search": "Balise Rambouillet", "exercise": True}}
    b = tv.tv_bearing(f)
    assert b["lat"] == 48.8 and b["azimuth_deg"] == 45 and b["exercise"] is True
    assert b["color"] == tv.search_color("Balise Rambouillet") in tv.SEARCH_COLORS
    assert tv.tv_bearing({**f, "bearing": {**f["bearing"], "exercise": None}})["exercise"] is False
    assert tv.tv_drawing({"id": "z", "kind": "zone", "points": [[1, 2]], "color": 1, "created_by": "x"}) == {
        "id": "z", "kind": "zone", "points": [[1, 2]], "color": 1}


def forecast(code=0, cloud=10, temp=12.4):
    hours = [{"time": f"2026-10-29T{h:02d}:00:00Z", "temperature_c": temp + h / 100, "weather_code": code,
              "cloud_cover_pct": cloud} for h in range(24)]
    return {"hourly": hours, "daily": [{"date": "2026-10-29", "sunrise": "2026-10-29T06:30:00Z",
                                        "sunset": "2026-10-29T16:50:00Z"}]}


def test_weather_of_the_current_hour():
    w = tv.weather_now(forecast(), None, NOW)
    assert w == {"temp_c": 12.5, "icon": "sun", "vigilance": None}
    night = NOW.replace(hour=21)
    assert tv.weather_now(forecast(), None, night)["icon"] == "moon"
    assert tv.weather_now(forecast(code=2), None, night)["icon"] == "moon_cloud"
    assert tv.weather_now(forecast(code=2), None, NOW)["icon"] == "sun_cloud"
    for code, icon in ((3, "cloud"), (61, "rain"), (81, "rain"), (95, "storm"), (73, "snow"), (45, "fog")):
        assert tv.weather_now(forecast(code=code), None, NOW)["icon"] == icon
    assert tv.weather_now(forecast(code=None, cloud=90), None, NOW)["icon"] == "cloud"
    assert tv.weather_now(forecast(), {"color_id": 3}, NOW)["vigilance"] == "orange"
    assert tv.weather_now(forecast(), {"color_id": 4}, NOW)["vigilance"] == "red"
    assert tv.weather_now(forecast(), {"color_id": 2}, NOW)["vigilance"] == "yellow"
    assert tv.weather_now(forecast(), {"color_id": 1}, NOW)["vigilance"] is None
    assert tv.weather_now(None, None, NOW) is None
    assert tv.weather_now(forecast(), None, NOW + timedelta(days=3)) is None   # outdated forecast


def test_snapshot_weather_from_the_weather_cache(monkeypatch):
    cache = {"event:e1": SimpleNamespace(data=forecast(code=61)), "vigilance:e1": SimpleNamespace(data={"color_id": 3})}
    calls = []

    def fake_get(db, key):
        calls.append(key)
        return cache.get(key)
    monkeypatch.setattr(api.weather_service, "cache_get", fake_get)
    monkeypatch.setattr(tv, "weather_cache", tv.WeatherCache())
    monkeypatch.setattr(api, "datetime", SimpleNamespace(now=lambda tz=None: NOW))
    w = api._weather(None, "e1")
    assert w == {"temp_c": 12.5, "icon": "rain", "vigilance": "orange"}
    api._weather(None, "e1")
    assert calls == ["event:e1", "vigilance:e1"]                 # kept 10 minutes
    assert api._weather(None, "no-point") is None                # event without weather point


def test_weather_cache_expires_after_ten_minutes():
    c = tv.WeatherCache()
    values = iter([1, 2])
    assert c.get("e", lambda: next(values), now=0) == 1
    assert c.get("e", lambda: next(values), now=599) == 1
    assert c.get("e", lambda: next(values), now=601) == 2


def test_tv_page_draws_the_layers_with_escaped_texts():
    for needle in ("drawFeatures", "drawBearings", "drawRefs", "EXERCICE", "msgBox", 'id="wx"',
                   "esc(f.label)", "esc(name)", "esc(r.callsign||r.name)"):
        assert needle in api._TV
