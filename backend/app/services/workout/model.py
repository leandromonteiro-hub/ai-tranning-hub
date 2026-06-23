"""Canonical, format-agnostic structured workout model.

Targets are expressed as fractions of FTP (e.g. 0.90 == 90% FTP). The absolute
FTP used at generation time is carried in ``ftp_watts`` so any exporter can
resolve watts without re-querying. This is the reusable core for future
exporters (.zwo, etc.) and the day-by-day calendar.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Target(BaseModel):
    type: Literal["power_pct_ftp", "open"]
    low: float | None = None   # fraction of FTP, e.g. 0.88
    high: float | None = None


class Step(BaseModel):
    intensity: Literal["warmup", "active", "rest", "cooldown"]
    duration_s: int
    target: Target
    cadence_low: int | None = None
    cadence_high: int | None = None
    note: str | None = None


class Repeat(BaseModel):
    count: int
    steps: list[Step]


class StructuredWorkout(BaseModel):
    name: str
    sport: Literal["cycling"] = "cycling"
    elements: list[Step | Repeat]
    estimated_tss: float | None = None
    ftp_watts: float | None = None
