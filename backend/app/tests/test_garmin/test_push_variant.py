"""Push do Garmin usa o treino da variante escolhida no aceite."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.jobs.garmin_job import _do_push_recommendation
from app.models.ai import AiRecommendation
from app.models.athlete import Athlete
from app.models.enums import GarminConnectionStatus, Role
from app.models.garmin import GarminConnection
from app.services.garmin import token_store
from app.services.garmin.fake_client import FakeGarminClient

pytestmark = pytest.mark.asyncio

_AI_WO: dict = {
    "name": "IA",
    "sport": "cycling",
    "elements": [
        {"intensity": "active", "duration_s": 3600, "target": {"type": "power_pct_ftp", "low": 0.6, "high": 0.68}}
    ],
    "ftp_watts": 250.0,
}
_TRAD_WO: dict = {
    "name": "Tradicional",
    "sport": "cycling",
    "elements": [
        {"intensity": "active", "duration_s": 5400, "target": {"type": "power_pct_ftp", "low": 0.62, "high": 0.68}}
    ],
    "ftp_watts": 250.0,
}


@pytest_asyncio.fixture
async def env(engine, monkeypatch):
    """Committed athlete + CONNECTED GarminConnection + Fernet key so is_enabled()=True."""
    monkeypatch.setattr(
        token_store.settings,
        "garmin_token_key",
        Fernet.generate_key().decode(),
    )
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        athlete = Athlete(
            email="push-variant@example.com",
            hashed_password=hash_password("pw"),
            full_name="PushVariant",
            role=Role.ATHLETE,
            tenant_id="tenant_push_variant",
        )
        s.add(athlete)
        await s.flush()
        conn = GarminConnection(
            athlete_id=athlete.id,
            status=GarminConnectionStatus.CONNECTED,
            encrypted_token=None,
        )
        s.add(conn)
        await s.commit()
        aid = str(athlete.id)
        tenant_id = athlete.tenant_id
    return maker, aid, tenant_id


async def _make_rec(maker, aid: str, chosen: str | None) -> str:
    """Commit a recommendation with both workout variants and return its str(id)."""
    payload = {"structured_workout": _AI_WO, "methodology_workout": _TRAD_WO}
    if chosen is not None:
        payload["chosen_variant"] = chosen
    async with maker() as s:
        rec = AiRecommendation(
            athlete_id=uuid.UUID(aid),
            summary="push variant test",
            target_date=date(2026, 7, 7),
            payload=payload,
        )
        s.add(rec)
        await s.commit()
        return str(rec.id)


async def test_push_uses_methodology_when_chosen(env):
    """chosen_variant='methodology' → the pushed workout is the traditional-method one."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(maker, aid, "methodology")
    fake = FakeGarminClient()

    result = await _do_push_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "ok"
    assert len(fake.pushed) == 1
    pushed_workout = fake.pushed[0][0]
    assert pushed_workout.name == "Tradicional"


async def test_push_uses_ai_by_default(env):
    """No chosen_variant (or 'ai') → the pushed workout is the AI one (unchanged default)."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(maker, aid, None)
    fake = FakeGarminClient()

    result = await _do_push_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "ok"
    assert len(fake.pushed) == 1
    pushed_workout = fake.pushed[0][0]
    assert pushed_workout.name == "IA"
