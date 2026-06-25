"""_signals surfaces the traceable inputs behind a recommendation."""
from __future__ import annotations

from app.models.enums import BlockType
from app.services.ai.recommender import _signals
from app.services.ai.safety_validator import AthleteSafetySnapshot


def test_signals_captures_form_block_ftp():
    snap = AthleteSafetySnapshot(ctl=85.2, atl=84.0, tsb=-9.7, ramp_rate_7d=4.1, monotony=1.6)
    sig = _signals(snap, "Distribuição piramidal: Z1 70%", BlockType.BUILD, 297.0)
    assert sig["form"] == {"ctl": 85.2, "atl": 84.0, "tsb": -9.7,
                           "ramp_rate_7d": 4.1, "monotony": 1.6}
    assert sig["block"] == BlockType.BUILD.value
    assert sig["ftp_watts"] == 297
    assert sig["methodology"].startswith("Distribuição piramidal")


def test_signals_handles_missing_values():
    snap = AthleteSafetySnapshot()  # all None
    sig = _signals(snap, "n/d", None, None)
    assert sig["form"]["ctl"] is None and sig["form"]["tsb"] is None
    assert sig["block"] is None
    assert sig["ftp_watts"] is None
