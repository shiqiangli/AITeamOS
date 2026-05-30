"""
Shared Kernel — Outbox Pattern 实现 (arch.md §6.1)。

Transactional Outbox: 领域事件与业务数据在同一事务中写入 outbox 表，
由 OutboxRelay 异步投递到 Kafka。保证 At-least-once 投递语义。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from .events import VersionedDomainEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OutboxEntry — outbox 表行模型
# ---------------------------------------------------------------------------


@dataclass
class OutboxEntry:
    """Represents a single row in the ``outbox`` table."""

    id: UUID = field(default_factory=uuid4)
    event_type: str = ""
    partition_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    global_seq: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None


# ---------------------------------------------------------------------------
# OutboxWriter — 同事务写入
# ---------------------------------------------------------------------------


class TransactionLike(Protocol):
    """Minimal protocol for a database transaction (asyncpg-compatible)."""

    async def execute(self, query: str, *args: Any) -> Any: ...

    async def fetchrow(self, query: str, *args: Any) -> Any: ...


class OutboxWriter:
    """Write domain events into the outbox table within the same DB transaction.

    Usage::

        async with db.transaction() as tx:
            await repo.save(aggregate, tx)
            await outbox_writer.write(event, partition_key="member-123", tx=tx)
    """

    INSERT_SQL = """
        INSERT INTO outbox (id, event_type, partition_key, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING global_seq
    """

    async def write(
        self,
        event: VersionedDomainEvent,
        *,
        partition_key: str,
        tx: TransactionLike,
    ) -> OutboxEntry:
        """Persist a domain event into the outbox within the given transaction.

        Returns the OutboxEntry with the assigned global_seq.
        """
        entry = OutboxEntry(
            event_type=event.event_type,
            partition_key=partition_key,
            payload=event.model_dump(mode="json"),
        )
        row = await tx.fetchrow(
            self.INSERT_SQL,
            entry.id,
            entry.event_type,
            entry.partition_key,
            json.dumps(entry.payload),
        )
        if row:
            entry.global_seq = row["global_seq"]
        logger.debug(
            "OutboxWriter: wrote event %s (seq=%d, partition=%s)",
            entry.event_type,
            entry.global_seq,
            entry.partition_key,
        )
        return entry


# ---------------------------------------------------------------------------
# KafkaProducerLike — Kafka 抽象 (可 mock)
# ---------------------------------------------------------------------------


class KafkaProducerLike(Protocol):
    """Minimal Kafka producer interface for outbox relay."""

    async def send(
        self, topic: str, value: bytes, key: str | None = None
    ) -> None: ...


# ---------------------------------------------------------------------------
# OutboxRelay — 轮询 + 投递 (简化版，Stage 4.6 加固)
# ---------------------------------------------------------------------------


class OutboxRelay:
    """Poll unpublished outbox entries and publish to Kafka.

    This is the simplified single-instance version for M1.
    Multi-instance sharded relay with advisory locks is implemented
    in Stage 4.6 (arch.md §6.1).
    """

    SELECT_UNPUBLISHED = """
        SELECT id, event_type, partition_key, payload, global_seq
        FROM outbox
        WHERE published_at IS NULL
        ORDER BY global_seq
        LIMIT $1
    """

    MARK_PUBLISHED = """
        UPDATE outbox SET published_at = now() WHERE id = ANY($1::uuid[])
    """

    def __init__(
        self,
        *,
        db: Any,
        kafka_producer: KafkaProducerLike,
        topic: str = "domain-events",
        batch_size: int = 100,
        poll_interval: float = 0.5,
    ):
        self._db = db
        self._kafka = kafka_producer
        self._topic = topic
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._stopped = False

    async def run(self) -> None:
        """Main relay loop — poll, publish, mark."""
        logger.info("OutboxRelay started (topic=%s, batch=%d)", self._topic, self._batch_size)
        while not self._stopped:
            published = await self._poll_and_publish()
            if published == 0:
                await asyncio.sleep(self._poll_interval)

    async def _poll_and_publish(self) -> int:
        """Fetch a batch of unpublished entries, publish, and mark."""
        rows = await self._db.fetch(self.SELECT_UNPUBLISHED, self._batch_size)
        if not rows:
            return 0

        ids: list[UUID] = []
        for row in rows:
            try:
                await self._kafka.send(
                    self._topic,
                    value=json.dumps(row["payload"]).encode(),
                    key=row["partition_key"],
                )
                ids.append(row["id"])
            except Exception:
                logger.exception(
                    "OutboxRelay: failed to publish event %s (id=%s)",
                    row["event_type"],
                    row["id"],
                )
                break  # stop batch on first failure, retry next cycle

        if ids:
            await self._db.execute(self.MARK_PUBLISHED, ids)
            logger.debug("OutboxRelay: published %d events", len(ids))

        return len(ids)

    def stop(self) -> None:
        """Signal the relay to stop."""
        self._stopped = True


# ---------------------------------------------------------------------------
# ShardedOutboxRelay — 多实例 Advisory Lock 分片 (Stage 4.6, arch.md §6.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelayCheckpoint:
    """高水位持久化：断点续传。"""

    shard_id: int = 0
    last_published_seq: int = 0
    instance_id: str = ""


class ShardedOutboxRelay:
    """Multi-instance OutboxRelay with advisory-lock sharding.

    Features (plan.md §4.6.1):
    - Advisory Lock 分片：按 partition_key hash 分配 shard
    - 背压机制：Kafka 不可用时暂停拉取
    - 高水位持久化：断点续传
    """

    SELECT_SHARD_UNPUBLISHED = """
        SELECT id, event_type, partition_key, payload, global_seq
        FROM outbox
        WHERE published_at IS NULL
          AND abs(hashtext(partition_key)) % $1 = $2
          AND global_seq > $3
        ORDER BY global_seq
        LIMIT $4
    """

    MARK_PUBLISHED = """
        UPDATE outbox SET published_at = now() WHERE id = ANY($1::uuid[])
    """

    ACQUIRE_LOCK = "SELECT pg_try_advisory_lock($1)"
    RELEASE_LOCK = "SELECT pg_advisory_unlock($1)"

    SAVE_CHECKPOINT = """
        INSERT INTO outbox_relay_checkpoints (shard_id, last_published_seq, instance_id, updated_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (shard_id) DO UPDATE
        SET last_published_seq = $2, instance_id = $3, updated_at = now()
    """

    LOAD_CHECKPOINT = """
        SELECT last_published_seq FROM outbox_relay_checkpoints WHERE shard_id = $1
    """

    LOCK_BASE_MAGIC = 900_000  # advisory lock namespace for outbox relay

    def __init__(
        self,
        *,
        db: Any,
        kafka_producer: KafkaProducerLike,
        shard_id: int = 0,
        num_shards: int = 1,
        instance_id: str = "default",
        topic: str = "domain-events",
        batch_size: int = 100,
        poll_interval: float = 0.5,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
    ):
        self._db = db
        self._kafka = kafka_producer
        self._shard_id = shard_id
        self._num_shards = num_shards
        self._instance_id = instance_id
        self._topic = topic
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._stopped = False
        self._high_watermark: int = 0
        self._backoff_current = backoff_initial
        self._kafka_available = True
        self._consecutive_failures = 0
        self._lock_acquired = False

    @property
    def high_watermark(self) -> int:
        return self._high_watermark

    @property
    def kafka_available(self) -> bool:
        return self._kafka_available

    @property
    def shard_id(self) -> int:
        return self._shard_id

    async def try_acquire_lock(self) -> bool:
        """Try to acquire advisory lock for this shard."""
        lock_key = self.LOCK_BASE_MAGIC + self._shard_id
        row = await self._db.fetchrow(self.ACQUIRE_LOCK, lock_key)
        acquired = row is not None and row[0] is True
        self._lock_acquired = acquired
        if acquired:
            logger.info(
                "ShardedOutboxRelay: acquired lock for shard %d (instance=%s)",
                self._shard_id,
                self._instance_id,
            )
        else:
            logger.warning(
                "ShardedOutboxRelay: failed to acquire lock for shard %d",
                self._shard_id,
            )
        return acquired

    async def release_lock(self) -> None:
        """Release advisory lock for this shard."""
        if self._lock_acquired:
            lock_key = self.LOCK_BASE_MAGIC + self._shard_id
            await self._db.execute(self.RELEASE_LOCK, lock_key)
            self._lock_acquired = False
            logger.info("ShardedOutboxRelay: released lock for shard %d", self._shard_id)

    async def load_checkpoint(self) -> int:
        """Load persisted high-watermark for resume."""
        row = await self._db.fetchrow(self.LOAD_CHECKPOINT, self._shard_id)
        if row:
            self._high_watermark = row["last_published_seq"]
            logger.info(
                "ShardedOutboxRelay: loaded checkpoint seq=%d for shard %d",
                self._high_watermark,
                self._shard_id,
            )
        return self._high_watermark

    async def save_checkpoint(self) -> None:
        """Persist current high-watermark."""
        await self._db.execute(
            self.SAVE_CHECKPOINT,
            self._shard_id,
            self._high_watermark,
            self._instance_id,
        )

    async def run(self) -> None:
        """Main sharded relay loop."""
        acquired = await self.try_acquire_lock()
        if not acquired:
            logger.error("ShardedOutboxRelay: cannot start without lock for shard %d", self._shard_id)
            return

        await self.load_checkpoint()
        logger.info(
            "ShardedOutboxRelay: started shard=%d/%d (instance=%s, watermark=%d)",
            self._shard_id,
            self._num_shards,
            self._instance_id,
            self._high_watermark,
        )

        try:
            while not self._stopped:
                if not self._kafka_available:
                    # 背压：Kafka 不可用时指数退避
                    logger.warning("ShardedOutboxRelay: Kafka unavailable, backing off %.1fs", self._backoff_current)
                    await asyncio.sleep(self._backoff_current)
                    self._backoff_current = min(self._backoff_current * 2, self._backoff_max)
                    continue

                published = await self._poll_and_publish()
                if published == 0:
                    await asyncio.sleep(self._poll_interval)
                else:
                    self._backoff_current = self._backoff_initial  # reset on success
        finally:
            await self.save_checkpoint()
            await self.release_lock()

    async def _poll_and_publish(self) -> int:
        """Fetch shard-specific batch, publish, mark, and advance watermark."""
        rows = await self._db.fetch(
            self.SELECT_SHARD_UNPUBLISHED,
            self._num_shards,
            self._shard_id,
            self._high_watermark,
            self._batch_size,
        )
        if not rows:
            return 0

        ids: list[UUID] = []
        last_seq = self._high_watermark
        for row in rows:
            try:
                await self._kafka.send(
                    self._topic,
                    value=json.dumps(row["payload"]).encode(),
                    key=row["partition_key"],
                )
                ids.append(row["id"])
                last_seq = max(last_seq, row["global_seq"])
                self._kafka_available = True
                self._consecutive_failures = 0
            except Exception:
                self._consecutive_failures += 1
                self._kafka_available = False
                logger.exception(
                    "ShardedOutboxRelay: Kafka send failed (shard=%d, consecutive=%d)",
                    self._shard_id,
                    self._consecutive_failures,
                )
                break

        if ids:
            await self._db.execute(self.MARK_PUBLISHED, ids)
            self._high_watermark = last_seq
            await self.save_checkpoint()
            logger.debug(
                "ShardedOutboxRelay: published %d events (shard=%d, watermark=%d)",
                len(ids),
                self._shard_id,
                self._high_watermark,
            )

        return len(ids)

    def stop(self) -> None:
        """Signal the relay to stop."""
        self._stopped = True
