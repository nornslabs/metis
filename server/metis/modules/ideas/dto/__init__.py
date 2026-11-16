"""Ideas DTOs (validated inputs, records, HTTP bodies), one file per domain."""

from __future__ import annotations

from metis.modules.ideas.dto.ideas import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_RAW_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
    MIN_RAW_TEXT_LENGTH,
    MIN_TITLE_LENGTH,
    Idea,
    IdeaKind,
    IdeaPage,
    IdeaPatch,
    NewIdea,
    Stage,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MAX_RAW_TEXT_LENGTH",
    "MAX_TITLE_LENGTH",
    "MIN_RAW_TEXT_LENGTH",
    "MIN_TITLE_LENGTH",
    "Idea",
    "IdeaKind",
    "IdeaPage",
    "IdeaPatch",
    "NewIdea",
    "Stage",
]
