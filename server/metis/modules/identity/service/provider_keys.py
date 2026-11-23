"""BYO provider keys (LLM, Exa): save, delete, use and test.

Every function takes the caller's ``AsyncSession``, flushes but never commits: the caller
owns the transaction. Each function sets the RLS context it needs (``app.user_id`` /
``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.llm import OpenAICompatibleClient
from metis.adapters.mcp.exa import ExaMcpClient
from metis.core import crypto
from metis.core.config import get_settings
from metis.core.db import WORKSPACE_SETTING
from metis.core.errors import (
    ProviderKeyNotFoundError,
    ProviderNotConfiguredError,
    UpstreamError,
    provider_not_configured,
)
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory
from metis.helpers.validation import validate_input
from metis.modules.identity import repo
from metis.modules.identity.dto import (
    ALLOW_LOCAL_HTTP,
    KeyReadiness,
    Membership,
    NewProviderKey,
    ProviderCredentials,
    ProviderKeyView,
    ProviderKind,
)
from metis.modules.identity.helpers.permissions import require_owner
from metis.modules.identity.helpers.views import key_view
from metis.modules.identity.models import ProviderKeyRow


@dataclass(frozen=True)
class KeyTestResult:
    """Outcome of ``test_key``: the key with its stored result, and the failure if any."""

    key: ProviderKeyView
    error: UpstreamError | None = None


async def set_key(
    session: AsyncSession,
    membership: Membership,
    kind: ProviderKind,
    value: str,
    base_url: str | None = None,
    model: str | None = None,
) -> ProviderKeyView:
    """Seal and save the workspace's key of ``kind``, replacing any previous one (owners only)."""
    require_owner(membership, "change provider keys")
    context = {ALLOW_LOCAL_HTTP: get_settings().is_development}
    new = validate_input(
        NewProviderKey, context, kind=kind, value=value, base_url=base_url, model=model
    )
    workspace_id = membership.workspace.id
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        row = await repo.provider_keys.upsert(
            session,
            workspace_id,
            new.kind,
            base_url=new.base_url,
            model=new.model,
            sealed=crypto.encrypt(new.value, workspace_id),
            masked=crypto.mask(new.value),
        )
    logger.info("provider_key.saved", kind=new.kind.value, version=row.version)
    return key_view(row)


async def delete_key(session: AsyncSession, membership: Membership, kind: ProviderKind) -> None:
    """Remove the workspace's key of ``kind`` (owners only); 404 if there is none."""
    require_owner(membership, "change provider keys")
    async with repo.rls.context(session, WORKSPACE_SETTING, membership.workspace.id):
        if not await repo.provider_keys.remove(session, membership.workspace.id, kind):
            raise ProviderKeyNotFoundError(f"No {kind.value} key is saved")
    logger.info("provider_key.deleted", kind=kind.value)


async def get_key_for_use(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> ProviderCredentials:
    """Decrypted credentials for a provider call.

    Only the LLM gateway and the Exa adapter call this; never return or log
    the result. Raises ``ProviderNotConfiguredError`` if no key is saved and
    ``SecretDecryptError`` if the stored key cannot be opened.
    """
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        row = await _saved_key(session, workspace_id, kind)
    return _credentials(row, workspace_id)


async def key_readiness(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> KeyReadiness:
    """Whether the workspace's key of ``kind`` is saved and passed its last test.

    Reads the row only: no decryption and no provider call.
    """
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        row = await repo.provider_keys.get(session, workspace_id, kind)
    if row is None:
        return KeyReadiness.NOT_CONFIGURED
    if row.last_test_ok is None:
        return KeyReadiness.NOT_TESTED
    return KeyReadiness.READY if row.last_test_ok else KeyReadiness.TEST_FAILED


async def test_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind, make_client: ClientFactory
) -> KeyTestResult:
    """Make one cheap call with the saved key and record the result.

    A provider failure is returned in ``KeyTestResult.error`` rather than
    raised, so the caller can commit the recorded result.
    """
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        row = await _saved_key(session, workspace_id, kind)
        error: UpstreamError | None = None
        try:
            await _check_provider(make_client, _credentials(row, workspace_id))
        except UpstreamError as exc:
            error = exc
        row = await repo.provider_keys.record_test(
            session, row.id, ok=error is None, tested_at=datetime.now(tz=UTC)
        )
    logger.info(
        "provider_key.tested",
        kind=kind.value,
        ok=error is None,
        reason=(error.meta or {}).get("reason") if error else None,
    )
    return KeyTestResult(key=key_view(row), error=error)


logger = get_logger(__name__)


async def _saved_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> ProviderKeyRow:
    """The saved key row; ``ProviderNotConfiguredError`` if there is none."""
    row = await repo.provider_keys.get(session, workspace_id, kind)
    if row is None:
        raise provider_not_configured(kind)
    return row


def _credentials(row: ProviderKeyRow, workspace_id: UUID) -> ProviderCredentials:
    api_key = crypto.decrypt(crypto.seal_from_json(row.sealed), workspace_id)
    return ProviderCredentials(
        kind=ProviderKind(row.kind), api_key=api_key, base_url=row.base_url, model=row.model
    )


async def _check_provider(make_client: ClientFactory, creds: ProviderCredentials) -> None:
    """One cheap provider call; raises ``UpstreamError`` if the key does not work."""
    if creds.kind is ProviderKind.EXA:
        await ExaMcpClient(make_client, creds.api_key).check()
        return
    if creds.base_url is None:  # unreachable: llm keys are saved with a base_url
        raise ProviderNotConfiguredError(
            "The llm key has no base_url; save it again", meta={"provider": ProviderKind.LLM.value}
        )
    await OpenAICompatibleClient(make_client, creds.base_url, creds.api_key).list_models()
