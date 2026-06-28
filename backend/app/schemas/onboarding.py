"""Schemas for the TrainingPeaks onboarding endpoint (T4.3)."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class IngestionSummary(BaseModel):
    """Summary of the IngestionReport (from dataclasses.asdict)."""

    workouts_completed: int = 0
    workouts_planned: int = 0
    rest_days: int = 0
    recovery_days: int = 0
    subjective_days: int = 0
    duplicates_skipped: int = 0
    merged_from_csv: int = 0
    period_start: date | None = None
    period_end: date | None = None
    pct_power: float = 0.0
    pct_hr: float = 0.0
    pct_hrv: float = 0.0
    unmapped_metric_types: dict[str, Any] = Field(default_factory=dict)
    anomalies: list[str] = Field(default_factory=list)


class RichnessSummary(BaseModel):
    """Subset of RichnessIndex used in the onboarding response."""

    years_covered: float = 0.0
    n_workouts: int = 0
    pct_power: float = 0.0
    pct_hr: float = 0.0
    pct_hrv: float = 0.0
    pct_sleep: float = 0.0
    score: float = 0.0
    label: str = "baixa"


class ProfileSummary(BaseModel):
    """Compact profile summary from generate_and_persist_profile (report_md excluded)."""

    n_workouts: int = 0
    weeks: int = 0
    ftp_recent: float | None = None
    n_blocks: int = 0
    n_races: int = 0
    excluded_power_streams: int = 0
    richness: dict[str, Any] = Field(default_factory=dict)


class TrainingPeaksOnboardingResponse(BaseModel):
    """Response schema for POST /imports/trainingpeaks-export.

    Fields:
        ingestion: counts and coverage from import_athlete_folder (IngestionReport).
        profile_task_id: id of the async profile-regeneration Celery task; the
            client polls GET /jobs/{id} and fetches the profile via
            /athletes/me/intelligence on SUCCESS.
    """

    ingestion: IngestionSummary
    profile_task_id: str
