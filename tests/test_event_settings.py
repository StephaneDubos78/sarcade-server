from datetime import UTC, datetime, timedelta

import pytest

from sarcade.events import settings as s


def test_defaults_match_the_validated_specification():
    d = s.merged(None)
    assert d["low_bandwidth"] is False
    assert d["low_bandwidth_interval_s"] == 60
    assert d["sync_alert_minutes"] == 5
    assert d["tracking_required"] is False
    assert d["tracking_default_interval_s"] == 30


def test_merged_ignores_unknown_stored_keys():
    assert "legacy" not in s.merged({"legacy": 1, "low_bandwidth": True})


def test_patch_applies_and_keeps_other_values():
    new = s.apply_patch({"sync_alert_minutes": 7}, {"low_bandwidth": True})
    assert new["low_bandwidth"] is True and new["sync_alert_minutes"] == 7


@pytest.mark.parametrize("patch,reason", [
    ({}, "empty_patch"),
    ({"colour": "red"}, "unknown_setting"),
    ({"low_bandwidth": "yes"}, "invalid_value"),
    ({"tracking_default_interval_s": 45}, "invalid_value"),
    ({"tracking_default_interval_s": True}, "invalid_value"),
    ({"sync_alert_minutes": 0}, "invalid_value"),
    ({"low_bandwidth_interval_s": 5}, "invalid_value"),
    ({"tracking_min_interval_s": 60, "tracking_default_interval_s": 30}, "inconsistent_tracking_bounds"),
])
def test_invalid_patches_are_rejected(patch, reason):
    with pytest.raises(s.InvalidSettings, match=reason):
        s.apply_patch(None, patch)


def test_interval_is_clamped_to_pco_bounds():
    bounds = {"tracking_min_interval_s": 30, "tracking_max_interval_s": 120, "tracking_default_interval_s": 60}
    assert s.clamp_interval(None, bounds) == 60
    assert s.clamp_interval(10, bounds) == 30
    assert s.clamp_interval(600, bounds) == 120
    assert s.clamp_interval(60, bounds) == 60


def test_logbook_lines_describe_pco_decisions():
    lines = s.logbook_summaries(None, s.apply_patch(None, {"low_bandwidth": True, "tracking_required": True}))
    assert "Mode liaison faible activé par le PCO" in lines
    assert "Suivi de position imposé par le PCO" in lines
    lines = s.logbook_summaries({"low_bandwidth": True}, s.merged(None))
    assert lines == ["Mode liaison faible levé par le PCO"]


def test_logbook_line_for_tracking_bounds():
    new = s.apply_patch(None, {"tracking_min_interval_s": 30, "tracking_max_interval_s": 300})
    assert s.logbook_summaries(None, new) == [
        "Suivi de position : fréquence de 30 s à 5 min, 30 s par défaut"]


def test_no_logbook_line_without_change():
    assert s.logbook_summaries(None, s.merged(None)) == []


def test_device_status_uses_alert_threshold():
    now = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
    assert s.device_status(None, {}, now) == "unknown"
    assert s.device_status(now - timedelta(minutes=4), {}, now) == "ok"
    assert s.device_status(now - timedelta(minutes=6), {}, now) == "late"
    assert s.device_status(now - timedelta(minutes=6), {"sync_alert_minutes": 10}, now) == "ok"
