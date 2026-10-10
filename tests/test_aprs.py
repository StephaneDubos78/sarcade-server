from datetime import UTC, datetime, timedelta

import pytest

from sarcade.aprs import callsigns as calls
from sarcade.aprs import encode, kiss, parser
from sarcade.aprs.service import Deduplicator, packet_key
from sarcade.events import settings as event_settings


def approx(a, b, tol=1e-4):
    return abs(a - b) < tol


# Reference values cross-checked with aprslib.

def test_uncompressed_position_with_timestamp_course_speed_altitude():
    p = parser.decode("F1ABC>APRS,WIDE2-1:@092345z4903.50N/07201.75W>088/036/A=001234 test")
    assert p.callsign == "F1ABC"
    assert approx(p.lat, 49.058333) and approx(p.lon, -72.029167)
    assert p.symbol == "/>" and p.course_deg == 88
    assert approx(p.speed_mps * 3.6, 66.672, 0.01) and approx(p.alt_m, 376.1232, 0.01)
    assert p.comment == "test"


def test_position_without_timestamp_and_ambiguity():
    p = parser.decode("F4JPO-7>APRS:!4903.5 N/0720 .  E-")
    assert approx(p.lat, 49 + 3.5 / 60) and approx(p.lon, 72 + 0.0)


def test_compressed_position():
    p = parser.decode("F4XYZ>APRS:!/5L!!<*e7>7P[")
    assert approx(p.lat, 49.5) and approx(p.lon, -72.750004)
    assert p.course_deg == 88 and approx(p.speed_mps * 3.6, 67.1017, 0.01)


def test_mic_e_position():
    p = parser.decode('F4XYZ-9>SR3PYT:`zQ{l"2>/ mobile')
    assert p.callsign == "F4XYZ-9"
    assert approx(p.lat, 32.515667) and approx(p.lon, -4.899167)
    assert p.course_deg == 222 and p.speed_mps == 0
    assert p.symbol == "/>" and p.comment == "mobile"


def test_object_belongs_to_its_name():
    p = parser.decode("F6KRK>APRS:;SECTEUR-A*092345z4903.50N/00201.75E[relais")
    assert p.callsign == "SECTEUR-A" and p.sender == "F6KRK" and p.extra["object"]


def test_third_party_traffic_is_unwrapped():
    p = parser.decode("F6KRK-10>APRS:}F4JPO-9>APRS,TCPIP,F6KRK-10*:!4903.50N/00201.75E>")
    assert p.callsign == "F4JPO-9"


@pytest.mark.parametrize("line", [
    "F1ABC>APRS::F4JPO    :Bonjour{1",   # message
    "F1ABC>APRS:>Station en route",       # status
    "F1ABC>APRS:!0000.00N/00000.00E>",     # null island
    "pas une trame",
    "F1ABC>APRS:;SECTEUR-A_092345z4903.50N/00201.75E[",  # killed object
])
def test_non_positions_are_ignored(line):
    with pytest.raises(parser.NotAPosition):
        parser.decode(line)


def test_callsign_normalisation():
    assert calls.normalize(" f4jpo-0 ") == "F4JPO"
    assert calls.normalize_list(["f4jpo", "F4JPO", "F1ABC-9"]) == ["F4JPO", "F1ABC-9"]
    with pytest.raises(calls.InvalidCallsign):
        calls.normalize("F4 JPO")


def test_entry_without_ssid_covers_every_ssid():
    assert calls.matches("F4JPO-9", ["F4JPO"]) and calls.matches("F4JPO", ["F4JPO"])
    assert calls.matches("F4JPO-9", ["F4JPO-9"]) and not calls.matches("F4JPO-7", ["F4JPO-9"])
    assert not calls.matches("F4JPOX", ["F4JPO"])


def test_aprs_is_filter_only_requests_selected_stations():
    assert calls.budlist_filter(["F4JPO", "F1ABC-9"]) == "b/F1ABC-9/F4JPO*"
    assert calls.budlist_filter([]) == "b/SARCADE-NONE"


