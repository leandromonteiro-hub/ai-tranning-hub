"""Seed the bootstrap admin + 2 demo athletes (the validation cohort) + FTP.

Idempotent: safe to run multiple times. Run with `make seed`.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from app.bootstrap import ensure_admin, ensure_pgvector
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.metrics import FtpHistory
from app.repositories.athlete_repo import AthleteRepository

DEMO_ATHLETES = [
    ("athlete1@athletehub.example.com", "athlete1_pwd", "Atleta Um", 280),
    ("athlete2@athletehub.example.com", "athlete2_pwd", "Atleta Dois", 240),
]


async def main() -> None:
    await ensure_pgvector()
    await ensure_admin()
    async with AsyncSessionLocal() as session:
        repo = AthleteRepository(session)
        for email, pwd, name, ftp in DEMO_ATHLETES:
            existing = await repo.get_by_email(email)
            if existing:
                continue
            athlete = Athlete(
                email=email,
                hashed_password=hash_password(pwd),
                full_name=name,
                role=Role.ATHLETE,
                tenant_id=f"tenant_{uuid.uuid4().hex[:12]}",
            )
            await repo.add(athlete)
            session.add(
                FtpHistory(
                    athlete_id=athlete.id,
                    created_by=athlete.id,
                    ftp_watts=ftp,
                    valid_from=date(date.today().year, 1, 1),
                    method="manual_seed",
                )
            )
        await session.commit()
    print("Seed complete: admin + 2 demo athletes + FTP.")


if __name__ == "__main__":
    asyncio.run(main())
