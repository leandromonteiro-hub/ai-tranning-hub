"""Content hashing and duplicate detection helpers."""
from __future__ import annotations

import hashlib


def content_hash(data: bytes) -> str:
    """SHA-256 of the raw file bytes — the primary dedup key."""
    return hashlib.sha256(data).hexdigest()


def activity_fingerprint(started_at_iso: str, duration_s: int | None) -> str:
    """Secondary fingerprint (start time + duration) for cross-format dedup."""
    raw = f"{started_at_iso}|{duration_s or 0}"
    return hashlib.sha256(raw.encode()).hexdigest()
