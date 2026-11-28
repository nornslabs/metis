"""The Interviewer's tools: ask one question, note a topic, recall the idea's turns, finish.

Each tool works on one run (``InterviewScope``) and opens its own short, committed
transaction, so nothing is held open while the run waits for the user. The rules (the
8-question cap, one open question per run, coverage) live in the ideas module; a tool only
turns a refusal into a message the model can act on.

``ask_user`` saves the question before it calls ``interrupt()`` and the answer after it
returns. On resume the node re-runs the tool from its start: saving the same question
again returns the saved turn, so nothing is duplicated; a turn that already has its answer
(a crash after saving it) returns that answer without pausing again.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.gate import GateContext, GateRefusal
from metis.agent.tools.interview_gates import IdeaTexts, ReviewOutcome, review_question
from metis.agent.tools.question_options import OptionArgs, check_options, question_payload
from metis.core.errors import QuestionAlreadyOpenError
from metis.helpers.dto import JsonList
from metis.modules import ideas
from metis.modules.ideas import (
    MAX_INTERVIEW_QUESTIONS,
    TOPIC_MEANING,
    InterviewFindings,
    InterviewTopic,
    QuestionRefusal,
    TurnSource,
)

ASK_USER = "ask_user"
SAVE_INTERVIEW_TURN = "save_interview_turn"
RECALL_MEMORY = "recall_memory"
FINISH_INTERVIEW = "finish_interview"
MAX_QUESTION_LENGTH = 500
MAX_ANSWER_LENGTH = 2_000

CAP_REACHED = (
    f"The question limit ({MAX_INTERVIEW_QUESTIONS}) is reached; this question was not asked. "
    f"Call {FINISH_INTERVIEW} now."
)
USER_ENDED = (
    f"The user ended the interview; this question was not asked. Call {FINISH_INTERVIEW} now."
)
SKIPPED = (
    "This question was not asked. Pick a different open assumption, or call "
    f"{FINISH_INTERVIEW} if none is worth asking."
)
ALREADY_ANSWERED = (
    "The idea or an earlier answer already answers this, so the {topic} topic was recorded and "
    f"the question was not asked. Pick a different open assumption, or call {FINISH_INTERVIEW} "
    "if none is worth asking."
)
ONE_AT_A_TIME = "Another question is still waiting for its answer. Ask one question at a time."
NOTED = "Noted."
FINISHED = "Interview finished."
REFUSED = {QuestionRefusal.CAP_REACHED: CAP_REACHED, QuestionRefusal.USER_ENDED: USER_ENDED}

TOPICS_HELP = "; ".join(f"{topic.value}: {meaning}" for topic, meaning in TOPIC_MEANING.items())

SessionOpener = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class InterviewScope:
    """The run the tools work on, and how to open a session scoped to its workspace."""

    workspace_id: UUID
    idea_id: UUID
    run_id: UUID
    open_session: SessionOpener

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self.open_session(self.workspace_id)


class AskUserArgs(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    topic: InterviewTopic = Field(description=TOPICS_HELP)
    options: JsonList[OptionArgs] = Field(
        default_factory=list,
        description="2 to 5 likely answers; leave empty for an open question the user types.",
    )
    multi: bool = Field(default=False, description="True when the user may pick several options.")
    allow_free_text: bool = Field(
        default=True, description="Whether the user may type an answer instead of picking."
    )


class SaveTurnArgs(BaseModel):
    topic: InterviewTopic = Field(description=TOPICS_HELP)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)


class RecallArgs(BaseModel):
    pass


def interview_tools(scope: InterviewScope, gates: GateContext) -> list[BaseTool]:
    """The Interviewer's allow-list, bound to one run; ``gates`` reviews every question."""
    return [_ask_user(scope, gates), _save_turn(scope), _recall(scope), _finish()]


