"""Async SQLAlchemy engine lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


from pathlib import Path

from rootlens.db.ssl import build_ssl_context


class Database:
    """Own the application's async database engine and session factory."""

    def __init__(
        self,
        database_url: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 10,
        pool_timeout: float = 10.0,
        ca_cert_file: str | Path | None = None,
        ssl_mode: str | None = None,
    ) -> None:
        connect_args: dict[str, object] = {}
        ssl_context = build_ssl_context(ca_cert_file=ca_cert_file, ssl_mode=ssl_mode)
        if ssl_context is not None:
            connect_args["ssl"] = ssl_context

        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            connect_args=connect_args,
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
