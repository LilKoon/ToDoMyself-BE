import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Ensure test uses SQLite in-memory
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-jwt-key-2026"

import app.core.database as db_module
from app.core.database import Base

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)

test_sessionmaker = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Monkeypatch database engine and sessionmaker
db_module.engine = test_engine
db_module.AsyncSessionLocal = test_sessionmaker

@pytest_asyncio.fixture(autouse=True, scope="function")
async def init_test_database():
    async with test_engine.begin() as conn:
        from app.models.user import User
        from app.models.todo import Todo, Subtask
        from app.models.notification import UserNotificationSettings, NotificationLog
        from app.models.otp import EmailOTP
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
