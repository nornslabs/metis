"""Workspace settings: run budget and step limits.

Every function takes the caller's ``AsyncSession``, flushes but never commits: the caller
owns the transaction. Each function sets the RLS context it needs (``app.user_id`` /
``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import WORKSPACE_SETTING
from metis.core.errors import ConflictError
from metis.modules.identity import repo
from metis.modules.identity.dto import (
    DEFAULT_MAX_STEPS,
    DEFAULT_RUN_BUDGET_USD,
    Membership,
    ProviderKeys,
    SettingsPatch,
    SettingsResponse,
    WorkspaceSettingsView,
)
from metis.modules.identity.helpers.permissions import require_owner
from metis.modules.identity.helpers.views import key_view
from metis.modules.identity.models import WorkspaceSettingsRow


async def get_settings_overview(session: AsyncSession, workspace_id: UUID) -> SettingsResponse:
    """Masked keys and run settings of the workspace."""
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        keys = {
            row.kind: key_view(row)
            for row in await repo.provider_keys.list_for_workspace(session, workspace_id)
        }
        settings = await repo.settings.get(session, workspace_id)
    return SettingsResponse(
        keys=ProviderKeys(**keys, sarvam=keys.get("sarvam")),
        settings=_settings_view(settings),
    )


async def update_settings(
    session: AsyncSession, membership: Membership, patch: SettingsPatch
) -> WorkspaceSettingsView:
    """Apply ``patch`` if ``patch.version`` is current (owners only); 409 if stale.

    Version 0 means "never saved": it creates the row from the defaults.
    """
    require_owner(membership, "change workspace settings")
    workspace_id = membership.workspace.id
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        if patch.version == 0:
            row = await repo.settings.create(
                session,
                workspace_id,
                run_budget_usd=patch.run_budget_usd or DEFAULT_RUN_BUDGET_USD,
                max_steps=patch.max_steps or DEFAULT_MAX_STEPS,
            )
        else:
            row = await repo.settings.update_at_version(
                session, workspace_id, version=patch.version, changes=_settings_changes(patch)
            )
    if row is None:
        raise ConflictError("Settings changed since you loaded them; reload and try again")
    return _settings_view(row)


def _settings_view(row: WorkspaceSettingsRow | None) -> WorkspaceSettingsView:
    if row is None:
        return WorkspaceSettingsView(
            run_budget_usd=DEFAULT_RUN_BUDGET_USD,
            max_steps=DEFAULT_MAX_STEPS,
            stt_provider="web-speech",
            version=0,
        )
    return WorkspaceSettingsView.model_validate(row)


def _settings_changes(patch: SettingsPatch) -> dict[str, object]:
    """Fields the patch sets. Read as attributes: ``model_dump`` would turn the
    Decimal budget into a float through its serializer."""
    changes: dict[str, object] = {}
    if patch.run_budget_usd is not None:
        changes["run_budget_usd"] = patch.run_budget_usd
    if patch.max_steps is not None:
        changes["max_steps"] = patch.max_steps
    if patch.stt_provider is not None:
        changes["stt_provider"] = patch.stt_provider
    return changes
