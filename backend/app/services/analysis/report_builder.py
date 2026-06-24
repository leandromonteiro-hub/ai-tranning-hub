"""Build a PT-BR markdown profile report and compact twin_seed dict.

This module is **pure** — no DB, no I/O.  It takes pre-computed analysis
results from ST2.1–ST2.3 and returns:
  - a PT-BR markdown string with all 6 required sections
  - a compact ``twin_seed`` dict suitable for persistence in ``AthleteProfile.twin_seed``

The function is therefore fully unit-testable with synthetic inputs.

Public API
----------
build_profile_report(
    athlete_name, weight_kg,
    volume_trend, modality, intensity, power_marks,
    blocks, races, tapers, comment_terms, ftp_timeline
) -> tuple[str, dict]

Design decisions
----------------
- Every block/taper claim cites the ``evidence`` field from ST2.3 verbatim.
- Tone: continuidade respeitosa, sem crítica gratuita, sem prometer resultados.
- The markdown uses ``##`` sections so it renders nicely in GitHub and mkdocs.
- twin_seed is built purely from the input objects — no DB access.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.analysis.ftp_estimator import FtpEstimate
from app.services.analysis.methodology import Block, Race, TaperWindow
from app.services.analysis.profile_metrics import (
    BestPowerMarks,
    IntensityDistribution,
    ModalitySplit,
    WeeklyVolumeTrend,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DURATION_LABELS: dict[int, str] = {
    5: "5 s",
    60: "1 min",
    300: "5 min",
    1200: "20 min",
    3600: "60 min",
}

_BLOCK_TYPE_PT: dict[str, str] = {
    "base": "Base",
    "build": "Construção",
    "peak": "Pico",
    "taper": "Afunilamento (Taper)",
    "recovery": "Recuperação",
}

_DISTRIBUTION_PT: dict[str, str] = {
    "polarized": "Polarizado",
    "pyramidal": "Piramidal",
    "sweet_spot": "Sweet Spot / Limiar",
    "mixed": "Misto",
}


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _fmt_date_iso(d: date | None) -> str:
    if d is None:
        return "atual"
    return d.isoformat()


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_perfil(
    athlete_name: str,
    weight_kg: float | None,
    volume_trend: WeeklyVolumeTrend,
    modality: ModalitySplit,
    ftp_timeline: list[FtpEstimate],
) -> str:
    lines: list[str] = []
    lines.append(f"## Perfil do atleta — {athlete_name}\n")

    # Weight
    if weight_kg:
        lines.append(f"- **Peso registrado:** {weight_kg:.1f} kg")

    # Volume
    if volume_trend.trend:
        t = volume_trend.trend
        lines.append(
            f"- **Volume médio semanal:** {t.mean_hours:.1f} h/sem "
            f"({t.mean_tss:.0f} TSS/sem) — tendência **{_direction_pt(t.direction)}** "
            f"ao longo de {t.weeks_analysed} semanas analisadas"
        )

    # Modality
    if modality.by_sport:
        top = modality.by_sport[0]
        lines.append(
            f"- **Modalidade principal:** {top.sport.capitalize()} "
            f"({top.pct_workouts * 100:.0f}% dos treinos, "
            f"{top.pct_hours * 100:.0f}% do volume em horas)"
        )
    lines.append(
        f"- **Total de treinos no período:** {modality.total_workouts} "
        f"({modality.total_hours:.0f} h total)"
    )

    # FTP timeline summary
    if ftp_timeline:
        latest = ftp_timeline[-1]
        lines.append(
            f"- **FTP estimado mais recente:** {latest.ftp_watts:.0f} W "
            f"(método: {latest.method}; período: "
            f"{_fmt_date(latest.valid_from)} → {_fmt_date_iso(latest.valid_to)})"
        )
        if weight_kg and weight_kg > 0:
            wkg = latest.ftp_watts / weight_kg
            lines.append(f"  - W/kg estimado: **{wkg:.2f} W/kg**")

    lines.append(
        "\n> *Nota: FTP estimado a partir da curva de potência (0,95 × melhor esforço "
        "de 20 min). Sem registros de teste formal de FTP no histórico importado.*"
    )
    return "\n".join(lines)


def _direction_pt(d: str) -> str:
    return {"rising": "crescente", "falling": "decrescente", "stable": "estável"}.get(d, d)


def _section_metodologia(blocks: list[Block]) -> str:
    lines: list[str] = []
    lines.append("## Engenharia reversa da metodologia\n")
    lines.append(
        "Análise inferida a partir da progressão de CTL/ATL/TSB e TSS semanal. "
        "Cada bloco detectado é acompanhado da evidência numérica que sustenta a classificação.\n"
    )

    if not blocks:
        lines.append("*Dados insuficientes de carga para detectar blocos de treinamento.*")
        return "\n".join(lines)

    for blk in blocks:
        label = _BLOCK_TYPE_PT.get(blk.block_type, blk.block_type.capitalize())
        lines.append(f"### Bloco: {label} ({_fmt_date(blk.start)} – {_fmt_date(blk.end)})\n")
        lines.append(f"**Evidência:** {blk.evidence}\n")

    return "\n".join(lines)


def _section_pre_prova(races: list[Race], tapers: list[TaperWindow]) -> str:
    lines: list[str] = []
    lines.append("## Metodologia pré-prova (taper)\n")

    if not races:
        lines.append("*Nenhuma prova detectada no histórico importado.*")
        return "\n".join(lines)

    # Map taper windows by race date
    taper_by_date: dict[date, TaperWindow] = {t.race_date: t for t in tapers}

    for race in races:
        lines.append(f"### Prova: {race.name or 'Prova sem nome'} — {_fmt_date(race.date)}\n")
        lines.append(f"**Detecção:** {race.evidence}\n")

        tw = taper_by_date.get(race.date)
        if tw:
            lines.append("**Janela pré-prova (21 dias):**\n")
            lines.append(f"**Evidência:** {tw.evidence}\n")
            lines.append(
                f"- CTL inicial: {tw.ctl_start:.1f} → CTL no dia da prova: {tw.ctl_race:.1f}"
            )
            lines.append(
                f"- ATL no dia da prova: {tw.atl_race:.1f} | "
                f"TSB no dia da prova: {tw.tsb_race:.1f}"
            )
            if tw.weekly_tss_trend:
                lines.append(
                    f"- Progressão TSS semanal: {' → '.join(str(int(v)) for v in tw.weekly_tss_trend)}"
                )
        else:
            lines.append("*Sem dados de carga nos 21 dias anteriores à prova.*")

    return "\n".join(lines)


def _section_melhores_marcas(power_marks: BestPowerMarks, ftp_timeline: list[FtpEstimate]) -> str:
    lines: list[str] = []
    lines.append("## Melhores marcas e padrões de potência\n")
    lines.append(
        "Baseado na curva de potência all-time derivada dos streams de potência importados "
        "(dado medido).\n"
    )

    if not power_marks.marks:
        lines.append("*Sem dados de potência suficientes para calcular marcas.*")
        return "\n".join(lines)

    lines.append("| Duração | Potência (W) | W/kg |")
    lines.append("|---------|-------------|------|")
    for mark in power_marks.marks:
        dur_label = _DURATION_LABELS.get(mark.duration_s, f"{mark.duration_s}s")
        wkg_str = f"{mark.w_per_kg:.2f}" if mark.w_per_kg is not None else "—"
        lines.append(f"| {dur_label} | {mark.watts:.0f} W | {wkg_str} |")

    if ftp_timeline:
        latest = ftp_timeline[-1]
        lines.append(f"\n**FTP estimado:** {latest.ftp_watts:.0f} W ({latest.method})")

    return "\n".join(lines)


def _section_correlacao(
    comment_terms: list[tuple[str, int]],
    intensity: IntensityDistribution,
) -> str:
    lines: list[str] = []
    lines.append("## Correlação com decisões do treinador (camada de confiança)\n")
    lines.append(
        "Esta seção apresenta observações baseadas em evidência sobre padrões recorrentes "
        "nos comentários do treinador e na distribuição de intensidade. "
        "As observações são descritivas — não prescritivas.\n"
    )

    # Intensity distribution
    derived = intensity.derived
    measured = intensity.measured
    dist_label = _DISTRIBUTION_PT.get(derived.distribution_label, derived.distribution_label)
    lines.append("### Distribuição de intensidade (dado derivado)\n")
    lines.append(
        f"- Classificação derivada do IF (Fator de Intensidade): **{dist_label}**"
    )
    lines.append(
        f"  - Z1 (baixa): {derived.z1_pct * 100:.1f}% | "
        f"Z2 (limiar): {derived.z2_pct * 100:.1f}% | "
        f"Z3 (alta): {derived.z3_pct * 100:.1f}%"
    )
    lines.append(
        f"  - {derived.workouts_classified} treinos com IF válido dos "
        f"{derived.workouts_classified + int(derived.unclassified_hours)} analisados"
    )
    lines.append(
        f"\n- Zonas de potência TrainingPeaks (dado medido, {measured.workouts_with_power_zones} "
        f"treinos com dado de zona):"
    )
    total_pwr_min = sum(measured.pwr_zone_minutes)
    if total_pwr_min > 0:
        for i, mins in enumerate(measured.pwr_zone_minutes):
            if mins > 0:
                pct = mins / total_pwr_min * 100
                lines.append(f"  - Z{i+1}: {mins} min ({pct:.1f}%)")

    # Coach comments
    if comment_terms:
        lines.append("\n### Termos recorrentes nos comentários do treinador\n")
        lines.append(
            "Frequência de termos nos comentários do treinador (após remoção de stopwords):\n"
        )
        lines.append("| Termo | Ocorrências |")
        lines.append("|-------|------------|")
        for term, count in comment_terms[:15]:
            lines.append(f"| {term} | {count} |")
        lines.append(
            "\n> *Padrões de linguagem observados — interpretação qualitativa, "
            "não conclusão definitiva.*"
        )

    return "\n".join(lines)


def _section_resumo_executivo(
    athlete_name: str,
    weight_kg: float | None,
    volume_trend: WeeklyVolumeTrend,
    modality: ModalitySplit,
    intensity: IntensityDistribution,
    power_marks: BestPowerMarks,
    blocks: list[Block],
    races: list[Race],
    ftp_timeline: list[FtpEstimate],
) -> str:
    lines: list[str] = []
    lines.append("## Resumo executivo (1 página)\n")

    # Period
    if volume_trend.weeks:
        first_w = volume_trend.weeks[0]
        last_w = volume_trend.weeks[-1]
        lines.append(
            f"**Período analisado:** semana ISO {first_w.iso_year}-W{first_w.iso_week:02d} "
            f"a {last_w.iso_year}-W{last_w.iso_week:02d} "
            f"({volume_trend.trend.weeks_analysed if volume_trend.trend else len(volume_trend.weeks)} semanas)\n"
        )

    # FTP
    if ftp_timeline:
        latest = ftp_timeline[-1]
        wkg_line = ""
        if weight_kg and weight_kg > 0:
            wkg_line = f" ({latest.ftp_watts / weight_kg:.2f} W/kg)"
        lines.append(f"**FTP estimado:** {latest.ftp_watts:.0f} W{wkg_line} — inferido, sem teste formal registrado\n")

    # Volume
    if volume_trend.trend:
        t = volume_trend.trend
        lines.append(
            f"**Volume:** média de {t.mean_hours:.1f} h/sem "
            f"({t.mean_tss:.0f} TSS/sem) — tendência {_direction_pt(t.direction)}\n"
        )

    # Blocks
    block_types = {}
    for blk in blocks:
        block_types[blk.block_type] = block_types.get(blk.block_type, 0) + 1
    if block_types:
        block_summary_str = "; ".join(
            f"{_BLOCK_TYPE_PT.get(k, k)}: {v}" for k, v in block_types.items()
        )
        lines.append(f"**Blocos detectados:** {block_summary_str}\n")

    # Races
    if races:
        race_names = ", ".join(r.name or "Prova" for r in races[:5])
        lines.append(f"**Provas detectadas:** {race_names}\n")

    # Power
    if power_marks.marks:
        marks_20min = next((m for m in power_marks.marks if m.duration_s == 1200), None)
        if marks_20min:
            wkg_str = f" | {marks_20min.w_per_kg:.2f} W/kg" if marks_20min.w_per_kg else ""
            lines.append(f"**Melhor 20 min:** {marks_20min.watts:.0f} W{wkg_str}\n")

    # Intensity label
    dist_label = _DISTRIBUTION_PT.get(intensity.derived.distribution_label, intensity.derived.distribution_label)
    lines.append(f"**Perfil de intensidade (derivado):** {dist_label}\n")

    # Modality
    if modality.by_sport:
        top = modality.by_sport[0]
        lines.append(
            f"**Modalidade:** {top.sport.capitalize()} predominante "
            f"({top.pct_hours * 100:.0f}% do volume)\n"
        )

    lines.append(
        "\n---\n"
        "> *Este relatório é uma análise descritiva baseada nos dados históricos importados. "
        "As inferências sobre metodologia do treinador são observações baseadas em evidência — "
        "não julgamentos. O objetivo é apoiar a continuidade do trabalho, "
        "respeitando o que foi construído.*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# twin_seed builder
# ---------------------------------------------------------------------------


def _build_twin_seed(
    power_marks: BestPowerMarks,
    ftp_timeline: list[FtpEstimate],
    intensity: IntensityDistribution,
    blocks: list[Block],
    modality: ModalitySplit,
    volume_trend: WeeklyVolumeTrend,
) -> dict:
    """Build a compact JSON-serialisable dict for AthleteProfile.twin_seed."""

    # Power curve bests: {duration_label: watts}
    power_curve_bests: dict[str, float] = {}
    for mark in power_marks.marks:
        label = _DURATION_LABELS.get(mark.duration_s, f"{mark.duration_s}s")
        power_curve_bests[label] = round(mark.watts, 1)

    # FTP timeline: list of {valid_from, valid_to, ftp_watts, method}
    ftp_list = [
        {
            "valid_from": _fmt_date_iso(est.valid_from),
            "valid_to": _fmt_date_iso(est.valid_to),
            "ftp_watts": round(est.ftp_watts, 1),
            "method": est.method,
        }
        for est in ftp_timeline
    ]

    # Intensity split
    derived = intensity.derived
    intensity_split = {
        "z1_pct": round(derived.z1_pct, 4),
        "z2_pct": round(derived.z2_pct, 4),
        "z3_pct": round(derived.z3_pct, 4),
        "label": derived.distribution_label,
        "source": "derived_if",
        "workouts_classified": derived.workouts_classified,
    }

    # Block summary: list of {block_type, start, end, evidence}
    block_summary = [
        {
            "block_type": blk.block_type,
            "start": _fmt_date_iso(blk.start),
            "end": _fmt_date_iso(blk.end),
            "evidence": blk.evidence,
        }
        for blk in blocks
    ]

    # Best marks: {duration_s: {watts, w_per_kg}}
    best_marks: dict[str, Any] = {}
    for mark in power_marks.marks:
        best_marks[str(mark.duration_s)] = {
            "watts": round(mark.watts, 1),
            "w_per_kg": round(mark.w_per_kg, 3) if mark.w_per_kg is not None else None,
        }

    # Data richness
    data_richness = {
        "total_workouts": modality.total_workouts,
        "total_hours": round(modality.total_hours, 1),
        "weeks_analysed": volume_trend.trend.weeks_analysed if volume_trend.trend else len(volume_trend.weeks),
        "power_zone_workouts": intensity.measured.workouts_with_power_zones,
        "hr_zone_workouts": intensity.measured.workouts_with_hr_zones,
    }

    return {
        "power_curve_bests": power_curve_bests,
        "ftp_timeline": ftp_list,
        "intensity_split": intensity_split,
        "block_summary": block_summary,
        "best_marks": best_marks,
        "data_richness": data_richness,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_profile_report(
    athlete_name: str,
    weight_kg: float | None,
    volume_trend: WeeklyVolumeTrend,
    modality: ModalitySplit,
    intensity: IntensityDistribution,
    power_marks: BestPowerMarks,
    blocks: list[Block],
    races: list[Race],
    tapers: list[TaperWindow],
    comment_terms: list[tuple[str, int]],
    ftp_timeline: list[FtpEstimate],
) -> tuple[str, dict]:
    """Assemble the PT-BR markdown profile report and the twin_seed dict.

    Parameters
    ----------
    athlete_name:
        Full name of the athlete (used in headers and report text).
    weight_kg:
        Athlete body weight in kg; used for W/kg calculations.  None-safe.
    volume_trend:
        Result of :func:`~app.services.analysis.profile_metrics.weekly_volume_trend`.
    modality:
        Result of :func:`~app.services.analysis.profile_metrics.modality_split`.
    intensity:
        Result of :func:`~app.services.analysis.profile_metrics.intensity_distribution`.
    power_marks:
        Result of :func:`~app.services.analysis.profile_metrics.best_power_marks`.
    blocks:
        List of :class:`~app.services.analysis.methodology.Block` from detect_blocks.
    races:
        List of :class:`~app.services.analysis.methodology.Race` from detect_races.
    tapers:
        List of :class:`~app.services.analysis.methodology.TaperWindow` from taper_windows.
    comment_terms:
        List of (term, count) from coach_comment_terms.
    ftp_timeline:
        List of :class:`~app.services.analysis.ftp_estimator.FtpEstimate`.

    Returns
    -------
    tuple[str, dict]
        (markdown_report, twin_seed_dict)
        - markdown_report: PT-BR markdown string with 6 sections.
        - twin_seed_dict: compact JSON-serialisable dict for persistence.
    """
    sections = [
        _section_perfil(athlete_name, weight_kg, volume_trend, modality, ftp_timeline),
        _section_metodologia(blocks),
        _section_pre_prova(races, tapers),
        _section_melhores_marcas(power_marks, ftp_timeline),
        _section_correlacao(comment_terms, intensity),
        _section_resumo_executivo(
            athlete_name, weight_kg, volume_trend, modality,
            intensity, power_marks, blocks, races, ftp_timeline
        ),
    ]

    report = "\n\n---\n\n".join(sections)

    twin_seed = _build_twin_seed(
        power_marks=power_marks,
        ftp_timeline=ftp_timeline,
        intensity=intensity,
        blocks=blocks,
        modality=modality,
        volume_trend=volume_trend,
    )

    return report, twin_seed
