"""SQLAlchemy models, base class, and mixins for Metis.

Provides:
- Base: declarative base with naming conventions
- TenantMixin: UUIDv7 id, workspace_id, created_at, updated_at
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def generate_uuid() -> str:
    """Generate a UUID string.

    Currently uses uuid4; should be replaced with uuid7 when available.
    """
    return str(uuid4())


# Type alias for naming convention (matches SQLAlchemy's expected type)
_NamingConvention = dict[str, Callable[..., str]]


def _ix(table_name: str, column_0_name: str) -> str:
    return f"ix_{table_name}_{column_0_name}"


def _pk(table_name: str) -> str:
    return f"pk_{table_name}"


def _fk(
    table_name: str, column_0_name: str, referred_table_name: str
) -> str:
    return f"fk_{table_name}_{column_0_name}_{referred_table_name}"


def _uq(table_name: str, column_0_name: str) -> str:
    return f"uq_{table_name}_{column_0_name}"


def _ck(table_name: str, constraint_name: str) -> str:
    return f"ck_{table_name}_{constraint_name}"


NAMING_CONVENTION: _NamingConvention = {
    "ix": _ix,
    "pk": _pk,
    "fk": _fk,
    "uq": _uq,
    "ck": _ck,
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