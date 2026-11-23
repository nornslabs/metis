"""Answer options for a question: the rules, the ids and the ``question`` interrupt payload.

The model proposes ``label``, ``detail`` and ``recommended`` for each option; the tool assigns
the ids (``o1``, ``o2``, ... by position) so an answer can only name an option that was shown.
A proposal that breaks a rule comes back as a message the model can act on, never as an error.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

MIN_OPTIONS = 2
MAX_OPTIONS = 5
MAX_LABEL_LENGTH = 80
MAX_DETAIL_LENGTH = 160


class OptionArgs(BaseModel):
    """One proposed answer. Plain fields: the rules below give the model a readable message."""

    label: str
    detail: str | None = None
    recommended: bool = False


def check_options(options: list[OptionArgs], *, multi: bool) -> str | None:
    """What to fix in the proposed options, or ``None`` when they follow the rules."""
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        return f"Give {MIN_OPTIONS} to {MAX_OPTIONS} options, or none for a free-text question."
    labels = [option.label.strip() for option in options]
    if any(not label or len(label) > MAX_LABEL_LENGTH for label in labels):
        return f"Each option label is 1 to {MAX_LABEL_LENGTH} characters."
    if len({label.casefold() for label in labels}) != len(labels):
        return "Option labels must be different from each other."
    if any(len((option.detail or "").strip()) > MAX_DETAIL_LENGTH for option in options):
        return f"An option detail is at most {MAX_DETAIL_LENGTH} characters."
    if not multi and sum(option.recommended for option in options) > 1:
        return "Recommend at most one option, unless the question takes several answers."
    return None


def question_payload(
    question: str,
    options: list[OptionArgs],
    *,
    multi: bool,
    allow_free_text: bool,
    index: int,
    total: int,
) -> dict[str, Any]:
    """The ``question`` interrupt. A question without options is free text only."""
    has_options = bool(options)
    return {
        "type": "question",
        "question": question,
        "multi": multi and has_options,
        "options": [_option(position, option) for position, option in enumerate(options, 1)],
        "allow_free_text": allow_free_text or not has_options,
        "index": index,
        "total": total,
    }


def _option(position: int, option: OptionArgs) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"o{position}",
        "label": option.label.strip(),
        "recommended": option.recommended,
    }
    if detail := (option.detail or "").strip():
        payload["detail"] = detail
    return payload
