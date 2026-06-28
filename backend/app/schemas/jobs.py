"""Schema for the async job-status endpoint."""
from __future__ import annotations

from pydantic import BaseModel


class JobStatus(BaseModel):
    task_id: str
    state: str  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