def _ask_user(scope: InterviewScope, gates: GateContext) -> BaseTool:
    async def ask_user(
        question: str,
        topic: InterviewTopic,
        options: list[OptionArgs] | None = None,
        multi: bool = False,
        allow_free_text: bool = True,
    ) -> str:
        proposed = options or []
        if proposed and (problem := check_options(proposed, multi=multi)):
            return problem
        async with scope.session() as session:
            if message := await _review(
                session, scope, gates, question, topic, proposed, multi=multi
            ):
                return message
            try:
                turn = await ideas.open_question(
                    session, scope.workspace_id, scope.idea_id, scope.run_id, topic, question
                )
            except QuestionAlreadyOpenError:
                return ONE_AT_A_TIME
            if isinstance(turn, QuestionRefusal):
                return REFUSED[turn]
            coverage = await ideas.interview_coverage(
                session, scope.workspace_id, scope.idea_id, scope.run_id
            )
        if turn.answer is not None:
            return turn.answer
        index, total = ideas.question_progress(coverage)
        payload = question_payload(
            question,
            proposed,
            multi=multi,
            allow_free_text=allow_free_text,
            index=index,
            total=total,
        )
        answer = str(interrupt(payload))
        async with scope.session() as session:
            await ideas.answer_question(session, scope.workspace_id, turn.id, answer)
        return answer

    return StructuredTool.from_function(
        coroutine=ask_user,
        name=ASK_USER,
        description=(
            "Ask the user one short question about this idea and wait for the answer. Tag it "
            "with the brief field it informs, or other. Offer options when a few distinct "
            "answers are likely. A question that is generic, already answered or a repeat is "
            "refused."
        ),
        args_schema=AskUserArgs,
    )


async def _review(
    session: AsyncSession,
    scope: InterviewScope,
    gates: GateContext,
    question: str,
    topic: InterviewTopic,
    options: list[OptionArgs],
    *,
    multi: bool,
) -> str | None:
    """A message for the model when the gates stop the question, ``None`` to go on and ask it.

    The node re-runs this tool from its start when the run resumes, so the run's last asked
    question is not reviewed again when it comes back with the same text: the first review
    stands. When the cap is reached or the user ended the interview, the question goes on to
    ``open_question`` unreviewed, which refuses it: no judge call and no turn are spent on it.
    """
    idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
    turns = await ideas.list_turns(session, scope.workspace_id, scope.idea_id)
    if _is_rerun(turns, scope.run_id, question):
        return None
    coverage = await ideas.interview_coverage(
        session, scope.workspace_id, scope.idea_id, scope.run_id
    )
    if coverage.user_ended or coverage.questions_left == 0:
        return None
    texts = IdeaTexts(idea.title, idea.raw_text, [(t.question, t.answer) for t in turns])
    review = await review_question(gates, texts, question, options, multi=multi)
    if review.outcome is ReviewOutcome.ASK:
        return None
    if review.outcome is ReviewOutcome.REVISE:
        raise GateRefusal(review.text)
    if review.outcome is ReviewOutcome.ANSWERED:
        await ideas.save_interview_turn(
            session, scope.workspace_id, scope.idea_id, scope.run_id, topic, question, review.text
        )
        return ALREADY_ANSWERED.format(topic=topic.value)
    return SKIPPED


def _is_rerun(turns: list[ideas.InterviewTurn], run_id: UUID, question: str) -> bool:
    asked = [t for t in turns if t.run_id == run_id and t.source is TurnSource.ASKED]
    return bool(asked) and asked[-1].question == question


def _save_turn(scope: InterviewScope) -> BaseTool:
    async def save_interview_turn(topic: InterviewTopic, question: str, answer: str) -> str:
        async with scope.session() as session:
            await ideas.save_interview_turn(
                session, scope.workspace_id, scope.idea_id, scope.run_id, topic, question, answer
            )
        return NOTED

    return StructuredTool.from_function(
        coroutine=save_interview_turn,
        name=SAVE_INTERVIEW_TURN,
        description=(
            "Record a topic the idea text or an earlier answer already answers, without "
            "asking the user: the question it answers and the answer, in a few words."
        ),
        args_schema=SaveTurnArgs,
    )


def _recall(scope: InterviewScope) -> BaseTool:
    async def recall_memory() -> str:
        async with scope.session() as session:
            turns = await ideas.list_turns(session, scope.workspace_id, scope.idea_id)
            coverage = await ideas.interview_coverage(
                session, scope.workspace_id, scope.idea_id, scope.run_id
            )
        return json.dumps(
            {
                "turns": [
                    {"topic": t.topic.value, "question": t.question, "answer": t.answer}
                    for t in turns
                ],
                "covered": [t.value for t in coverage.covered],
                "skipped": [t.value for t in coverage.skipped],
                "missing": [t.value for t in coverage.missing],
                "questions_left": coverage.questions_left,
            }
        )

    return StructuredTool.from_function(
        coroutine=recall_memory,
        name=RECALL_MEMORY,
        description="What is already known about this idea: earlier turns and topic coverage.",
        args_schema=RecallArgs,
    )


def _finish() -> BaseTool:
    async def finish_interview(**_: object) -> str:
        # The node reads the findings from this call once the interview ends.
        return FINISHED

    return StructuredTool.from_function(
        coroutine=finish_interview,
        name=FINISH_INTERVIEW,
        description=(
            "End the interview with the findings: one short line per field, null when unknown."
        ),
        args_schema=InterviewFindings,
    )
