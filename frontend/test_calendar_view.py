from datetime import date

from calendar_view import (
    adherence,
    block_label_for_week,
    calendar_html,
    detail_html,
    flatten_structure,
    interval_lines,
    week_dates,
    workout_svg,
    zone_of,
)

_STRUCT = {
    "name": "VO2 4x4",
    "elements": [
        {"intensity": "warmup", "duration_s": 600,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.65}},
        {"count": 3, "steps": [
            {"intensity": "active", "duration_s": 300,
             "target": {"type": "power_pct_ftp", "low": 1.1, "high": 1.1}},
            {"intensity": "rest", "duration_s": 180,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
        ]},
        {"intensity": "cooldown", "duration_s": 300,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.55}},
    ],
}


def test_zone_of_boundaries():
    assert zone_of(0.50) == 1
    assert zone_of(0.60) == 2
    assert zone_of(0.80) == 3
    assert zone_of(1.00) == 4
    assert zone_of(1.10) == 5
    assert zone_of(1.30) == 6
    assert zone_of(1.60) == 7


def test_flatten_expands_repeats():
    segs = flatten_structure(_STRUCT)
    # warmup + 3*(active+rest) + cooldown = 1 + 6 + 1 = 8
    assert len(segs) == 8
    assert sum(s["duration_s"] for s in segs) == 600 + 3 * (300 + 180) + 300
    assert segs[1]["zone"] == 5  # the active VO2 step


def test_flatten_empty():
    assert flatten_structure(None) == []
    assert flatten_structure({}) == []


def test_interval_lines_formats_repeat_and_endpoints():
    lines = interval_lines(_STRUCT)
    assert lines[0].startswith("Aquecimento 10min @ 55-65%")
    assert any(l.startswith("3× 5min @ 110% / 3min @ 50%") for l in lines)
    assert lines[-1].startswith("Volta à calma 5min @ 55%")


def test_adherence_thresholds():
    assert adherence(100, 95)[0] == "✅"
    assert adherence(100, 70)[0] == "🟡"
    assert adherence(100, 30)[0] == "🔴"
    assert adherence(None, 50) == ("", "")
    assert adherence(100, None) == ("", "")


def test_week_dates_monday_to_sunday():
    wd = week_dates(date(2026, 6, 25))  # quinta
    assert wd[0] == date(2026, 6, 22)   # segunda
    assert wd[6] == date(2026, 6, 28)   # domingo
    assert len(wd) == 7


def test_workout_svg_empty_and_zone_colors():
    assert workout_svg([]) == ""
    svg = workout_svg(flatten_structure(_STRUCT))
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 8          # one bar per flattened segment
    assert "#ff8a3d" in svg                 # zone 5 (VO2) color present


def test_calendar_html_renders_week():
    week = week_dates(date(2026, 6, 25))    # Mon 22 .. Sun 28
    by_date = {"2026-06-25": {
        "id": "x", "name": "VO2 4x4", "workout_type": "VO2MAX",
        "planned_duration_s": 3600, "planned_tss": 90, "structure": _STRUCT,
    }}
    completed = {"2026-06-22": [{"tss": 80, "duration_s": 3600}]}
    # athlete did Monday's (rest) day work; the planned day is today (the 25th)
    html = calendar_html(week, by_date, completed, today=date(2026, 6, 25))
    assert html.count('class="cell') == 7   # 7 day cells
    assert "Descanso" in html               # days without a planned workout
    assert "HOJE" in html                   # today's tag
    assert "VO2 4x4" in html                # the planned workout name
    assert "<svg" in html                   # the profile is drawn


def test_calendar_html_escapes_name():
    week = week_dates(date(2026, 6, 25))
    by_date = {"2026-06-25": {
        "id": "x", "name": "A & B <hack>", "workout_type": "ENDURANCE",
        "planned_duration_s": 600, "planned_tss": 50, "structure": _STRUCT,
    }}
    html = calendar_html(week, by_date, {}, today=date(2026, 6, 25))
    assert "<hack>" not in html
    assert "&amp; B" in html


def test_detail_html_empty_and_present():
    assert detail_html(None) == ""
    assert "<svg" in detail_html(_STRUCT)


def test_block_label_for_week_overlap():
    week = week_dates(date(2026, 6, 25))  # 22..28 jun
    blocks = [
        {"block_type": "BASE", "start_date": "2026-06-01", "end_date": "2026-06-21"},
        {"block_type": "BUILD", "start_date": "2026-06-22", "end_date": "2026-07-12"},
    ]
    assert block_label_for_week(blocks, week) == "Bloco BUILD"
    assert block_label_for_week([], week) == ""
    # a week before any block -> no label
    early = week_dates(date(2026, 5, 1))
    assert block_label_for_week(blocks, early) == ""


def test_calendar_html_week_adherence_and_block():
    week = week_dates(date(2026, 6, 25))
    by_date = {"2026-06-24": {"id": "a", "name": "Endurance", "workout_type": "ENDURANCE",
                              "planned_duration_s": 3600, "planned_tss": 100, "structure": _STRUCT}}
    completed = {"2026-06-24": [{"tss": 95, "duration_s": 3600}]}
    html = calendar_html(week, by_date, completed, today=date(2026, 6, 28),
                         block_label="Bloco BUILD")
    assert "Bloco BUILD" in html
    assert "95% adesão" in html          # 95/100
    # a future week with no actuals shows no adherence pill
    future = calendar_html(week, by_date, {}, today=date(2026, 6, 1))
    assert "adesão" not in future


def test_effective_workout_prefers_adjustment():
    from calendar_view import effective_workout
    w = {"name": "Sweet Spot", "planned_tss": 80, "planned_duration_s": 3600,
         "structure": {"elements": [{"intensity": "active", "duration_s": 3600,
                                     "target": {"type": "power_pct_ftp", "low": 0.9}}]},
         "adjustment": {"structure": {"elements": []}, "tss": 30, "duration_s": 1800}}
    eff, is_adj = effective_workout(w)
    assert is_adj is True
    assert eff["planned_tss"] == 30
    assert eff["planned_duration_s"] == 1800
    assert eff["structure"] == {"elements": []}


def test_effective_workout_without_adjustment():
    from calendar_view import effective_workout
    w = {"name": "X", "planned_tss": 80, "structure": {"elements": []}}
    eff, is_adj = effective_workout(w)
    assert is_adj is False
    assert eff is w


def test_day_cell_shows_ai_badge_when_adjusted():
    from datetime import date
    from calendar_view import _day_cell_html
    w = {"name": "Sweet Spot", "workout_type": "SWEET_SPOT", "planned_tss": 30,
         "planned_duration_s": 1800, "structure": {"elements": []},
         "adjustment": {"structure": {"elements": []}, "tss": 30, "duration_s": 1800}}
    html = _day_cell_html(date(2026, 6, 30), w, [], date(2026, 6, 30))
    assert "IA" in html


def test_calendar_html_marks_selected_day():
    week = week_dates(date(2026, 6, 25))
    by_date = {
        "2026-06-24": {"id": "a", "name": "Endurance", "workout_type": "ENDURANCE",
                       "planned_duration_s": 3600, "planned_tss": 60, "structure": _STRUCT},
        "2026-06-25": {"id": "b", "name": "VO2 4x4", "workout_type": "VO2MAX",
                       "planned_duration_s": 3600, "planned_tss": 90, "structure": _STRUCT},
    }
    html = calendar_html(week, by_date, {}, today=date(2026, 6, 25),
                         selected="2026-06-24")
    assert "cell sel" in html               # the chosen day carries the highlight
    assert html.count('"cell sel"') == 1    # exactly one cell highlighted
