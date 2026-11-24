"""STT module DTOs: request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class TranscribeRequest(BaseModel):
    """Request to transcribe audio. Uses multipart/form-data, not JSON."""


class TranscribeResponse(BaseModel):
    """Response from transcription."""

    transcript: str


class STTErrorResponse(BaseModel):
    """Error response from STT endpoint."""

    error: str
    detail: str | None = None