"""Check a resume value against the interrupt the run waits on."""

from __future__ import annotations

from typing import Any

from metis.agent.tools.ask_user import ADVICE_DECISION, APPROVAL, QUESTION
from metis.core.errors import InvalidInputError
from metis.modules.ideas.dto.workflow_runs import AdviceResume

MAX_ANSWER_LENGTH = 10_000


def check_resume_value(
    pending_interrupt: dict[str, Any] | None, value: str | bool | AdviceResume
) -> str | bool | dict[str, Any]:
    """The value to resume with: trimmed text for a question, a boolean for an approval, a
    JSON-safe dict for an advice decision.

    Raises ``InvalidInputError`` (422) when the value does not fit the pending interrupt.
    """
    kind = (pending_interrupt or {}).get("type")
    if kind == QUESTION:
        return _answer(value)
    if kind == APPROVAL:
        return _decision(value)
    if kind == ADVICE_DECISION:
        return _advice(value)
    raise InvalidInputError("The run is not waiting for a known kind of input")


def _advice(value: str | bool | AdviceResume) -> dict[str, Any]:
    if isinstance(value, AdviceResume):
        return value.model_dump(mode="json")
    raise _invalid("An advice decision needs {decision, revised_text?, accepted_suggestion_ids?}")


def _answer(value: str | bool | AdviceResume) -> str:
    if isinstance(value, str) and (text := value.strip()) and len(text) <= MAX_ANSWER_LENGTH:
        return text
    raise _invalid(f"An answer is 1 to {MAX_ANSWER_LENGTH} characters of text")


def _decision(value: str | bool | AdviceResume) -> bool:
    if isinstance(value, bool):
        return value
    raise _invalid("An approval needs true or false")


def _invalid(message: str) -> InvalidInputError:
    return InvalidInputError(
        "Invalid resume value", errors=[{"field": "body.value", "message": message}]
    )
