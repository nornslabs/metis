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

from metis.agent.tools.ask_user import QUESTION
from metis.core.errors import QuestionAlreadyOpenError
from metis.modules import ideas
from metis.modules.ideas import (
    MAX_INTERVIEW_QUESTIONS,
    TOPIC_MEANING,
    InterviewFindings,
    InterviewTopic,
    QuestionRefusal,
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


class SaveTurnArgs(BaseModel):
    topic: InterviewTopic = Field(description=TOPICS_HELP)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)


class RecallArgs(BaseModel):
    pass


def interview_tools(scope: InterviewScope) -> list[BaseTool]:
    """The Interviewer's allow-list, bound to one run."""
    return [_ask_user(scope), _save_turn(scope), _recall(scope), _finish()]


def _ask_user(scope: InterviewScope) -> BaseTool:
    async def ask_user(question: str, topic: InterviewTopic) -> str:
        async with scope.session() as session:
            try:
                turn = await ideas.open_question(
                    session, scope.workspace_id, scope.idea_id, scope.run_id, topic, question
                )
            except QuestionAlreadyOpenError:
                return ONE_AT_A_TIME
        if isinstance(turn, QuestionRefusal):
            return REFUSED[turn]
        if turn.answer is not None:
            return turn.answer
        answer = str(interrupt({"type": QUESTION, "question": question}))
        async with scope.session() as session:
            await ideas.answer_question(session, scope.workspace_id, turn.id, answer)
        return answer

    return StructuredTool.from_function(
        coroutine=ask_user,
        name=ASK_USER,
        description="Ask the user one short question about one topic and wait for the answer.",
        args_schema=AskUserArgs,
    )


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