def test_ax25_round_trip_and_kiss_stream():
    frame = kiss.encode_ui("F4JPO-9", "APRS", ["WIDE1-1", "F6KRK-10*"], "!4903.50N/00201.75E>")
    assert kiss.ax25_to_tnc2(frame) == "F4JPO-9>APRS,WIDE1-1,F6KRK-10*:!4903.50N/00201.75E>"
    data = kiss.kiss_frame(frame) + kiss.kiss_frame(kiss.encode_ui("F1ABC", "APRS", [], "\xc0\xdb"))
    decoder = kiss.KissDecoder()
    frames = decoder.feed(data[:7]) + decoder.feed(data[7:])
    assert [kiss.ax25_to_tnc2(f) for f in frames][1] == "F1ABC>APRS:\xc0\xdb", "escaped bytes survive"


def test_invalid_ax25_callsign():
    with pytest.raises(kiss.InvalidFrame):
        kiss.encode_ui("TOOLONGCALL", "APRS", [], "x")


def test_object_report_decodes_back():
    at = datetime(2026, 10, 10, 6, 30, tzinfo=UTC)
    info = encode.object_report("F4JPO-9", 48.80123, 2.13456, at, comment="SARCADE")
    assert info.startswith(";F4JPO-9  *100630z")
    p = parser.decode(f"F6KRK>{encode.TOCALL}:{info}")
    assert p.callsign == "F4JPO-9" and approx(p.lat, 48.80123, 1e-3) and approx(p.lon, 2.13456, 1e-3)


def test_deduplication_window():
    d, t = Deduplicator(timedelta(seconds=30)), datetime(2026, 10, 10, tzinfo=UTC)
    key = packet_key("F4JPO-9>APRS:!4903.50N/00201.75E>")
    assert key == packet_key("F4JPO-9>APRS,WIDE1-1,qAR,F6KRK:!4903.50N/00201.75E>"), "path does not matter"
    assert d.first_time(key, t) and not d.first_time(key, t + timedelta(seconds=10))
    assert d.first_time(key, t + timedelta(seconds=45))


def test_event_settings_validate_aprs_callsigns():
    s = event_settings.apply_patch(None, {"aprs_callsigns": ["f4jpo", "F1ABC-9"], "aprs_groups": ["g1", "g1"]})
    assert s["aprs_callsigns"] == ["F4JPO", "F1ABC-9"] and s["aprs_groups"] == ["g1"]
    with pytest.raises(event_settings.InvalidSettings):
        event_settings.apply_patch(None, {"aprs_callsigns": ["pas valide !"]})
    assert event_settings.merged(None)["aprs_tx_rf"] is False, "radio transmission off by default"


def test_radio_transmission_needs_pco_decision_consent_and_callsigns(monkeypatch):
    import asyncio
    from sarcade.aprs import service
    from sarcade.db.models import DeviceRow

    rt = service.AprsRuntime()
    rt.tx_queue = asyncio.Queue()
    rt.radio.connected = True
    monkeypatch.setattr(service, "runtime", rt)
    monkeypatch.setenv("SARCADE_APRS_CALLSIGN", "F6KRK")
    now = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
    device = DeviceRow(event_id="e", device_id="TEL-01", callsign="F4JPO", aprs_tx_consent=True)
    on = {"aprs_tx_rf": True}

    assert not service.queue_transmission({}, device, 48.8, 2.1, now), "off unless the PCO enables it"
    device.aprs_tx_consent = False
    assert not service.queue_transmission(on, device, 48.8, 2.1, now), "operator consent required"
    device.aprs_tx_consent = True
    assert service.queue_transmission(on, device, 48.8, 2.1, now)
    assert not service.queue_transmission(on, device, 48.8, 2.1, now + timedelta(seconds=30)), "rate limited"
    assert service.queue_transmission(on, device, 48.8, 2.1, now + timedelta(minutes=3))
    frame = kiss.KissDecoder().feed(rt.tx_queue.get_nowait())[0]
    line = kiss.ax25_to_tnc2(frame)
    assert line.startswith("F6KRK>APZSAR,WIDE1-1:;F4JPO    *"), "object sent under the ADRASEC callsign"
    monkeypatch.setenv("SARCADE_APRS_CALLSIGN", "")
    assert not service.queue_transmission(on, device, 48.8, 2.1, now + timedelta(minutes=10)), "no ADRASEC callsign"
