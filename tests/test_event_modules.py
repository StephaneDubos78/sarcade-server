"""Modules enabled per event (card « Séparer le Core et les modules », step 2)."""
import pytest

from sarcade import modules
from sarcade.events import settings as s


def test_older_events_keep_adrasec():
    assert s.merged(None)["modules"] == ["adrasec"]
    assert modules.enabled(None, "adrasec") and modules.enabled({}, "adrasec")


def test_event_models():
    assert modules.for_kind("family") == []
    assert modules.for_kind("friends") == []
    assert modules.for_kind("exercise") == ["adrasec"]
    assert modules.for_kind("SATER") == ["adrasec"]
    assert modules.for_kind("race") == ["race"]
    assert modules.for_kind("anything else") == ["adrasec"]


def test_patch_modules_known_only_in_registry_order():
    assert s.apply_patch(None, {"modules": ["race", "adrasec", "race"]})["modules"] == ["adrasec", "race"]
    assert s.apply_patch(None, {"modules": []})["modules"] == []
    for bad in (["sar"], "adrasec", [1]):
        with pytest.raises(s.InvalidSettings):
            s.apply_patch(None, {"modules": bad})


def test_logbook_line_when_modules_change():
    assert "Modules de l'événement : aucun (Core seul)" in s.logbook_summaries(None, {"modules": []})
    assert s.logbook_summaries({"modules": ["adrasec"]}, {"modules": ["adrasec"]}) == []


def test_enabled_reads_stored_settings():
    assert not modules.enabled({"modules": []}, "adrasec")
    assert modules.enabled({"modules": ["adrasec"]}, "adrasec")
    assert not modules.enabled({"modules": ["adrasec"]}, "race")
