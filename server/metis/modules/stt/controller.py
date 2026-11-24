"""STT module controller: HTTP routes for speech-to-text."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import JSONResponse

from metis.core.db import SessionDep
from metis.core.error_handlers import metis_error_response
from metis.core.errors import UpstreamError
from metis.modules.identity.deps import CurrentWorkspaceDep
from metis.modules.stt import service
from metis.modules.stt.dto import STTErrorResponse, TranscribeResponse

router = APIRouter(prefix="/v1/stt", tags=["stt"])


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": STTErrorResponse,
            "description": "Client-side provider or missing key",
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": STTErrorResponse,
            "description": "Transcription failed",
        },
    },
)
async def transcribe(
    request: Request,
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    file: Annotated[UploadFile, File(description="Audio file (WebM/Opus)")],
) -> TranscribeResponse | JSONResponse:
    """Transcribe audio using the workspace's configured STT provider.

    - If provider is 'sarvam': uses workspace's Sarvam API key
    - If provider is 'web-speech': returns 400 (use client-side)
    - If provider is 'mock': returns mock transcript
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        return metis_error_response(
            request,
            UpstreamError("Invalid file type", meta={"reason": "file must be audio"}),
        )

    audio_content = await file.read()

    if not audio_content:
        return metis_error_response(
            request,
            UpstreamError("Empty audio file", meta={"reason": "no audio data"}),
        )

    result = await service.transcribe_audio(
        session,
        workspace.workspace.id,
        audio_content,
        file.content_type,
    )

    if isinstance(result, STTErrorResponse):
        if result.error == "client_side_provider":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=result.model_dump(),
            )
        if result.error == "key_not_configured":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=result.model_dump(),
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=result.model_dump(),
        )

    return result