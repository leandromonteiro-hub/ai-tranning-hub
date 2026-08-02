"""Provas de múltiplos dias — modelo e schemas (spec 2026-08-02)."""
from __future__ import annotations

from app.models.race import Race


def test_race_tem_end_date_nullable():
    col = Race.__table__.columns["end_date"]
    assert col.nullable is True
