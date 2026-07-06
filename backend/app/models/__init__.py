"""SQLAlchemy models. Importing this package registers all tables on Base."""
from app.models.base import Base
from app.models.athlete import Athlete, AthleteProfile, AthleteGoal, AthleteAvailability
from app.models.invite import InviteCode
from app.models.workout import (
    WorkoutCompleted,
    WorkoutPlanned,
    WorkoutStream,
    WorkoutInterval,
    ImportedFile,
)
from app.models.metrics import (
    FtpHistory,
    LoadMetric,
    RecoveryMetric,
    SubjectiveMetric,
    BodyMetric,
    PowerCurvePoint,
)
from app.models.race import Race, RaceResult, RaceAnalysis
from app.models.training_plan import TrainingPlan, TrainingBlock, TrainingWeek
from app.models.ai import (
    AiRecommendation,
    AiRecommendationEvidence,
    AiRecommendationFeedback,
    AiDecision,
    LlmCallLog,
)
from app.models.knowledge import KnowledgeDocument, Embedding, PromptTemplate
from app.models.audit import AuditLog
from app.models.garmin import GarminConnection

__all__ = [
    "Base",
    "Athlete",
    "AthleteProfile",
    "AthleteGoal",
    "AthleteAvailability",
    "InviteCode",
    "WorkoutCompleted",
    "WorkoutPlanned",
    "WorkoutStream",
    "WorkoutInterval",
    "ImportedFile",
    "FtpHistory",
    "LoadMetric",
    "RecoveryMetric",
    "SubjectiveMetric",
    "BodyMetric",
    "PowerCurvePoint",
    "Race",
    "RaceResult",
    "RaceAnalysis",
    "TrainingPlan",
    "TrainingBlock",
    "TrainingWeek",
    "AiRecommendation",
    "AiRecommendationEvidence",
    "AiRecommendationFeedback",
    "AiDecision",
    "LlmCallLog",
    "KnowledgeDocument",
    "Embedding",
    "PromptTemplate",
    "AuditLog",
    "GarminConnection",
]
