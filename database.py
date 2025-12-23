"""Database setup and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings

# Async engine for API layer
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    future=True,
)

# Sync engine for Alembic migrations and Scrapy pipelines
sync_engine = create_engine(
    settings.database_url_sync,
    echo=settings.environment == "development",
    future=True,
)

# Session makers
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

SessionLocal = sessionmaker(
    sync_engine,
    expire_on_commit=False,
)

# Base class for models
Base = declarative_base()


# Dependency for FastAPI
async def get_db():
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db():
    """Get sync database session (for Scrapy)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
