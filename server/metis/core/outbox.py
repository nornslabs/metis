"""Transactional outbox for domain events.

Services record a :class:`DomainEvent` with :func:`add_event` inside their own
transaction, so the event exists only if the change commits. The
``outbox_relay`` job calls :func:`relay_once`, which hands unpublished events to
the handlers registered with :func:`on_event` and marks them published.

Delivery is at least once: a handler may see the same event again (for example
when another handler of the same event failed and the event retried), so
handlers must be idempotent, keyed on ``event.id``. Concurrent relays never
deliver the same event at the same time (``FOR UPDATE SKIP LOCKED``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.ids import uuid7
from metis.core.logging import get_logger
from metis.core.models import Base

RELAY_BATCH_SIZE = 100
MAX_ATTEMPTS = 10

logger = get_logger(__name__)


class DomainEventType(StrEnum):
    """Domain events modules publish to each other through the outbox."""

    IDEA_SUBMITTED = "IdeaSubmitted"
    SCORE_COMPUTED = "ScoreComputed"
    SPEC_CONFIRMED = "SpecConfirmed"
    PLAN_READY = "PlanReady"
    EXPORT_FINISHED = "ExportFinished"
    MARKET_SIGNAL_DETECTED = "MarketSignalDetected"


class DomainEvent(BaseModel):
    """Envelope for one domain event; ``id`` keys idempotent handling."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid7)
    workspace_id: UUID
    type: DomainEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class OutboxRow(Base):
    """``core.outbox`` row. No RLS: the relay reads across workspaces."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "core"}

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def add_event(session: AsyncSession, event: DomainEvent) -> None:
    """Add ``event`` to the caller's transaction. Never commits or flushes."""
    session.add(
        OutboxRow(
            id=event.id,
            workspace_id=event.workspace_id,
            type=event.type.value,
            payload=event.payload,
            created_at=event.created_at,
            attempts=0,
        )
    )


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventRegistry:
    """Maps each event type to its handlers, in registration order."""

    def __init__(self) -> None:
        self._handlers: MappingProxyType[DomainEventType, tuple[Handler, ...]] = (
            MappingProxyType({})
        )

    def on(self, event_type: DomainEventType) -> Callable[[Handler], Handler]:
        """Decorator: register an async handler for ``event_type``."""

        def register(handler: Handler) -> Handler:
            current = self._handlers.get(event_type, ())
            self._handlers = MappingProxyType(
                {**self._handlers, event_type: (*current, handler)}
            )
            return handler

        return register

    def handlers_for(self, event_type: DomainEventType) -> tuple[Handler, ...]:
        return self._handlers.get(event_type, ())


default_registry = EventRegistry()
on_event = default_registry.on


class Outcome(StrEnum):
    """What one relay pass did with one event."""

    PUBLISHED = "published"
    FAILED = "failed"
    DEAD = "dead"


@dataclass(frozen=True)
class RelayResult:
    """Counts from one relay pass. ``dead`` events hit :data:`MAX_ATTEMPTS`."""

    published: int = 0
    failed: int = 0
    dead: int = 0


async def relay_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    registry: EventRegistry = default_registry,
    batch_size: int = RELAY_BATCH_SIZE,
) -> RelayResult:
    """Deliver one batch of unpublished events, oldest first.

    Rows stay locked until the pass commits, so a concurrent relay skips them.
    """
    async with sessionmaker() as session, session.begin():
        rows = (
            await session.scalars(
                select(OutboxRow)
                .where(OutboxRow.published_at.is_(None), OutboxRow.attempts < MAX_ATTEMPTS)
                .order_by(OutboxRow.created_at, OutboxRow.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        outcomes = [await _deliver(session, row, registry) for row in rows]

    return RelayResult(
        published=outcomes.count(Outcome.PUBLISHED),
        failed=outcomes.count(Outcome.FAILED),
        dead=outcomes.count(Outcome.DEAD),
    )


def _to_event(row: OutboxRow) -> DomainEvent:
    return DomainEvent(
        id=row.id,
        workspace_id=row.workspace_id,
        type=DomainEventType(row.type),
        payload=row.payload,
        created_at=row.created_at,
    )


async def _deliver(session: AsyncSession, row: OutboxRow, registry: EventRegistry) -> Outcome:
    """Decode ``row`` and run every handler for it; record the outcome on the row.

    Decoding sits inside the failure path so an undecodable row (for example an
    unknown type after an enum rename) counts attempts and dies like any other
    failure instead of aborting the batch on every pass.
    """
    try:
        event = _to_event(row)
        for handler in registry.handlers_for(event.type):
            await handler(event)
    except Exception:
        return await _record_failure(session, row)

    await session.execute(
        update(OutboxRow).where(OutboxRow.id == row.id).values(published_at=func.now())
    )
    return Outcome.PUBLISHED


async def _record_failure(session: AsyncSession, row: OutboxRow) -> Outcome:
    attempts = row.attempts + 1
    await session.execute(update(OutboxRow).where(OutboxRow.id == row.id).values(attempts=attempts))
    context = {
        "event_id": str(row.id),
        "event_type": row.type,
        "workspace_id": str(row.workspace_id),
        "attempts": attempts,
    }
    if attempts >= MAX_ATTEMPTS:
        logger.error("outbox.event_dead", exc_info=True, **context)
        return Outcome.DEAD
    logger.warning("outbox.event_failed", exc_info=True, **context)
    return Outcome.FAILED
