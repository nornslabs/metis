"""STT module service: business logic for speech-to-text."""

from __future__ import annotations

from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.feature_flags import build_feature_flag_provider
from metis.core.config import get_settings
from metis.core.crypto import decrypt, seal_from_json
from metis.core.db import WORKSPACE_SETTING
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import FeatureFlagProvider, FlagContext
from metis.modules.identity import repo
from metis.modules.identity.dto import ProviderKind
from metis.modules.stt.dto import STTErrorResponse, TranscribeResponse


async def transcribe_audio(
    session: AsyncSession,
    workspace_id: UUID,
    audio_content: bytes,
    content_type: str,
    flags: FeatureFlagProvider | None = None,
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
        flags: Feature flag provider (defaults to the static environment provider)

    Returns:
        TranscribeResponse with transcript, or STTErrorResponse on failure
    """
    _flags = flags or build_feature_flag_provider(get_settings())
    flag_context = FlagContext(
        workspace_id=workspace_id,
        environment=get_settings().app_env,
        custom_attributes={},
    )
    if not await _flags.is_enabled("sarvam_enabled", flag_context, default=True):
        raise ProviderNotConfiguredError(
            "Sarvam STT is disabled: the sarvam_enabled kill switch is off.",
            meta={"provider": "stt", "reason": "kill_switch"},
        )

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
