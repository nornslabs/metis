"""Spec routes: read, list, edit and confirm an idea's spec (``/v1/ideas/{id}/spec``).

Any workspace member may use them. Confirming commits first and resumes the run waiting on
``spec_review`` second, as the run routes do, so a worker never resumes an unsaved confirmation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, status

from metis.core.db import SessionDep
from metis.modules.auth import CurrentUserDep
from metis.modules.ideas import service
from metis.modules.ideas.controller.runs import enqueue_run
from metis.modules.ideas.dto import (
    ConfirmSpecBody,
    EditSpecBody,
    NewSpecVersion,
    SpecConfirmed,
    SpecOverview,
    SpecSource,
    SpecVersion,
    SpecVersionList,
)
from metis.modules.identity import CurrentWorkspaceDep

if TYPE_CHECKING:
    from uuid import UUID

router = APIRouter(prefix="/ideas")


@router.get("/{idea_id}/spec", response_model=SpecOverview)
async def get_spec(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> SpecOverview:
    """The latest and the confirmed spec version (each ``null`` while there is none)."""
    return await service.specs.get_spec_overview(session, workspace.workspace.id, idea_id)


@router.get("/{idea_id}/spec/versions", response_model=SpecVersionList)
async def list_spec_versions(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> SpecVersionList:
    """Every version without its text, newest first."""
    return await service.specs.list_spec_versions(session, workspace.workspace.id, idea_id)


@router.get("/{idea_id}/spec/versions/{number}", response_model=SpecVersion)
async def get_spec_version(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID, number: int
) -> SpecVersion:
    """One version of the spec, with its text."""
    return await service.specs.get_spec(session, workspace.workspace.id, idea_id, number)


@router.post(
    "/{idea_id}/spec/versions", response_model=SpecVersion, status_code=status.HTTP_201_CREATED
)
async def edit_spec(
    session: SessionDep,
    caller: CurrentUserDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    body: EditSpecBody,
) -> SpecVersion:
    """Save an edit as the next version; ``base_number`` must be the latest (else 409)."""
    return await service.specs.save_spec_version(
        session,
        workspace.workspace.id,
        idea_id,
        NewSpecVersion(
            content_md=body.content_md, source=SpecSource.USER, created_by=caller.user.id
        ),
        base_number=body.base_number,
    )


@router.post(
    "/{idea_id}/spec/confirm", response_model=SpecConfirmed, status_code=status.HTTP_202_ACCEPTED
)
async def confirm_spec(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID, body: ConfirmSpecBody
) -> SpecConfirmed:
    """Confirm the latest version and resume the run waiting on it (if one is)."""
    workspace_id = workspace.workspace.id
    await service.specs.confirm_spec(session, workspace_id, idea_id, body.number)
    confirmed = await service.specs.get_spec(session, workspace_id, idea_id, body.number)
    run = await service.specs.waiting_run(session, workspace_id, idea_id)
    await session.commit()
    if run is not None:
        await enqueue_run(
            run.id,
            workspace_id,
            job_id=f"{run.id}:resume:{run.version}",
            resume={"confirmed_number": confirmed.number},
        )
    return SpecConfirmed(confirmed=confirmed, run_id=None if run is None else run.id)
