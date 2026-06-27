"""The daily-workout prompt carries the reverse-engineered methodology section."""
from __future__ import annotations

from app.services.ai import prompts


def test_render_includes_methodology_section():
    out = prompts.render_daily_workout(
        twin="TWIN", safety="SAFE", evidence="EV", knowledge="KN",
        question="Qual treino hoje?", profile="PROFILE",
        methodology="Distribuição piramidal: Z1 70% / Z2 27% / Z3 3%",
    )
    assert "PROFILE" in out
    assert "Distribuição piramidal: Z1 70% / Z2 27% / Z3 3%" in out
    assert "reverse-engineered" in out  # the section is labeled


def test_render_methodology_defaults_to_nd():
    out = prompts.render_daily_workout(
        twin="T", safety="S", evidence="E", knowledge="K", question="q",
    )
    assert "{methodology}" not in out  # placeholder is filled
    assert "n/d" in out


def test_active_template_version_bumped():
    version, body = prompts.ACTIVE_TEMPLATES["daily_workout"]
    assert version == 4
    assert "{methodology}" in body


def test_render_includes_feedback_section():
    from app.services.ai import prompts
    out = prompts.render_daily_workout(
        twin="T", safety="S", evidence="E", knowledge="K",
        question="q",
        feedback="Feedback recente (3 avaliações, nota média 4.0)",
    )
    assert "Feedback recente (3 avaliações, nota média 4.0)" in out
    assert "{feedback}" not in out          # placeholder preenchido
    assert prompts.ACTIVE_TEMPLATES["daily_workout"][0] == 4


def test_render_feedback_defaults_to_nd():
    from app.services.ai import prompts
    out = prompts.render_daily_workout(twin="T", safety="S", evidence="E",
                                       knowledge="K", question="q")
    assert "{feedback}" not in out
