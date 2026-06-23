"""Validate the quality/sanity of a normalized activity before persistence."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ingestion.normalizer import NormalizedActivity


@dataclass
class QualityReport:
    is_valid: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_activity(act: NormalizedActivity) -> QualityReport:
    """Cheap, deterministic sanity checks. Errors block import; warnings don't."""
    errors: list[str] = []
    warnings: list[str] = []

    if act.started_at is None:
        errors.append("missing start time")
    if act.duration_s is not None and act.duration_s <= 0:
        errors.append("non-positive duration")
    if act.duration_s and act.duration_s > 24 * 3600:
        warnings.append("duration exceeds 24h — possible bad data")
    if act.avg_power is not None and not (0 <= act.avg_power <= 2000):
        warnings.append(f"avg_power out of plausible range: {act.avg_power}")
    if act.avg_hr is not None and not (20 <= act.avg_hr <= 230):
        warnings.append(f"avg_hr out of plausible range: {act.avg_hr}")
    if act.power_stream and any(p < 0 for p in act.power_stream):
        warnings.append("negative power samples present (clamped downstream)")

    return QualityReport(is_valid=not errors, warnings=warnings, errors=errors)
