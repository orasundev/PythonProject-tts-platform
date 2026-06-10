"""
Shared pytest fixtures.
Uses a dedicated TEST_DATABASE_URL; runs Alembic migrations before the suite.
"""

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.utils.crypto import hash_password

settings = get_settings()

TEST_DB_URL = settings.test_database_url or settings.database_url.replace(
    "/tts_platform", "/tts_platform_test"
)

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()  # isolate each test


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired to the test DB session."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def free_plan(db: AsyncSession) -> Plan:
    plan = Plan(
        id=uuid.uuid4(),
        name="free",
        monthly_char_limit=10_000,
        max_api_keys=1,
        allows_ssml=False,
        allows_all_voices=False,
        allows_webhooks=False,
        allows_priority_queue=False,
        file_retention_days=7,
        price_cents=0,
    )
    db.add(plan)
    await db.commit()
    return plan


@pytest_asyncio.fixture
async def pro_plan(db: AsyncSession) -> Plan:
    plan = Plan(
        id=uuid.uuid4(),
        name="pro",
        monthly_char_limit=500_000,
        max_api_keys=10,
        allows_ssml=True,
        allows_all_voices=True,
        allows_webhooks=False,
        allows_priority_queue=False,
        file_retention_days=30,
        price_cents=2900,
    )
    db.add(plan)
    await db.commit()
    return plan


@pytest_asyncio.fixture
async def test_org(db: AsyncSession, free_plan: Plan) -> Organisation:
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        plan_id=free_plan.id,
    )
    db.add(org)
    await db.commit()
    return org


@pytest_asyncio.fixture
async def test_user(db: AsyncSession, test_org: Organisation) -> User:
    user = User(
        id=uuid.uuid4(),
        organisation_id=test_org.id,
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("password123"),
        role="owner",
        is_email_verified=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: User) -> AsyncClient:
    """Client pre-authenticated with a valid JWT cookie."""
    from app.utils.crypto import create_access_token
    token = create_access_token(str(test_user.id))
    client.cookies.set("access_token", token)
    return client
