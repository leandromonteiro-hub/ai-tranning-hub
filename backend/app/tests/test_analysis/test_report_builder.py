"""TDD tests for report_builder — pure unit tests with synthetic inputs.

These tests verify:
1. All 6 PT-BR sections are present in the generated markdown.
2. Every block/taper section includes the evidence string from ST2.3.
3. No results-promising language appears in the report.
4. twin_seed dict contains required keys.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.analysis.ftp_estimator import FtpEstimate
from app.services.analysis.methodology import Block, Race, TaperWindow
from app.services.analysis.profile_metrics import (
    BestPowerMarks,
    DerivedZones,
    IntensityDistribution,
    MeasuredZones,
    ModalitySplit,
    PowerMark,
    SportShare,
    VolumeTrend,
    WeeklyVolumePoint,
    WeeklyVolumeTrend,
    WorkoutTypeShare,
)
from app.services.analysis.report_builder import build_profile_report

# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

_ATHLETE_NAME = "João Ciclista"
_WEIGHT_KG = 72.0

_BLOCKS = [
    Block(
        start=date(2024, 1, 1),
        end=date(2024, 2, 28),
        block_type="base",
        evidence="CTL 40.0→65.0 de 2024-01-01 a 2024-02-28 (8 sem); TSS médio 550/sem; TSS total 4400 em 56 dias",
    ),
    Block(
        start=date(2024, 3, 1),
        end=date(2024, 4, 14),
        block_type="build",
        evidence="CTL 65.0→85.0 de 2024-03-01 a 2024-04-14 (6 sem); TSS médio 720/sem; TSS total 4320 em 45 dias",
    ),
    Block(
        start=date(2024, 4, 15),
        end=date(2024, 4, 21),
        block_type="taper",
        evidence="CTL 85.0→82.0 de 2024-04-15 a 2024-04-21 (1 sem); TSS médio 320/sem; TSS total 320 em 7 dias",
    ),
]

_RACES = [
    Race(
        date=date(2024, 4, 21),
        name="XCO Campeonato Regional",
        evidence="keyword:campeonato em nome='XCO Campeonato Regional' (tss=180)",
    ),
]

_TAPERS = [
    TaperWindow(
        race_date=date(2024, 4, 21),
        ctl_start=88.0,
        ctl_race=82.0,
        atl_race=75.0,
        tsb_race=7.0,
        weekly_tss_trend=[620.0, 480.0, 320.0],
        evidence="CTL 88.0→82.0 (-6.0) nos 21 dias antes de 2024-04-21; ATL=75.0, TSB=7.0 no dia da prova; TSS semanal: [620.0, 480.0, 320.0]",
    ),
]

_COMMENT_TERMS = [("z2", 45), ("limiar", 30), ("intervalo", 20), ("sprint", 10)]

_FTP_TIMELINE = [
    FtpEstimate(
        valid_from=date(2024, 1, 1),
        valid_to=date(2024, 4, 21),
        ftp_watts=275.0,
        method="estimate_pc20",
    ),
]

_VOLUME_TREND = WeeklyVolumeTrend(
    weeks=[
        WeeklyVolumePoint(iso_year=2024, iso_week=1, hours=8.0, tss=550, distance_km=200, workout_count=5),
        WeeklyVolumePoint(iso_year=2024, iso_week=2, hours=9.5, tss=650, distance_km=230, workout_count=6),
    ],
    trend=VolumeTrend(mean_hours=8.75, mean_tss=600, direction="rising", weeks_analysed=2),
)

_MODALITY = ModalitySplit(
    by_sport=[
        SportShare(sport="cycling", workout_count=80, total_hours=120.0, pct_workouts=0.90, pct_hours=0.92),
        SportShare(sport="strength", workout_count=8, total_hours=10.0, pct_workouts=0.09, pct_hours=0.07),
    ],
    by_workout_type=[
        WorkoutTypeShare(workout_type="ENDURANCE", workout_count=50, total_hours=80.0, pct_workouts=0.56, pct_hours=0.61),
        WorkoutTypeShare(workout_type="INTERVAL", workout_count=30, total_hours=50.0, pct_workouts=0.34, pct_hours=0.38),
    ],
    total_workouts=88,
    total_hours=130.0,
)

_INTENSITY = IntensityDistribution(
    measured=MeasuredZones(
        source="trainingpeaks",
        pwr_zone_minutes=[120, 200, 180, 100, 60, 20, 5, 0, 0, 0],
        hr_zone_minutes=[150, 180, 100, 50, 20, 0, 0, 0, 0, 0],
        workouts_with_power_zones=75,
        workouts_with_hr_zones=80,
    ),
    derived=DerivedZones(
        source="derived_if",
        z1_hours=95.0,
        z2_hours=25.0,
        z3_hours=10.0,
        unclassified_hours=5.0,
        z1_pct=0.73,
        z2_pct=0.19,
        z3_pct=0.08,
        distribution_label="pyramidal",
        workouts_classified=80,
    ),
)

_POWER_MARKS = BestPowerMarks(
    marks=[
        PowerMark(duration_s=5, watts=950.0, w_per_kg=13.19),
        PowerMark(duration_s=60, watts=530.0, w_per_kg=7.36),
        PowerMark(duration_s=300, watts=380.0, w_per_kg=5.28),
        PowerMark(duration_s=1200, watts=310.0, w_per_kg=4.31),
        PowerMark(duration_s=3600, watts=270.0, w_per_kg=3.75),
    ],
    weight_kg=72.0,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build() -> tuple[str, dict]:
    """Run build_profile_report with the synthetic fixtures."""
    return build_profile_report(
        athlete_name=_ATHLETE_NAME,
        weight_kg=_WEIGHT_KG,
        volume_trend=_VOLUME_TREND,
        modality=_MODALITY,
        intensity=_INTENSITY,
        power_marks=_POWER_MARKS,
        blocks=_BLOCKS,
        races=_RACES,
        tapers=_TAPERS,
        comment_terms=_COMMENT_TERMS,
        ftp_timeline=_FTP_TIMELINE,
    )


# ---------------------------------------------------------------------------
# Section presence tests (RED: module doesn't exist yet)
# ---------------------------------------------------------------------------

class TestReportSections:
    """All 6 required PT-BR sections must be present."""

    def test_section_perfil_do_atleta(self) -> None:
        report, _ = _build()
        assert "Perfil do atleta" in report

    def test_section_engenharia_reversa(self) -> None:
        report, _ = _build()
        assert "Engenharia reversa da metodologia" in report

    def test_section_pre_prova_taper(self) -> None:
        report, _ = _build()
        assert "Metodologia pré-prova" in report

    def test_section_melhores_marcas(self) -> None:
        report, _ = _build()
        assert "Melhores marcas" in report

    def test_section_correlacao_treinador(self) -> None:
        report, _ = _build()
        assert "Correlação com decisões do treinador" in report

    def test_section_resumo_executivo(self) -> None:
        report, _ = _build()
        assert "Resumo executivo" in report


class TestEvidenceCitation:
    """Every block/taper section must cite the evidence string."""

    def test_block_evidence_cited_base(self) -> None:
        report, _ = _build()
        # The base block evidence should appear somewhere in the methodology section
        assert "CTL 40.0→65.0" in report

    def test_block_evidence_cited_build(self) -> None:
        report, _ = _build()
        assert "CTL 65.0→85.0" in report

    def test_block_evidence_cited_taper_block(self) -> None:
        report, _ = _build()
        assert "CTL 85.0→82.0" in report

    def test_taper_window_evidence_cited(self) -> None:
        report, _ = _build()
        # The taper window evidence string must appear in the pre-race section
        assert "ATL=75.0, TSB=7.0" in report

    def test_race_evidence_cited(self) -> None:
        report, _ = _build()
        assert "XCO Campeonato Regional" in report


class TestNoResultsPromising:
    """No results-promising language may appear."""

    _FORBIDDEN = [
        "garantimos", "garantido", "garantiremos",
        "você vai", "você irá",
        "certamente", "com certeza",
        "resultado garantido",
        "podemos prometer",
        "irá melhorar",
        "vai melhorar",
    ]

    def test_no_guarantee_language(self) -> None:
        report, _ = _build()
        report_lower = report.lower()
        for phrase in self._FORBIDDEN:
            assert phrase not in report_lower, f"Forbidden phrase found: '{phrase}'"


# ---------------------------------------------------------------------------
# twin_seed structure tests
# ---------------------------------------------------------------------------

class TestTwinSeed:
    """twin_seed dict must contain all required keys with correct types."""

    def test_twin_seed_has_power_curve_bests(self) -> None:
        _, seed = _build()
        assert "power_curve_bests" in seed
        assert isinstance(seed["power_curve_bests"], dict)

    def test_twin_seed_has_ftp_timeline(self) -> None:
        _, seed = _build()
        assert "ftp_timeline" in seed
        assert isinstance(seed["ftp_timeline"], list)
        assert len(seed["ftp_timeline"]) > 0

    def test_twin_seed_has_intensity_split(self) -> None:
        _, seed = _build()
        assert "intensity_split" in seed
        split = seed["intensity_split"]
        assert "z1_pct" in split
        assert "z2_pct" in split
        assert "z3_pct" in split
        assert "label" in split

    def test_twin_seed_has_block_summary(self) -> None:
        _, seed = _build()
        assert "block_summary" in seed
        assert isinstance(seed["block_summary"], list)
        assert len(seed["block_summary"]) > 0

    def test_twin_seed_has_best_marks(self) -> None:
        _, seed = _build()
        assert "best_marks" in seed
        assert isinstance(seed["best_marks"], dict)

    def test_twin_seed_has_data_richness(self) -> None:
        _, seed = _build()
        assert "data_richness" in seed
        richness = seed["data_richness"]
        assert "total_workouts" in richness
        assert "weeks_analysed" in richness
        assert "power_zone_workouts" in richness

    def test_twin_seed_ftp_serialisable(self) -> None:
        """FTP entries must use string dates (JSON-serialisable)."""
        import json
        _, seed = _build()
        # Should not raise
        json.dumps(seed)

    def test_twin_seed_block_has_type_and_dates(self) -> None:
        _, seed = _build()
        block = seed["block_summary"][0]
        assert "block_type" in block
        assert "start" in block
        assert "end" in block


# ---------------------------------------------------------------------------
# Content coherence tests
# ---------------------------------------------------------------------------

class TestContentCoherence:
    """Check that athlete name, FTP value, and key metrics appear."""

    def test_athlete_name_in_report(self) -> None:
        report, _ = _build()
        assert _ATHLETE_NAME in report

    def test_ftp_value_in_report(self) -> None:
        report, _ = _build()
        # FTP 275 should appear somewhere
        assert "275" in report

    def test_power_marks_5s_in_report(self) -> None:
        report, _ = _build()
        assert "950" in report

    def test_intensity_label_in_report(self) -> None:
        report, _ = _build()
        # pyramidal distribution label should appear
        assert "piramidal" in report.lower() or "pyramidal" in report.lower()

    def test_report_is_portuguese(self) -> None:
        """Basic check that the report contains common Portuguese words."""
        report, _ = _build()
        portuguese_markers = ["atleta", "treinador", "semana", "potência"]
        matches = sum(1 for w in portuguese_markers if w in report.lower())
        assert matches >= 3, f"Report doesn't appear to be in Portuguese; found {matches}/4 markers"


# ---------------------------------------------------------------------------
# Methodology signals in twin_seed
# ---------------------------------------------------------------------------

def test_twin_seed_includes_methodology_signals():
    from datetime import date
    from app.services.analysis.methodology import Race, TaperWindow
    from app.services.analysis import report_builder as rb

    # Reusa o helper interno diretamente com objetos mínimos:
    races = [Race(date=date(2025, 5, 4), name="XCO Cup", evidence="keyword:xco")]
    tapers = [TaperWindow(race_date=date(2025, 5, 4), ctl_start=80.0, ctl_race=78.0,
                          atl_race=55.0, tsb_race=23.0,
                          weekly_tss_trend=[600.0, 450.0, 300.0],
                          evidence="CTL -2, TSB +23 no dia da prova")]
    comment_terms = [("sweet", 12), ("limiar", 9), ("z2", 7)]

    seed = rb._build_twin_seed_methodology(races, tapers, comment_terms,
                                           power_curve_bests={}, blocks=[])

    assert seed["races"][0]["name"] == "XCO Cup"
    assert seed["tapers"][0]["tsb_race"] == 23.0
    assert seed["tapers"][0]["weekly_tss_trend"] == [600.0, 450.0, 300.0]
    assert seed["coach_terms"][:1] == [["sweet", 12]]
    assert "n_blocks" in seed["periodization_summary"]
