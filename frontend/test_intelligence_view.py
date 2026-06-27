from intelligence_view import (
    dashboard_html,
    feedback_line,
    form_reading,
    ftp_bars,
    intensity_bar,
    power_bars,
    summary_html,
)

_TWIN = {
    "intensity_split": {"label": "pyramidal", "z1_pct": 0.70, "z2_pct": 0.27, "z3_pct": 0.03},
    "power_curve_bests": {"5 s": 1227.0, "20 min": 331.0, "60 min": 275.0},
    "block_summary": [
        {"block_type": "build", "start": "2025-06-09", "end": "2025-07-20",
         "evidence": "CTL 27→68 em 6 sem"},
        {"block_type": "recovery", "start": "2025-09-15", "end": "2025-09-21",
         "evidence": "CTL 89→85"},
    ],
    "data_richness": {"score": 0.91},
}
_FORM = {"metric_date": "2026-06-24", "ctl": 85.2, "atl": 84.0, "tsb": -9.7}
_FTP = [
    {"ftp_watts": 281.0, "valid_from": "2026-01-01"},
    {"ftp_watts": 297.0, "valid_from": "2026-04-01"},
]


def test_form_reading_thresholds():
    assert "pico de forma" in form_reading(80, 60, 20)
    assert "Fresco" in form_reading(80, 70, 8)
    assert "Equilibrado" in form_reading(85, 84, -5)
    assert "fatigado" in form_reading(85, 95, -20)
    assert "recupera" in form_reading(85, 120, -35)


def test_intensity_bar_three_zones():
    svg = intensity_bar(_TWIN["intensity_split"])
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 3
    assert "#3b82f6" in svg  # z1 color
    assert intensity_bar(None) == ""


def test_power_bars_scales_to_max():
    html = power_bars(_TWIN["power_curve_bests"])
    assert "1227" in html and "275" in html
    assert power_bars(None) == ""


def test_ftp_bars_dedupes_period():
    # two rows for the same period (different methods) -> a single bar
    hist = [
        {"ftp_watts": 281.0, "valid_from": "2026-01-01", "method": "estimate_pc20"},
        {"ftp_watts": 285.0, "valid_from": "2026-01-01", "method": "task2_analysis"},
        {"ftp_watts": 297.0, "valid_from": "2026-04-01", "method": "estimate_pc20"},
    ]
    html = ftp_bars(hist)
    assert html.count("border-radius:4px 4px 0 0") == 2  # 2 distinct periods
    assert ftp_bars(None) == ""


def test_summary_html_has_form_and_ftp():
    html = summary_html(_FORM, 297.0, _TWIN["intensity_split"])
    assert "Forma (TSB)" in html
    assert "-10" in html or "−10" in html or "-9" in html  # rounded TSB shown
    assert "297" in html
    assert "pyramidal" in html


def test_summary_html_empty_when_nothing():
    assert summary_html(None, None, None) == ""


def test_dashboard_renders_all_sections():
    html = dashboard_html(_TWIN, _FTP, _FORM)
    assert "Estado de forma" in html
    assert "Curva de potência" in html
    assert "Distribuição de intensidade" in html
    assert "Periodização real · 2 blocos" in html
    assert "score 0.91" in html
    assert "BUILD" in html  # block tag


def test_dashboard_empty_when_no_intelligence():
    html = dashboard_html(None, None, None)
    assert "ainda não gerado" in html


def test_feedback_line_renders_when_count_positive():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 4, "avg_rating": 4.2, "made_sense_pct": 88})
    assert "4" in out and "4.2" in out and "88%" in out
    assert "avalia" in out.lower()


def test_feedback_line_empty_when_no_feedback():
    from intelligence_view import feedback_line
    assert feedback_line(None) == ""
    assert feedback_line({}) == ""
    assert feedback_line({"count": 0}) == ""


def test_feedback_line_without_made_sense():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 2, "avg_rating": 3.5, "made_sense_pct": None})
    assert "3.5" in out
    assert "%" not in out  # sem o trecho de "fez sentido"
