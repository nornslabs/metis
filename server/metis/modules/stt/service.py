"""STT module service: business logic for speech-to-text."""

from __future__ import annotations

from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.crypto import decrypt, seal_from_json
from metis.core.db import WORKSPACE_SETTING
from metis.modules.identity import repo
from metis.modules.identity.dto import ProviderKind
from metis.modules.stt.dto import STTErrorResponse, TranscribeResponse


async def transcribe_audio(
    session: AsyncSession,
    workspace_id: UUID,
    audio_content: bytes,
    content_type: str,
) -> TranscribeResponse | STTErrorResponse:
    """Transcribe audio using the workspace's configured STT provider.

    Provider selection:
    - If Sarvam API key is configured → use Sarvam (server-side)
    - Otherwise → web-speech (client-side)

    Args:
        session: Database session
        workspace_id: Workspace ID
        audio_content: Raw audio bytes
        content_type: MIME type of audio (e.g., "audio/webm")

    Returns:
        TranscribeResponse with transcript, or STTErrorResponse on failure
    """
    # Check if Sarvam API key exists for this workspace
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        key_row = await repo.provider_keys.get(session, workspace_id, ProviderKind.SARVAM)

    if key_row:
        return await _transcribe_sarvam(session, workspace_id, audio_content, content_type)

    # No Sarvam key: use client-side Web Speech API
    return STTErrorResponse(
        error="client_side_provider",
        detail="Use client-side Web Speech API for this provider",
    )


async def _transcribe_sarvam(
    session: AsyncSession,
    workspace_id: UUID,
    audio_content: bytes,
    content_type: str,
) -> TranscribeResponse | STTErrorResponse:
    """Transcribe using Sarvam API."""
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        # Get Sarvam API key from provider_keys
        key_row = await repo.provider_keys.get(session, workspace_id, ProviderKind.SARVAM)

    if not key_row:
        return STTErrorResponse(
            error="key_not_configured",
            detail="Sarvam API key not configured for this workspace",
        )

    try:
        # Decrypt the API key
        sealed = seal_from_json(key_row.sealed)
        api_key = decrypt(sealed, workspace_id)

        # Call Sarvam API
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": ("audio.webm", audio_content, content_type)}
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.post(
                "https://api.sarvam.ai/speech-to-text",
                files=files,
                headers=headers,
            )

        if not response.is_success:
            return STTErrorResponse(
                error="provider_error",
                detail=f"Sarvam STT failed: {response.status_code} {response.text}",
            )

        data = response.json()
        transcript = data.get("transcript", "")

        return TranscribeResponse(transcript=transcript)

    except httpx.RequestError as e:
        return STTErrorResponse(
            error="network_error",
            detail=f"Failed to connect to Sarvam API: {str(e)}",
        )
    except Exception as e:
        return STTErrorResponse(
            error="internal_error",
            detail=f"Transcription failed: {str(e)}",
        )