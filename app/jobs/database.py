from typing import Final, Protocol, final

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry


def _wal(connection: DBAPIConnection, record: ConnectionPoolEntry) -> None:
    record.info["journal_mode"] = "wal"
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


class Sessions(Protocol):
    """Source of database sessions."""

    def session(self) -> AsyncSession: ...

    async def close(self) -> None: ...


@final
class Database:
    """Async connection pool to the database named by the settings."""

    __slots__ = ("_engine", "_factory")

    def __init__(self, url: str) -> None:
        engine: AsyncEngine = create_async_engine(
            url, connect_args={"timeout": 30} if url.startswith("sqlite") else {}
        )
        if url.startswith("sqlite"):
            event.listen(engine.sync_engine, "connect", _wal)
        self._engine: Final = engine
        self._factory: Final = async_sessionmaker(engine, expire_on_commit=False)

    def session(self) -> AsyncSession:
        return self._factory()

    async def close(self) -> None:
        await self._engine.dispose()
