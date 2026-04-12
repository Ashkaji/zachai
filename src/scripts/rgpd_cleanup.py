"""
RGPD Cleanup Script — Story 12.1 AC 5
Anonymizes users whose deletion grace period (48h) has expired.
Usage: python rgpd_cleanup.py
"""
import os
import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete, text
from urllib.parse import quote_plus

# We need the models. Since this is a script in src/scripts, we can import from src.api.fastapi.main
# But to avoid complex imports in a standalone script, I'll redefine the necessary parts or 
# assume we can import if PYTHONPATH is set.
# For robustness in this environment, I'll use raw SQL or simple re-definitions.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
# Docker network alias is 'postgres'
DATABASE_URL = f"postgresql+asyncpg://{quote_plus(POSTGRES_USER)}:{quote_plus(POSTGRES_PASSWORD)}@postgres:5432/zachai"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

PLATFORM_SALT = os.environ.get("PLATFORM_SALT", "zachai-default-salt")

def anonymize_id(sub: str) -> str:
    h = hashlib.sha256(f"{sub}{PLATFORM_SALT}".encode()).hexdigest()[:16]
    return f"deleted_user_{h}"

async def run_cleanup():
    async with AsyncSessionLocal() as session:
        # 1. Find users to delete
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        # Using raw SQL for simplicity in a script that might not have the full ORM context
        res = await session.execute(
            text("SELECT user_id FROM user_consents WHERE deletion_pending_at < :cutoff"),
            {"cutoff": cutoff}
        )
        users = res.scalars().all()
        
        if not users:
            logger.info("No users found for cleanup.")
            return

        for user_id in users:
            logger.info(f"Cleaning up user: {user_id}")
            anon_id = anonymize_id(user_id)
            
            # A. Anonymize Assignments
            await session.execute(
                text("UPDATE assignments SET transcripteur_id = :anon WHERE transcripteur_id = :sub"),
                {"anon": anon_id, "sub": user_id}
            )
            
            # B. Anonymize Audit Logs
            await session.execute(
                text("UPDATE audit_logs SET user_id = 'ANONYMOUS' WHERE user_id = :sub"),
                {"sub": user_id}
            )
            
            # B2. Anonymize Projects
            await session.execute(
                text("UPDATE projects SET manager_id = :anon WHERE manager_id = :sub"),
                {"anon": anon_id, "sub": user_id}
            )
            
            # C. Purge Golden Set (source=frontend_correction)
            # Find audios assigned to user
            r_audios = await session.execute(
                text("SELECT audio_id FROM assignments WHERE transcripteur_id = :anon"),
                {"anon": anon_id}
            )
            audio_ids = r_audios.scalars().all()
            if audio_ids:
                await session.execute(
                    text("DELETE FROM golden_set_entries WHERE audio_id = ANY(:ids) AND source = 'frontend_correction'"),
                    {"ids": audio_ids}
                )
            
            # D. Delete Consent record
            await session.execute(
                text("DELETE FROM user_consents WHERE user_id = :sub"),
                {"sub": user_id}
            )
            
            logger.info(f"User {user_id} anonymized as {anon_id}")
            
        await session.commit()
        logger.info("Cleanup cycle completed.")

if __name__ == "__main__":
    asyncio.run(run_cleanup())
