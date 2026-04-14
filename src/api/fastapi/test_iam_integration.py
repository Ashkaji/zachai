import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from main import Base, ManagerMembership
from sqlalchemy import select
from datetime import datetime

@pytest.fixture
async def db_engine():
    """In-memory SQLite engine for integration testing"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    """Async session for database integration testing"""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.mark.asyncio
class TestManagerMembershipIntegration:
    """[P0] Integration tests for ManagerMembership DB operations"""

    async def test_persist_membership(self, db_session):
        """[P1] Should persist a new membership and handle timestamp generation"""
        m = ManagerMembership(manager_id="manager-id-123", member_id="user-id-456")
        db_session.add(m)
        await db_session.commit()
        
        stmt = select(ManagerMembership).where(ManagerMembership.member_id == "user-id-456")
        result = await db_session.execute(stmt)
        persisted = result.scalar_one_or_none()
        assert persisted is not None
        assert persisted.manager_id == "manager-id-123"
        assert isinstance(persisted.created_at, datetime)

    async def test_duplicate_member_constraint(self, db_session):
        """[P0] Should enforce unique member_id (one user -> one manager)"""
        m1 = ManagerMembership(manager_id="manager-1", member_id="user-1")
        db_session.add(m1)
        await db_session.commit()
        
        m2 = ManagerMembership(manager_id="manager-2", member_id="user-1")
        db_session.add(m2)
        # Unique constraint on member_id should trigger IntegrityError
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_multiple_members_for_one_manager(self, db_session):
        """[P1] Should allow a manager to have multiple members in their perimeter"""
        m1 = ManagerMembership(manager_id="manager-1", member_id="user-1")
        m2 = ManagerMembership(manager_id="manager-1", member_id="user-2")
        db_session.add_all([m1, m2])
        await db_session.commit()
        
        stmt = select(ManagerMembership).where(ManagerMembership.manager_id == "manager-1")
        result = await db_session.execute(stmt)
        members = result.scalars().all()
        assert len(members) == 2
        assert {m.member_id for m in members} == {"user-1", "user-2"}
