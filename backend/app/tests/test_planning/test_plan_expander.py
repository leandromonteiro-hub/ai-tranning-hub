from datetime import date
from app.models.enums import BlockType, WorkoutType
from app.services.planning.plan_expander import WeekSpec, allocate_days


def _weeks() -> list[WeekSpec]:
    return [
        WeekSpec(date(2026, 1, 5), BlockType.BASE, 500.0, False),   # seg-dom
        WeekSpec(date(2026, 1, 12), BlockType.BUILD, 600.0, False),
    ]


def test_rest_days_per_week():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 18),
                         rest_per_week=1, today=date(2026, 1, 5))
    # 2 semanas × 6 dias de treino = 12 (jan 18 é o fim da 2a semana)
    assert len(days) == 12


def test_base_week_has_one_quality():
    days = allocate_days(_weeks()[:1], ftp=300.0, race_date=date(2026, 1, 11),
                         rest_per_week=1, today=date(2026, 1, 5))
    quality = [d for d in days if d.workout_type in (WorkoutType.SWEET_SPOT, WorkoutType.VO2MAX, WorkoutType.THRESHOLD)]
    assert len(quality) == 1
    assert all(d.structure and d.planned_tss > 0 for d in days)


def test_window_stops_at_race():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 14),
                         rest_per_week=1, today=date(2026, 1, 5))
    assert max(d.planned_date for d in days) <= date(2026, 1, 14)


def test_starts_at_today_not_before():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 18),
                         rest_per_week=1, today=date(2026, 1, 8))
    assert min(d.planned_date for d in days) >= date(2026, 1, 8)
