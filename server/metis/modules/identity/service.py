"""Public API of the identity module: users, workspaces, membership, BYO
provider keys and workspace settings.

Every function takes the caller's ``AsyncSession``, flushes but never commits:
the caller owns the transaction. Each function sets the RLS context it needs
(``app.user_id`` / ``app.workspace_id``) and restores the caller's value after.
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
from metis.core.db import USER_SETTING, WORKSPACE_SETTING
from metis.core.errors import (
    AlreadyMemberError,
    ConflictError,
    EmailTakenError,
    MemberUserNotFoundError,
    PermissionDeniedError,
    ProviderKeyNotFoundError,
    ProviderNotConfiguredError,
    UpstreamError,
    WorkspaceNotFoundError,
)
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory
from metis.helpers.validation import validate_input
from metis.modules.identity import repo
from metis.modules.identity.models import ProviderKeyRow, WorkspaceSettingsRow
from metis.modules.identity.schemas import (
    ALLOW_LOCAL_HTTP,
    DEFAULT_MAX_STEPS,
    DEFAULT_RUN_BUDGET_USD,
    MemberRole,
    Membership,
    NewMember,
    NewProviderKey,
    ProviderCredentials,
    ProviderKeys,
    ProviderKeyView,
    ProviderKind,
    SettingsPatch,
    SettingsResponse,
    User,
    UserClaims,
    Workspace,
    WorkspaceName,
    WorkspaceSettingsView,
)

PERSONAL_WORKSPACE_NAME = "Personal"

logger = get_logger(__name__)


async def _add_owner(session: AsyncSession, workspace_id: UUID, user_id: UUID) -> None:
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        await repo.insert_member(session, workspace_id, user_id, MemberRole.OWNER)


async def upsert_user_from_claims(
    session: AsyncSession, sub: str, email: str, name: str | None, image: str | None
) -> User:
    claims = validate_input(UserClaims, sub=sub, email=email, name=name, image=image)
    row = await repo.upsert_user(session, claims)
    if row is None:
        raise EmailTakenError("That email already belongs to another account")
    return User.model_validate(row)


async def ensure_personal_workspace(session: AsyncSession, user: User) -> Workspace:
    created = await repo.insert_workspace(
        session, PERSONAL_WORKSPACE_NAME, user.id, is_personal=True
    )
    if created is not None:
        await _add_owner(session, created.id, user.id)
        return Workspace.model_validate(created)
    return Workspace.model_validate(await repo.get_personal_workspace(session, user.id))


async def list_workspaces(session: AsyncSession, user: User) -> list[Membership]:
    async with repo.rls_context(session, USER_SETTING, user.id):
        rows = await repo.list_memberships(session, user.id)
    return [Membership(workspace=Workspace.model_validate(ws), role=role) for ws, role in rows]


async def create_workspace(session: AsyncSession, user: User, name: str) -> Workspace:
    valid = validate_input(WorkspaceName, name=name)
    row = await repo.insert_workspace(session, valid.name, user.id, is_personal=False)
    if row is None:  # unreachable: only a personal insert can be skipped
        raise WorkspaceNotFoundError("Workspace was not created")
    await _add_owner(session, row.id, user.id)
    return Workspace.model_validate(row)


async def add_member(
    session: AsyncSession, actor: User, workspace_id: UUID, email: str, role: MemberRole
) -> Membership:
    new = validate_input(NewMember, email=email, role=role)
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        # A non-member gets the same error, so it cannot probe which workspaces exist.
        if await repo.get_member_role(session, workspace_id, actor.id) != MemberRole.OWNER:
            raise PermissionDeniedError("Only workspace owners can add members")
        user = await repo.get_user_by_email(session, new.email)
        if user is None:
            raise MemberUserNotFoundError("No user with that email; they must sign in first")
        if not await repo.insert_member(session, workspace_id, user.id, new.role):
            raise AlreadyMemberError("That user is already a member of this workspace")
    workspace = await repo.get_workspace(session, workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError()
    return Membership(workspace=Workspace.model_validate(workspace), role=new.role)


# ------------------------------------------------------------- provider keys
@dataclass(frozen=True)
class KeyTestResult:
    """Outcome of ``test_key``: the key with its stored result, and the failure if any."""

    key: ProviderKeyView
    error: UpstreamError | None = None


def _require_owner(membership: Membership, action: str) -> None:
    if membership.role is not MemberRole.OWNER:
        raise PermissionDeniedError(f"Only workspace owners can {action}")


def _key_view(row: ProviderKeyRow) -> ProviderKeyView:
    return ProviderKeyView.model_validate(row)


def _settings_view(row: WorkspaceSettingsRow | None) -> WorkspaceSettingsView:
    if row is None:
        return WorkspaceSettingsView(
            run_budget_usd=DEFAULT_RUN_BUDGET_USD, max_steps=DEFAULT_MAX_STEPS, version=0
        )
    return WorkspaceSettingsView.model_validate(row)


async def get_settings_overview(session: AsyncSession, workspace_id: UUID) -> SettingsResponse:
    """Masked keys and run settings of the workspace."""
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        keys = {
            row.kind: _key_view(row) for row in await repo.list_provider_keys(session, workspace_id)
        }
        settings = await repo.get_workspace_settings(session, workspace_id)
    return SettingsResponse(keys=ProviderKeys(**keys), settings=_settings_view(settings))


async def set_key(
    session: AsyncSession,
    membership: Membership,
    kind: ProviderKind,
    value: str,
    base_url: str | None = None,
    model: str | None = None,
) -> ProviderKeyView:
    """Seal and save the workspace's key of ``kind``, replacing any previous one (owners only)."""
    _require_owner(membership, "change provider keys")
    context = {ALLOW_LOCAL_HTTP: get_settings().is_development}
    new = validate_input(
        NewProviderKey, context, kind=kind, value=value, base_url=base_url, model=model
    )
    workspace_id = membership.workspace.id
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        row = await repo.upsert_provider_key(
            session,
            workspace_id,
            new.kind,
            base_url=new.base_url,
            model=new.model,
            sealed=crypto.encrypt(new.value, workspace_id),
            masked=crypto.mask(new.value),
        )
    logger.info("provider_key.saved", kind=new.kind.value, version=row.version)
    return _key_view(row)


