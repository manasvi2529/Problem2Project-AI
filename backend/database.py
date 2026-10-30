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
    """Create all tables and seed default workspace user on startup."""
    async with engine.begin() as conn:
        from backend.models import user, project, research, approval, audit  # noqa
        await conn.run_sync(Base.metadata.create_all)

    # Seed default developer user for zero-friction access
    async with AsyncSessionLocal() as session:
        from backend.models.user import User
        from backend.security import hash_password
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.email == "developer@problempilot.ai"))
        if not res.scalar_one_or_none():
            dev_user = User(
                id="default-dev-user-0001",
                email="developer@problempilot.ai",
                username="developer",
                hashed_password=hash_password("ProblemPilot123!"),
                full_name="Principal Architect",
                operating_mode="hybrid",
            )
            session.add(dev_user)
            await session.commit()
