"""Build Pydantic models from untrusted input, failing with a safe 422."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from metis.core.errors import InvalidInputError


def validate_input[ModelT: BaseModel](
    model: type[ModelT], context: dict[str, Any] | None = None, /, **data: object
) -> ModelT:
    """Build ``model`` from ``data`` or raise a 422 ``InvalidInputError``.

    Errors carry field names and messages only, never the input values, so a
    rejected secret is never echoed back. ``context`` reaches validators via
    ``ValidationInfo.context``.
    """
    try:
        return model.model_validate(data, context=context)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise InvalidInputError("Invalid input", errors=errors) from exc