async def delete_key(session: AsyncSession, membership: Membership, kind: ProviderKind) -> None:
    """Remove the workspace's key of ``kind`` (owners only); 404 if there is none."""
    _require_owner(membership, "change provider keys")
    async with repo.rls_context(session, WORKSPACE_SETTING, membership.workspace.id):
        if not await repo.delete_provider_key(session, membership.workspace.id, kind):
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
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        row = await _saved_key(session, workspace_id, kind)
    return _credentials(row, workspace_id)


async def _saved_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> ProviderKeyRow:
    """The saved key row; ``ProviderNotConfiguredError`` if there is none."""
    row = await repo.get_provider_key(session, workspace_id, kind)
    if row is None:
        raise ProviderNotConfiguredError(f"Add your {kind.value} key in settings first")
    return row


def _credentials(row: ProviderKeyRow, workspace_id: UUID) -> ProviderCredentials:
    api_key = crypto.decrypt(repo.seal_from_json(row.sealed), workspace_id)
    return ProviderCredentials(
        kind=ProviderKind(row.kind), api_key=api_key, base_url=row.base_url, model=row.model
    )


async def _check_provider(make_client: ClientFactory, creds: ProviderCredentials) -> None:
    """One cheap provider call; raises ``UpstreamError`` if the key does not work."""
    if creds.kind is ProviderKind.EXA:
        await ExaMcpClient(make_client, creds.api_key).check()
        return
    if creds.base_url is None:  # unreachable: llm keys are saved with a base_url
        raise ProviderNotConfiguredError("The llm key has no base_url; save it again")
    await OpenAICompatibleClient(make_client, creds.base_url, creds.api_key).list_models()


async def test_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind, make_client: ClientFactory
) -> KeyTestResult:
    """Make one cheap call with the saved key and record the result.

    A provider failure is returned in ``KeyTestResult.error`` rather than
    raised, so the caller can commit the recorded result.
    """
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        row = await _saved_key(session, workspace_id, kind)
        error: UpstreamError | None = None
        try:
            await _check_provider(make_client, _credentials(row, workspace_id))
        except UpstreamError as exc:
            error = exc
        row = await repo.record_key_test(
            session, row.id, ok=error is None, tested_at=datetime.now(tz=UTC)
        )
    logger.info(
        "provider_key.tested",
        kind=kind.value,
        ok=error is None,
        reason=(error.meta or {}).get("reason") if error else None,
    )
    return KeyTestResult(key=_key_view(row), error=error)


# ---------------------------------------------------------- workspace settings
def _settings_changes(patch: SettingsPatch) -> dict[str, object]:
    """Fields the patch sets. Read as attributes: ``model_dump`` would turn the
    Decimal budget into a float through its serializer."""
    changes: dict[str, object] = {}
    if patch.run_budget_usd is not None:
        changes["run_budget_usd"] = patch.run_budget_usd
    if patch.max_steps is not None:
        changes["max_steps"] = patch.max_steps
    return changes


async def update_settings(
    session: AsyncSession, membership: Membership, patch: SettingsPatch
) -> WorkspaceSettingsView:
    """Apply ``patch`` if ``patch.version`` is current (owners only); 409 if stale.

    Version 0 means "never saved": it creates the row from the defaults.
    """
    _require_owner(membership, "change workspace settings")
    workspace_id = membership.workspace.id
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        if patch.version == 0:
            row = await repo.insert_workspace_settings(
                session,
                workspace_id,
                run_budget_usd=patch.run_budget_usd or DEFAULT_RUN_BUDGET_USD,
                max_steps=patch.max_steps or DEFAULT_MAX_STEPS,
            )
        else:
            row = await repo.update_workspace_settings(
                session, workspace_id, version=patch.version, changes=_settings_changes(patch)
            )
    if row is None:
        raise ConflictError("Settings changed since you loaded them; reload and try again")
    return _settings_view(row)
