"""
Shared Kernel — BaseRepository 抽象 + asyncpg 连接池管理。

提供仓储基类和数据库连接池工厂，供各 Bounded Context
基础设施层继承使用。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Generic, TypeVar
from uuid import UUID

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Connection Pool 管理
# ---------------------------------------------------------------------------


class DatabasePool:
    """Thin wrapper around asyncpg connection pool.

    Provides ``transaction()`` context manager and convenience query methods.
    In tests, this can be replaced with a mock pool.
    """

    def __init__(self, pool: Any):
        """
        Args:
            pool: An asyncpg.Pool instance (or compatible mock).
        """
        self._pool = pool

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """Yield an asyncpg transaction object for use in ``with`` blocks.

        Usage::

            async with db.transaction() as tx:
                await tx.execute("INSERT ...", ...)
                await tx.execute("UPDATE ...", ...)
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def close(self) -> None:
        await self._pool.close()


async def create_pool(
    dsn: str,
    *,
    min_size: int = 5,
    max_size: int = 20,
) -> DatabasePool:
    """Create an asyncpg connection pool wrapped in DatabasePool."""
    try:
        import asyncpg

        pool = await asyncpg.create_pool(
            dsn, min_size=min_size, max_size=max_size
        )
        logger.info("DatabasePool: created (min=%d, max=%d)", min_size, max_size)
        return DatabasePool(pool)
    except ImportError:
        raise RuntimeError(
            "asyncpg is required for DatabasePool. Install with: pip install asyncpg"
        )


# ---------------------------------------------------------------------------
# BaseRepository — 仓储抽象基类
# ---------------------------------------------------------------------------


class BaseRepository(ABC, Generic[T]):
    """Abstract base repository providing common patterns.

    Subclasses implement specific CRUD operations for their aggregate root.
    All write operations should be performed within a transaction and
    accompanied by an Outbox event write (arch.md 纪律 #3).

    Type parameter T is the aggregate root type.
    """

    def __init__(self, db: DatabasePool):
        self._db = db

    @abstractmethod
    async def get_by_id(self, id: UUID, *, tx: Any = None) -> T | None:
        """Load an aggregate by its primary key."""
        ...

    @abstractmethod
    async def save(self, aggregate: T, *, tx: Any = None) -> None:
        """Persist an aggregate (insert or update)."""
        ...

    async def lock_for_update(self, id: UUID, *, tx: Any) -> T | None:
        """Load an aggregate with a row-level lock (SELECT ... FOR UPDATE).

        Must be called within a transaction context.
        """
        return await self.get_by_id(id, tx=tx)
