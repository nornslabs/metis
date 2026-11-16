"""Tools that pause the run for the user: a question, or approval of an external write.

Both call ``interrupt()``: the graph stops at the checkpoint with the payload, and the run
continues when the caller resumes it with ``Command(resume=value)``; the tool then returns
that value. A node that calls a tool is re-run from its start on resume, so it must do no
side effects before the call.
"""

from __future__ import annotations

from langchain_core.tools import tool
from langgraph.types import interrupt

QUESTION = "question"
APPROVAL = "approval"


@tool
def ask_user(question: str) -> str:
    """Ask the user one question and wait for the answer."""
    return str(interrupt({"type": QUESTION, "question": question}))


@tool
def request_approval(action: str, details: str) -> bool:
    """Ask the user to approve an action that writes to an external tool; True when approved."""
    return bool(interrupt({"type": APPROVAL, "action": action, "details": details}))
