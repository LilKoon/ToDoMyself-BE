from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Create async engine for PostgreSQL (or SQLite fallback)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        # Import all models before creating tables
        from app.models.user import User
        from app.models.todo import Todo, Subtask
        from app.models.notification import UserNotificationSettings, NotificationLog
        from app.models.otp import EmailOTP
        
        await conn.run_sync(Base.metadata.create_all)


        # Ensure start_date column exists on existing PostgreSQL/SQLite tables
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE todos ADD COLUMN IF NOT EXISTS start_date TIMESTAMPTZ;"))
        except Exception:
            pass

        logger.info("Database tables initialized successfully.")

