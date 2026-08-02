"""Provas de múltiplos dias — modelo e schemas (spec 2026-08-02)."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.race import Race
from app.schemas.calendar import RaceMarker
from app.schemas.race import RaceCreate


def test_race_tem_end_date_nullable():
    col = Race.__table__.columns["end_date"]
    assert col.nullable is True


def _base(**kw):
    return {"name": "Brasil Ride", "race_date": date(2026, 9, 12), **kw}


def test_race_create_sem_end_date_ok():
    r = RaceCreate(**_base())
    assert r.end_date is None


def test_race_create_periodo_valido():
    r = RaceCreate(**_base(end_date=date(2026, 9, 14)))
    assert r.end_date == date(2026, 9, 14)


def test_end_date_antes_do_inicio_rejeitado():
    with pytest.raises(ValidationError):
        RaceCreate(**_base(end_date=date(2026, 9, 11)))


def test_periodo_acima_de_14_dias_rejeitado():
    with pytest.raises(ValidationError):
        RaceCreate(**_base(end_date=date(2026, 9, 26)))  # 15 dias


def test_race_marker_aceita_end_date():
    m = RaceMarker(id="00000000-0000-0000-0000-000000000001", name="X",
                   race_date=date(2026, 9, 12), end_date=date(2026, 9, 14), days_until=3)
    assert m.end_date == date(2026, 9, 14)
