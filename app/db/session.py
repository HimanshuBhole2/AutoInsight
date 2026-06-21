from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
async_session_factory: async_sessionmaker[AsyncSession]


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=(settings.app_env == "development"),
        )
    return _engine


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=_get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


async_session_factory = _make_session_factory()
