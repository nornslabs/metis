"""Workspace settings: run budget and step limits.

Every function takes the caller's ``AsyncSession``, flushes but never commits: the caller
owns the transaction. Each function sets the RLS context it needs (``app.user_id`` /
``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.feature_flags import build_feature_flag_provider
from metis.core.config import get_settings
from metis.core.db import WORKSPACE_SETTING
from metis.core.errors import ConflictError
from metis.core.logging import get_logger
from metis.core.ports import FeatureFlagProvider, FlagContext
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

logger = get_logger(__name__)

async def get_settings_overview(
    session: AsyncSession, workspace_id: UUID, flags: FeatureFlagProvider | None = None
) -> SettingsResponse:
    """Masked keys and run settings of the workspace.

    Remote config values (capabilities, run_budget_usd, max_steps) override DB values
    when the flag provider returns a non-default result.
    """
    _flags = flags or build_feature_flag_provider(get_settings())
    context = FlagContext(
        workspace_id=workspace_id,
        environment=get_settings().app_env,
        custom_attributes={},
    )
    capabilities = await _flags.get_json("capabilities", context, {})
    run_budget_remote = await _flags.get_json("run_budget_usd", context, {})
    max_steps_remote = await _flags.get_json("max_steps", context, {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    if not isinstance(run_budget_remote, dict):
        run_budget_remote = {}
    if not isinstance(max_steps_remote, dict):
        max_steps_remote = {}

    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        keys = {
            row.kind: key_view(row)
            for row in await repo.provider_keys.list_for_workspace(session, workspace_id)
        }
        settings = await repo.settings.get(session, workspace_id)

    run_budget_usd = settings.run_budget_usd if settings else DEFAULT_RUN_BUDGET_USD
    max_steps = settings.max_steps if settings else DEFAULT_MAX_STEPS
    linear_team_id = settings.linear_team_id if settings else None

    if run_budget_remote:
        remote_value = run_budget_remote.get("value")
        if remote_value is not None:
            run_budget_usd = Decimal(str(remote_value))
    if max_steps_remote:
        remote_value = max_steps_remote.get("value")
        if remote_value is not None:
            max_steps = int(str(remote_value))

    return SettingsResponse(
        keys=ProviderKeys(**keys),
        settings=WorkspaceSettingsView(
            run_budget_usd=run_budget_usd,
            max_steps=max_steps,
            version=settings.version if settings else 0,
            linear_team_id=linear_team_id,
            capabilities=capabilities,
        ),
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


async def set_linear_team(session: AsyncSession, workspace_id: UUID, team_id: str) -> None:
    """Save the Linear team exports go to. Any member's run may call this (the member who
    answered the team question); it is not the owner-only settings patch."""
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        await repo.settings.set_linear_team(session, workspace_id, team_id)


def _settings_view(row: WorkspaceSettingsRow | None) -> WorkspaceSettingsView:
    if row is None:
        return WorkspaceSettingsView(
            run_budget_usd=DEFAULT_RUN_BUDGET_USD,
            max_steps=DEFAULT_MAX_STEPS,
            version=0,
            capabilities={},
        )
    return WorkspaceSettingsView(
        run_budget_usd=row.run_budget_usd,
        max_steps=row.max_steps,
        version=row.version,
        linear_team_id=row.linear_team_id,
        capabilities={},
    )


def _settings_changes(patch: SettingsPatch) -> dict[str, object]:
    """Fields the patch sets. Read as attributes: ``model_dump`` would turn the
    Decimal budget into a float through its serializer."""
    changes: dict[str, object] = {}
    if patch.run_budget_usd is not None:
        changes["run_budget_usd"] = patch.run_budget_usd
    if patch.max_steps is not None:
        changes["max_steps"] = patch.max_steps
    return changes
