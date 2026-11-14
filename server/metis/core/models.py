"""SQLAlchemy models, base class, and mixins for Metis.

Provides:
- Base: declarative base with naming conventions
- TenantMixin: UUIDv7 id, workspace_id, created_at, updated_at
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from metis.helpers.ids import uuid7


def generate_uuid() -> str:
    """Generate a UUIDv7 string."""
    return str(uuid7())


# SQLAlchemy expects %-format templates here; callables are not interpolated.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with naming conventions.

    All models inherit from this to get consistent naming.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantMixin:
    """Mixin for tenant-isolated tables.

    Provides:
    - id: UUID primary key (server-generated)
    - workspace_id: UUID foreign key to identity.workspaces
    - created_at: timestamp with timezone
    - updated_at: timestamp with timezone
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
        comment="Primary key",
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="FK to identity.workspaces.id, used for RLS",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )