"""Enumerations used across models and schemas."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ATHLETE = "ATHLETE"
    COACH = "COACH"  # future: read-only access to linked athletes


class ImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class FileFormat(str, enum.Enum):
    FIT = "FIT"
    TCX = "TCX"
    GPX = "GPX"
    CSV = "CSV"
    JSON = "JSON"


class WorkoutType(str, enum.Enum):
    ENDURANCE = "ENDURANCE"
    TEMPO = "TEMPO"
    SWEET_SPOT = "SWEET_SPOT"
    THRESHOLD = "THRESHOLD"
    VO2MAX = "VO2MAX"
    ANAEROBIC = "ANAEROBIC"
    SPRINT = "SPRINT"
    RECOVERY = "RECOVERY"
    RACE = "RACE"
    OTHER = "OTHER"


class BlockType(str, enum.Enum):
    BASE = "BASE"
    BUILD = "BUILD"
    PEAK = "PEAK"
    TAPER = "TAPER"
    RECOVERY = "RECOVERY"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class RecommendationDecision(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class GoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    ABANDONED = "ABANDONED"


class GarminConnectionStatus(str, enum.Enum):
    AWAITING_MFA = "AWAITING_MFA"
    CONNECTED = "CONNECTED"
    NEEDS_REAUTH = "NEEDS_REAUTH"
    DISCONNECTED = "DISCONNECTED"
