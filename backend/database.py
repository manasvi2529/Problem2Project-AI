"""
Problem2Project AI — Database Setup (Async SQLAlchemy + SQLite)
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings


settings.setup_directories()

db_url = settings.DATABASE_URL or f"sqlite+aiosqlite:///{(settings.DATA_DIR / 'problem2project.db').as_posix()}"

engine = create_async_engine(
    db_url,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},  # SQLite specific
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency: yield a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables. Called on startup."""
    async with engine.begin() as conn:
        from backend.models import user, project, research, approval, audit  # noqa
        await conn.run_sync(Base.metadata.create_all)
