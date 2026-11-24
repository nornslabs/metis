"""STT module: speech-to-text transcription endpoint."""

from metis.modules.stt.controller import router, transcribe
from metis.modules.stt.dto import STTErrorResponse, TranscribeResponse
from metis.modules.stt.service import transcribe_audio

__all__ = [
    "router",
    "transcribe",
    "transcribe_audio",
    "TranscribeResponse",
    "STTErrorResponse",
]