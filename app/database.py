"""
Database engine, async session factory, and initialization.
"""
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'xpersona.db'}")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables if they don't exist."""
    # Ensure data directory exists for SQLite
    if "sqlite" in DATABASE_URL:
        os.makedirs(BASE_DIR / "data", exist_ok=True)
    from app.models import Profile, ProfileRequest  # noqa: F401 — import so SQLAlchemy sees the models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Dependency injection for FastAPI routes."""
    async with async_session() as session:
        yield session
