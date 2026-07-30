"""Duas fontes, uma linha por dia — quem ganha e quem nunca apaga.

Regressão histórica (2026-07-29): o sync do Garmin fazia
``existing.hrv_ms = snap.hrv_ms`` sem checar, então um dia em que o atleta dormiu
sem o relógio gravava None por cima de um HRV bom. Com a Whoop na jogada isso
passaria a apagar o dado da pulseira todo dia.
"""
from __future__ import annotations

from app.models.metrics import RecoveryMetric
from app.services.recovery.merge import RecoverySnapshot, merge_into


def _row(**kw) -> RecoveryMetric:
    return RecoveryMetric(metric_date=None, **kw)


def test_whoop_fills_an_empty_day():
    row = _row()

    assert merge_into(row, RecoverySnapshot(hrv_ms=61.5, resting_hr=48), "whoop") is True
    assert row.hrv_ms == 61.5
    assert row.resting_hr == 48
    assert row.source == "whoop"


def test_whoop_overwrites_garmin_on_the_same_day():
    """Precedência: a pulseira 24h vence o relógio que depende de dormir com ele."""
    row = _row(hrv_ms=40.0, source="garmin")

    merge_into(row, RecoverySnapshot(hrv_ms=61.5), "whoop")

    assert row.hrv_ms == 61.5
    assert row.source == "garmin+whoop"


def test_garmin_does_not_overwrite_a_whoop_day():
    row = _row(hrv_ms=61.5, source="whoop")

    assert merge_into(row, RecoverySnapshot(hrv_ms=40.0), "garmin") is False
    assert row.hrv_ms == 61.5
    assert row.source == "whoop"


def test_garmin_fills_a_field_the_whoop_left_empty():
    """Precedência é por campo na leitura: o que a Whoop não trouxe, o Garmin preenche."""
    row = _row(hrv_ms=61.5, source="whoop")

    assert merge_into(row, RecoverySnapshot(sleep_hours=7.2), "garmin") is True
    assert row.sleep_hours == 7.2
    assert row.hrv_ms == 61.5
    assert row.source == "whoop+garmin"


def test_garmin_still_refreshes_its_own_data_on_a_garmin_only_day():
    row = _row(hrv_ms=40.0, source="garmin")

    merge_into(row, RecoverySnapshot(hrv_ms=42.0), "garmin")

    assert row.hrv_ms == 42.0


def test_empty_value_never_erases_an_existing_one():
    """O bug de 2026-07-29, travado: None não é dado, é ausência de dado."""
    row = _row(hrv_ms=61.5, sleep_hours=7.2, source="whoop")

    assert merge_into(row, RecoverySnapshot(), "garmin") is False
    assert row.hrv_ms == 61.5
    assert row.sleep_hours == 7.2

    assert merge_into(row, RecoverySnapshot(), "whoop") is False
    assert row.hrv_ms == 61.5


def test_source_does_not_duplicate_on_repeated_sync():
    row = _row()
    merge_into(row, RecoverySnapshot(hrv_ms=61.5), "whoop")
    merge_into(row, RecoverySnapshot(hrv_ms=62.0), "whoop")

    assert row.source == "whoop"
