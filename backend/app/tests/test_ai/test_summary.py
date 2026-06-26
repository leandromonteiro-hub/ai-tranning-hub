"""Unit tests for the recommendation summary builder.

The summary line is shown in the recommendations tab and the day-adjustment
preview panel, so it must read as plain text — the raw LLM markdown heading
('# ...') must not leak through — while keeping the risk prefix.
"""
from types import SimpleNamespace

from app.models.enums import RiskLevel
from app.services.ai.recommender import _summary, first_meaningful_line


def _safety(risk):
    return SimpleNamespace(risk_level=risk)


def test_summary_strips_markdown_heading_keeps_risk_prefix():
    text = "## Recomendação para 2026-06-26 — Endurance Z2 (ajustado)\n\nbla bla"
    out = _summary(text, _safety(RiskLevel.HIGH))
    assert out.startswith("[CONSERVATIVE ALTERNATIVE — high-risk state] ")
    assert "Recomendação para 2026-06-26 — Endurance Z2 (ajustado)" in out
    assert "##" not in out


def test_summary_low_risk_has_no_prefix():
    out = _summary("# Manter o planejado\nresto", _safety(RiskLevel.LOW))
    assert out == "Manter o planejado"


def test_summary_empty_text_falls_back():
    out = _summary("", _safety(RiskLevel.LOW))
    assert out == "Recommendation generated."


def test_first_meaningful_line_skips_blank_and_hash_only_lines():
    assert first_meaningful_line("\n#\n##  \n  Texto real\n") == "Texto real"
    assert first_meaningful_line(None) is None
    assert first_meaningful_line("plain") == "plain"
