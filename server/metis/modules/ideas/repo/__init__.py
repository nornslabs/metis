"""Postgres access for the ideas module, one file per table.

Call it domain-qualified: ``repo.ideas.create(...)``.
"""

from __future__ import annotations

from metis.modules.ideas.repo import ideas, interview, llm_usage, workflow_runs

__all__ = ["ideas", "interview", "llm_usage", "workflow_runs"]
