"""Check a resume value against the interrupt the run waits on."""

from __future__ import annotations

from typing import Any

from metis.agent.tools.ask_user import (
    ADVICE_DECISION,
    APPROVAL,
    CHOOSE_TEAM,
    EXPORT_APPROVAL,
    PHASE_REVIEW,
    QUESTION,
    SPEC_REVIEW,
)
from metis.core.errors import InvalidInputError
from metis.modules.ideas.dto.workflow_runs import (
    AdviceResume,
    ExportApprovalResume,
    PhaseReviewResume,
    QuestionAnswer,
    ResumeValue,
    TeamChoice,
)

MAX_ANSWER_LENGTH = 10_000
OPTION_SEPARATOR = "; "


def check_resume_value(
    pending_interrupt: dict[str, Any] | None, value: ResumeValue
) -> str | bool | dict[str, Any]:
    """The value to resume with: trimmed text for a question (the picked labels joined, or the
    typed text), a boolean for an approval, a JSON-safe dict for an advice decision, a phase
    review, a team choice or an export approval.

    Raises ``InvalidInputError`` (422) when the value does not fit the pending interrupt.
    """
    kind = (pending_interrupt or {}).get("type")
    if kind == QUESTION:
        return _answer(value, pending_interrupt or {})
    if kind == APPROVAL:
        return _decision(value)
    if kind == ADVICE_DECISION:
        return _advice(value)
    if kind == PHASE_REVIEW:
        return _phases(value)
    if kind == CHOOSE_TEAM:
        return _team(value, pending_interrupt or {})
    if kind == EXPORT_APPROVAL:
        return _export_approval(value)
    if kind == SPEC_REVIEW:
        raise _invalid("Confirm the spec to continue the run")
    raise InvalidInputError("The run is not waiting for a known kind of input")


def _advice(value: ResumeValue) -> dict[str, Any]:
    if isinstance(value, AdviceResume):
        return value.model_dump(mode="json")
    raise _invalid("An advice decision needs {decision, revised_text?, accepted_suggestion_ids?}")


def _team(value: ResumeValue, pending: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, TeamChoice):
        raise _invalid("A team choice needs {team_id}")
    offered = {str(team["id"]) for team in pending.get("teams") or []}
    if value.team_id not in offered:
        raise _invalid("team_id is not one of the offered teams")
    return value.model_dump(mode="json")


def _export_approval(value: ResumeValue) -> dict[str, Any]:
    if isinstance(value, ExportApprovalResume):
        return value.model_dump(mode="json", exclude_none=True)
    raise _invalid("An export approval needs {approved: true|false}")


def _phases(value: ResumeValue) -> dict[str, Any]:
    if isinstance(value, PhaseReviewResume):
        return value.model_dump(mode="json")
    raise _invalid("A phase review needs {phases: [{name, goal, exit_criteria}]}")


def _answer(value: ResumeValue, pending: dict[str, Any]) -> str:
    options: list[dict[str, Any]] = pending.get("options") or []
    if isinstance(value, QuestionAnswer):
        return _structured_answer(value, pending, options)
    if isinstance(value, str):
        _require_free_text(pending, options)
        return _text(value)
    raise _invalid(f"An answer is 1 to {MAX_ANSWER_LENGTH} characters of text")


def _structured_answer(
    value: QuestionAnswer, pending: dict[str, Any], options: list[dict[str, Any]]
) -> str:
    if value.option_ids and value.text is not None:
        raise _invalid("Answer with option_ids or text, not both")
    if value.text is not None:
        _require_free_text(pending, options)
        return _text(value.text)
    if not value.option_ids:
        raise _invalid("An answer needs option_ids or text")
    return _picked_labels(value.option_ids, pending, options)


def _picked_labels(
    ids: tuple[str, ...], pending: dict[str, Any], options: list[dict[str, Any]]
) -> str:
    if not options:
        raise _invalid("This question has no options; answer with text")
    if len(set(ids)) != len(ids):
        raise _invalid("option_ids must not repeat an option")
    known = {str(option["id"]) for option in options}
    if unknown := [i for i in ids if i not in known]:
        raise _invalid(f"Unknown option_ids: {', '.join(unknown)}")
    if len(ids) > 1 and not pending.get("multi"):
        raise _invalid("This question takes one option")
    picked = set(ids)
    return OPTION_SEPARATOR.join(str(o["label"]) for o in options if str(o["id"]) in picked)


def _require_free_text(pending: dict[str, Any], options: list[dict[str, Any]]) -> None:
    if options and not pending.get("allow_free_text", True):
        raise _invalid("This question takes an option; free text is not allowed")


def _text(value: str) -> str:
    if (text := value.strip()) and len(text) <= MAX_ANSWER_LENGTH:
        return text
    raise _invalid(f"An answer is 1 to {MAX_ANSWER_LENGTH} characters of text")


def _decision(value: ResumeValue) -> bool:
    if isinstance(value, bool):
        return value
    raise _invalid("An approval needs true or false")


def _invalid(message: str) -> InvalidInputError:
    return InvalidInputError(
        "Invalid resume value", errors=[{"field": "body.value", "message": message}]
    )
