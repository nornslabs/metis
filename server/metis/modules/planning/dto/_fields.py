"""Field types shared by the planning DTOs: trimmed texts and labels."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from metis.modules.planning.dto.enums import MAX_COMPONENT_LENGTH

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000)]
TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TaskDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Component = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_COMPONENT_LENGTH)
]
# An edit's component: an empty string clears it.
ComponentOrBlank = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_COMPONENT_LENGTH)
]
TaskKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
