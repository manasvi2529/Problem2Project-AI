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
    """Create all tables, migrate schema additions, and seed default workspace user on startup."""
    async with engine.begin() as conn:
        from backend.models import user, project, research, approval, audit, deployment  # noqa
        await conn.run_sync(Base.metadata.create_all)

        # Automatic lightweight schema migration for existing SQLite databases
        def _migrate_schema(connection):
            try:
                # Check approvals table columns
                res = connection.exec_driver_sql("PRAGMA table_info(approvals)").fetchall()
                approval_cols = {row[1] for row in res}
                new_approval_cols = [
                    ("expires_at", "DATETIME"),
                    ("consumed", "BOOLEAN DEFAULT 0"),
                    ("consumed_at", "DATETIME"),
                    ("action_params", "JSON"),
                    ("action_params_hash", "VARCHAR(64)"),
                ]
                for col_name, col_type in new_approval_cols:
                    if col_name not in approval_cols:
                        connection.exec_driver_sql(f"ALTER TABLE approvals ADD COLUMN {col_name} {col_type}")

                # Check users table columns
                user_res = connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()
                user_cols = {row[1] for row in user_res}
                if "github_oauth_state" not in user_cols:
                    connection.exec_driver_sql("ALTER TABLE users ADD COLUMN github_oauth_state VARCHAR(150)")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Schema migration warning: %s", e)

        await conn.run_sync(_migrate_schema)

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
