"""Error types and error code catalog for the Metis API.

Every failure returns a standardized JSON body with a stable custom error code,
so clients can reliably map codes to user-facing messages.

Response format: `application/problem+json`
{
  "type": "<HTTP-ORIGIN>/errors/common.validation_failed",
  "title": "Validation Failed",
  "status": 422,
  "code": "common.validation_failed",
  "detail": "One or more fields failed validation",
  "request_id": "01H...",
  "retryable": false,
  "errors": [{"field": "email", "message": "Invalid email format"}],
  "meta": {"retry_after": 60}
}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable error codes for every failure type.

    Codes are organized by domain: common.*, auth.*, workspace.*, provider.*,
    idea.*, run.*, research.*, score.*, spec.*, plan.*, mcp.*, export.*
    """

    # ------------------------------------------------------------------ common
    INTERNAL_ERROR = "common.internal_error"
    ROUTE_NOT_FOUND = "common.route_not_found"
    METHOD_NOT_ALLOWED = "common.method_not_allowed"
    VALIDATION_FAILED = "common.validation_failed"
    RATE_LIMITED = "common.rate_limited"
    TIMEOUT = "common.timeout"
    UNAVAILABLE = "common.unavailable"
    CONFLICT = "common.conflict"
    BAD_REQUEST = "common.bad_request"

    # ----------------------------------------------------------------------- auth
    UNAUTHORIZED = "auth.unauthorized"
    FORBIDDEN = "auth.forbidden"
    INVALID_CREDENTIALS = "auth.invalid_credentials"
    NOT_SIGNED_IN = "auth.not_signed_in"
    SESSION_EXPIRED = "auth.session_expired"
    CSRF_FAILED = "auth.csrf_failed"
    OAUTH_STATE_INVALID = "auth.oauth_state_invalid"
    OAUTH_FAILED = "auth.oauth_failed"
    EMAIL_UNVERIFIED = "auth.email_unverified"

    # -------------------------------------------------------------------- workspace
    WORKSPACE_NOT_FOUND = "workspace.not_found"
    WORKSPACE_ALREADY_EXISTS = "workspace.already_exists"
    MEMBER_NOT_FOUND = "workspace.member_not_found"
    INVITE_EXPIRED = "workspace.invite_expired"

    # -------------------------------------------------------------------- provider
    PROVIDER_NOT_CONFIGURED = "provider.not_configured"
    PROVIDER_KEY_NOT_FOUND = "provider.key_not_found"
    UPSTREAM_ERROR = "provider.upstream_error"
    BUDGET_EXCEEDED = "provider.budget_exceeded"

    # ---------------------------------------------------------------------- crypto
    SECRET_DECRYPT_FAILED = "crypto.decrypt_failed"

    # ----------------------------------------------------------------------- idea
    IDEA_NOT_FOUND = "idea.not_found"
    IDEA_INVALID_TRANSITION = "idea.invalid_transition"
    IDEA_NOT_OWNER = "idea.not_owner"
    IDEA_CANCELLED = "idea.cancelled"

    # -------------------------------------------------------------------------- run
    RUN_NOT_FOUND = "run.not_found"
    RUN_ALREADY_RUNNING = "run.already_running"
    RUN_INVALID_STATE = "run.invalid_state"
    RUN_TIMEOUT = "run.timeout"
    RUN_CANCELLED = "run.cancelled"
    RUN_EVENT_MALFORMED = "run.event_malformed"
    RUN_STEP_LIMIT_REACHED = "run.step_limit_reached"
    RUN_FAILED = "run.failed"
    RUN_IDEMPOTENCY_MISMATCH = "run.idempotency_mismatch"
    RUN_ENQUEUE_FAILED = "run.enqueue_failed"

    # --------------------------------------------------------------------- interview
    INTERVIEW_QUESTION_OPEN = "interview.question_open"
    INTERVIEW_TURN_NOT_FOUND = "interview.turn_not_found"

    # ---------------------------------------------------------------------- research
    RESEARCH_NO_RESULTS = "research.no_results"
    RESEARCH_UPSTREAM_ERROR = "research.upstream_error"
    RESEARCH_BUDGET_EXCEEDED = "research.budget_exceeded"
    RESEARCH_NOT_FOUND = "research.not_found"
    RESEARCH_SNAPSHOT_NOT_FOUND = "research.snapshot_not_found"
    RESEARCH_SNAPSHOT_CLOSED = "research.snapshot_closed"
    RESEARCH_SOURCE_MISSING = "research.source_missing"
    RESEARCH_COMPETITOR_NOT_FOUND = "research.competitor_not_found"

    # ----------------------------------------------------------------------- scoring
    SCORE_INVALID_RUBRIC = "score.invalid_rubric"
    SCORE_UPSTREAM_ERROR = "score.upstream_error"
    SCORE_BUDGET_EXCEEDED = "score.budget_exceeded"

    # ------------------------------------------------------------------------- spec
    SPEC_NOT_FOUND = "spec.not_found"
    SPEC_CONFLICT = "spec.conflict"
    SPEC_INVALID_TRANSITION = "spec.invalid_transition"

    # ------------------------------------------------------------------------- plan
    PLAN_NOT_FOUND = "plan.not_found"
    PLAN_CONFLICT = "plan.conflict"
    PLAN_INVALID_TRANSITION = "plan.invalid_transition"

    # -------------------------------------------------------------------------- mcp
    MCP_NOT_CONNECTED = "mcp.not_connected"
    MCP_UPSTREAM_ERROR = "mcp.upstream_error"
    MCP_TOOL_NOT_FOUND = "mcp.tool_not_found"

    # ----------------------------------------------------------------------- export
    EXPORT_NOT_FOUND = "export.not_found"
    EXPORT_CONFLICT = "export.conflict"
    EXPORT_UPSTREAM_ERROR = "export.upstream_error"
    EXPORT_CANCELLED = "export.cancelled"


@dataclass(frozen=True)
class ErrorSpec:
    """Specification for how to render an error code.

    Attributes:
        status: HTTP status code for the error response.
        title: Human-readable title for the error.
        retryable: Whether the client should retry the request.
    """

    status: int
    title: str
    retryable: bool = False


# ---------------------------------------------------------------------------
# ERROR CATALOG
# ---------------------------------------------------------------------------

ERROR_CATALOG: dict[ErrorCode, ErrorSpec] = {
    # common
    ErrorCode.INTERNAL_ERROR: ErrorSpec(
        status=500,
        title="Internal Server Error",
        retryable=True,
    ),
    ErrorCode.ROUTE_NOT_FOUND: ErrorSpec(
        status=404,
        title="Not Found",
        retryable=False,
    ),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(
        status=405,
        title="Method Not Allowed",
        retryable=False,
    ),
    ErrorCode.VALIDATION_FAILED: ErrorSpec(
        status=422,
        title="Validation Failed",
        retryable=False,
    ),
    ErrorCode.RATE_LIMITED: ErrorSpec(
        status=429,
        title="Too Many Requests",
        retryable=True,
    ),
    ErrorCode.TIMEOUT: ErrorSpec(
        status=504,
        title="Request Timeout",
        retryable=True,
    ),
    ErrorCode.UNAVAILABLE: ErrorSpec(
        status=503,
        title="Service Unavailable",
        retryable=True,
    ),
    ErrorCode.CONFLICT: ErrorSpec(
        status=409,
        title="Conflict",
        retryable=False,
    ),
    ErrorCode.BAD_REQUEST: ErrorSpec(
        status=400,
        title="Bad Request",
        retryable=False,
    ),
    # auth
    ErrorCode.UNAUTHORIZED: ErrorSpec(
        status=401,
        title="Unauthorized",
        retryable=False,
    ),
    ErrorCode.FORBIDDEN: ErrorSpec(
        status=403,
        title="Forbidden",
        retryable=False,
    ),
    ErrorCode.INVALID_CREDENTIALS: ErrorSpec(
        status=401,
        title="Invalid Credentials",
        retryable=False,
    ),
    ErrorCode.NOT_SIGNED_IN: ErrorSpec(
        status=401,
        title="Not Signed In",
        retryable=False,
    ),
    ErrorCode.SESSION_EXPIRED: ErrorSpec(
        status=401,
        title="Session Expired",
        retryable=False,
    ),
    ErrorCode.CSRF_FAILED: ErrorSpec(
        status=403,
        title="CSRF Check Failed",
        retryable=False,
    ),
    ErrorCode.OAUTH_STATE_INVALID: ErrorSpec(
        status=400,
        title="Sign-in Link Invalid",
        retryable=False,
    ),
    ErrorCode.OAUTH_FAILED: ErrorSpec(
        status=502,
        title="Sign-in Failed",
        retryable=True,
    ),
    ErrorCode.EMAIL_UNVERIFIED: ErrorSpec(
        status=403,
        title="Email Not Verified",
        retryable=False,
    ),
    # workspace
    ErrorCode.WORKSPACE_NOT_FOUND: ErrorSpec(
        status=404,
        title="Workspace Not Found",
        retryable=False,
    ),
    ErrorCode.WORKSPACE_ALREADY_EXISTS: ErrorSpec(
        status=409,
        title="Workspace Already Exists",
        retryable=False,
    ),
    ErrorCode.MEMBER_NOT_FOUND: ErrorSpec(
        status=404,
        title="Member Not Found",
        retryable=False,
    ),
    ErrorCode.INVITE_EXPIRED: ErrorSpec(
        status=400,
        title="Invite Expired",
        retryable=False,
    ),
    # provider
    ErrorCode.PROVIDER_NOT_CONFIGURED: ErrorSpec(
        status=402,
        title="Provider Not Configured",
        retryable=False,
    ),
    ErrorCode.PROVIDER_KEY_NOT_FOUND: ErrorSpec(
        status=404,
        title="Provider Key Not Found",
        retryable=False,
    ),
    ErrorCode.UPSTREAM_ERROR: ErrorSpec(
        status=502,
        title="Upstream Error",
        retryable=True,
    ),
    ErrorCode.BUDGET_EXCEEDED: ErrorSpec(
        status=402,
        title="Budget Exceeded",
        retryable=False,
    ),
    # idea
    ErrorCode.IDEA_NOT_FOUND: ErrorSpec(
        status=404,
        title="Idea Not Found",
        retryable=False,
    ),
    ErrorCode.IDEA_INVALID_TRANSITION: ErrorSpec(
        status=409,
        title="Invalid State Transition",
        retryable=False,
    ),
    ErrorCode.IDEA_NOT_OWNER: ErrorSpec(
        status=403,
        title="Not the Owner",
        retryable=False,
    ),
    ErrorCode.IDEA_CANCELLED: ErrorSpec(
        status=410,
        title="Idea Cancelled",
        retryable=False,
    ),
    # run
    ErrorCode.RUN_NOT_FOUND: ErrorSpec(
        status=404,
        title="Run Not Found",
        retryable=False,
    ),
    ErrorCode.RUN_ALREADY_RUNNING: ErrorSpec(
        status=409,
        title="Run Already in Progress",
        retryable=False,
    ),
    ErrorCode.RUN_INVALID_STATE: ErrorSpec(
        status=409,
        title="Invalid Run State",
        retryable=False,
    ),
    ErrorCode.RUN_TIMEOUT: ErrorSpec(
        status=504,
        title="Run Timeout",
        retryable=True,
    ),
    ErrorCode.RUN_CANCELLED: ErrorSpec(
        status=410,
        title="Run Cancelled",
        retryable=False,
    ),
    ErrorCode.SECRET_DECRYPT_FAILED: ErrorSpec(
        status=422,
        title="Stored Secret Unreadable",
        retryable=False,
    ),
    ErrorCode.RUN_EVENT_MALFORMED: ErrorSpec(
        status=500,
        title="Malformed Run Event",
        retryable=False,
    ),
    ErrorCode.RUN_STEP_LIMIT_REACHED: ErrorSpec(
        status=422,
        title="Run Step Limit Reached",
        retryable=False,
    ),
    ErrorCode.RUN_FAILED: ErrorSpec(
        status=500,
        title="Run Failed",
        retryable=False,
    ),
    ErrorCode.RUN_IDEMPOTENCY_MISMATCH: ErrorSpec(
        status=409,
        title="Idempotency Key Reused",
        retryable=False,
    ),
    ErrorCode.INTERVIEW_QUESTION_OPEN: ErrorSpec(
        status=409,
        title="Interview Question Already Open",
        retryable=False,
    ),
    ErrorCode.INTERVIEW_TURN_NOT_FOUND: ErrorSpec(
        status=404,
        title="Interview Turn Not Found",
        retryable=False,
    ),
    ErrorCode.RUN_ENQUEUE_FAILED: ErrorSpec(
        status=503,
        title="Run Could Not Be Queued",
        retryable=True,
    ),
    # research
    ErrorCode.RESEARCH_NOT_FOUND: ErrorSpec(
        status=404,
        title="No Research Yet",
        retryable=False,
    ),
    ErrorCode.RESEARCH_SNAPSHOT_NOT_FOUND: ErrorSpec(
        status=404,
        title="Research Snapshot Not Found",
        retryable=False,
    ),
    ErrorCode.RESEARCH_SNAPSHOT_CLOSED: ErrorSpec(
        status=409,
        title="Research Snapshot Closed",
        retryable=False,
    ),
    ErrorCode.RESEARCH_SOURCE_MISSING: ErrorSpec(
        status=422,
        title="Research Source Missing",
        retryable=False,
    ),
    ErrorCode.RESEARCH_COMPETITOR_NOT_FOUND: ErrorSpec(
        status=404,
        title="Competitor Not Found",
        retryable=False,
    ),
    ErrorCode.RESEARCH_NO_RESULTS: ErrorSpec(
        status=404,
        title="No Results Found",
        retryable=False,
    ),
    ErrorCode.RESEARCH_UPSTREAM_ERROR: ErrorSpec(
        status=502,
        title="Research Service Error",
        retryable=True,
    ),
    ErrorCode.RESEARCH_BUDGET_EXCEEDED: ErrorSpec(
        status=402,
        title="Research Budget Exceeded",
        retryable=False,
    ),
    # scoring
    ErrorCode.SCORE_INVALID_RUBRIC: ErrorSpec(
        status=400,
        title="Invalid Scoring Rubric",
        retryable=False,
    ),
    ErrorCode.SCORE_UPSTREAM_ERROR: ErrorSpec(
        status=502,
        title="Scoring Service Error",
        retryable=True,
    ),
    ErrorCode.SCORE_BUDGET_EXCEEDED: ErrorSpec(
        status=402,
        title="Scoring Budget Exceeded",
        retryable=False,
    ),
    # spec
    ErrorCode.SPEC_NOT_FOUND: ErrorSpec(
        status=404,
        title="Spec Not Found",
        retryable=False,
    ),
    ErrorCode.SPEC_CONFLICT: ErrorSpec(
        status=409,
        title="Spec Conflict",
        retryable=False,
    ),
    ErrorCode.SPEC_INVALID_TRANSITION: ErrorSpec(
        status=409,
        title="Invalid Spec Transition",
        retryable=False,
    ),
    # plan
    ErrorCode.PLAN_NOT_FOUND: ErrorSpec(
        status=404,
        title="Plan Not Found",
        retryable=False,
    ),
    ErrorCode.PLAN_CONFLICT: ErrorSpec(
        status=409,
        title="Plan Conflict",
        retryable=False,
    ),
    ErrorCode.PLAN_INVALID_TRANSITION: ErrorSpec(
        status=409,
        title="Invalid Plan Transition",
        retryable=False,
    ),
    # mcp
    ErrorCode.MCP_NOT_CONNECTED: ErrorSpec(
        status=503,
        title="MCP Service Not Connected",
        retryable=True,
    ),
    ErrorCode.MCP_UPSTREAM_ERROR: ErrorSpec(
        status=502,
        title="MCP Service Error",
        retryable=True,
    ),
    ErrorCode.MCP_TOOL_NOT_FOUND: ErrorSpec(
        status=404,
        title="MCP Tool Not Found",
        retryable=False,
    ),
    # export
    ErrorCode.EXPORT_NOT_FOUND: ErrorSpec(
        status=404,
        title="Export Not Found",
        retryable=False,
    ),
    ErrorCode.EXPORT_CONFLICT: ErrorSpec(
        status=409,
        title="Export Conflict",
        retryable=False,
    ),
    ErrorCode.EXPORT_UPSTREAM_ERROR: ErrorSpec(
        status=502,
        title="Export Service Error",
        retryable=True,
    ),
    ErrorCode.EXPORT_CANCELLED: ErrorSpec(
        status=410,
        title="Export Cancelled",
        retryable=False,
    ),
}


class MetisError(Exception):
    """Base exception with a stable error code.

    Attributes:
        code: The error code from the catalog.
        detail: Human-readable error message (optional, defaults from catalog).
        errors: List of validation errors (optional).
        meta: Additional metadata like `retry_after` (optional).
    """

    code: ErrorCode

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail
        self.errors = errors
        self.meta = meta
        super().__init__(detail)

    @property
    def status(self) -> int:
        """HTTP status code from the catalog."""
        return ERROR_CATALOG[self.code].status

    @property
    def title(self) -> str:
        """Human-readable title from the catalog."""
        return ERROR_CATALOG[self.code].title

    @property
    def retryable(self) -> bool:
        """Whether the request should be retried."""
        return ERROR_CATALOG[self.code].retryable

    def __repr__(self) -> str:
        return f"MetisError(code={self.code!r}, detail={self.detail!r})"


class NotFoundError(MetisError):
    """Generic 404 not found error."""

    code: ErrorCode = ErrorCode.ROUTE_NOT_FOUND


class ConflictError(MetisError):
    """Generic 409 conflict error."""

    code: ErrorCode = ErrorCode.CONFLICT


class AuthError(MetisError):
    """Generic 401 authentication error."""

    code: ErrorCode = ErrorCode.UNAUTHORIZED


class NotSignedInError(MetisError):
    """The request carries no session cookie; the user must sign in."""

    code: ErrorCode = ErrorCode.NOT_SIGNED_IN


class SessionExpiredError(MetisError):
    """The session cookie is unknown, expired, idle or revoked; sign in again."""

    code: ErrorCode = ErrorCode.SESSION_EXPIRED


class CsrfError(MetisError):
    """A cookie-authenticated mutation lacks the ``X-Metis-Client: web`` header."""

    code: ErrorCode = ErrorCode.CSRF_FAILED


class OAuthStateInvalidError(MetisError):
    """The sign-in callback's ``state`` is missing, unknown, expired or already used."""

    code: ErrorCode = ErrorCode.OAUTH_STATE_INVALID


class OAuthFailedError(MetisError):
    """The identity provider failed or sent an answer that did not verify."""

    code: ErrorCode = ErrorCode.OAUTH_FAILED


class EmailUnverifiedError(MetisError):
    """The identity provider has not verified the account's email."""

    code: ErrorCode = ErrorCode.EMAIL_UNVERIFIED


class PermissionDeniedError(MetisError):
    """Generic 403 authorization error."""

    code: ErrorCode = ErrorCode.FORBIDDEN


class InvalidInputError(MetisError):
    """Generic 400/422 validation error."""

    code: ErrorCode = ErrorCode.VALIDATION_FAILED


class UpstreamError(MetisError):
    """Generic 502 upstream error."""

    code: ErrorCode = ErrorCode.UPSTREAM_ERROR


class BudgetError(MetisError):
    """Generic 402 budget/exceeded error."""

    code: ErrorCode = ErrorCode.BUDGET_EXCEEDED


class RateLimitError(MetisError):
    """Generic 429 rate limit error."""

    code: ErrorCode = ErrorCode.RATE_LIMITED


class MemberUserNotFoundError(NotFoundError):
    """The email given for a new workspace member matches no user."""

    code: ErrorCode = ErrorCode.MEMBER_NOT_FOUND


class WorkspaceNotFoundError(NotFoundError):
    """The workspace does not exist."""

    code: ErrorCode = ErrorCode.WORKSPACE_NOT_FOUND


class AlreadyMemberError(ConflictError):
    """The user is already a member of the workspace."""


class MalformedEventError(MetisError):
    """A run event stream entry could not be decoded."""

    code: ErrorCode = ErrorCode.RUN_EVENT_MALFORMED


class SecretDecryptError(MetisError):
    """A stored secret could not be decrypted; the user should re-enter it."""

    code: ErrorCode = ErrorCode.SECRET_DECRYPT_FAILED


class ProviderNotConfiguredError(MetisError):
    """The workspace has no key for the provider; the user must add one."""

    code: ErrorCode = ErrorCode.PROVIDER_NOT_CONFIGURED


class ProviderKeyNotFoundError(NotFoundError):
    """The workspace has no key of that kind to delete."""

    code: ErrorCode = ErrorCode.PROVIDER_KEY_NOT_FOUND


class RunNotFoundError(NotFoundError):
    """404: no such run in the caller's workspace."""

    code: ErrorCode = ErrorCode.RUN_NOT_FOUND


class IllegalRunTransition(MetisError):  # noqa: N818  (named like ``IllegalTransition``)
    """409: the run cannot move from its status to the requested one."""

    code: ErrorCode = ErrorCode.RUN_INVALID_STATE


class RunAlreadyRunningError(MetisError):
    """409: the idea already has a queued, running or awaiting_user run."""

    code: ErrorCode = ErrorCode.RUN_ALREADY_RUNNING


class IdempotencyMismatchError(MetisError):
    """409: the ``Idempotency-Key`` already started a run on a different idea."""

    code: ErrorCode = ErrorCode.RUN_IDEMPOTENCY_MISMATCH


class QuestionAlreadyOpenError(ConflictError):
    """409: the run already waits on a different interview question (ask one at a time)."""

    code: ErrorCode = ErrorCode.INTERVIEW_QUESTION_OPEN


class InterviewTurnNotFoundError(NotFoundError):
    """404: no such interview turn in the caller's workspace."""

    code: ErrorCode = ErrorCode.INTERVIEW_TURN_NOT_FOUND


class RunEnqueueError(MetisError):
    """503: the run was saved but its job could not be queued; retry the same request."""

    code: ErrorCode = ErrorCode.RUN_ENQUEUE_FAILED


class ResearchNotFoundError(NotFoundError):
    """404: the idea has no closed research snapshot yet."""

    code: ErrorCode = ErrorCode.RESEARCH_NOT_FOUND


class SnapshotNotFoundError(NotFoundError):
    """404: no such research snapshot in the caller's workspace (or its idea is archived)."""

    code: ErrorCode = ErrorCode.RESEARCH_SNAPSHOT_NOT_FOUND


class SnapshotClosedError(ConflictError):
    """409: a closed research snapshot is immutable."""

    code: ErrorCode = ErrorCode.RESEARCH_SNAPSHOT_CLOSED


class ResearchSourceMissingError(MetisError):
    """422: competitors and market facts must cite a source URL."""

    code: ErrorCode = ErrorCode.RESEARCH_SOURCE_MISSING


class CompetitorNotFoundError(NotFoundError):
    """404: no such competitor in the caller's workspace."""

    code: ErrorCode = ErrorCode.RESEARCH_COMPETITOR_NOT_FOUND


__all__ = [
    "ErrorCode",
    "ErrorSpec",
    "ERROR_CATALOG",
    "MetisError",
    "NotFoundError",
    "ConflictError",
    "AuthError",
    "NotSignedInError",
    "SessionExpiredError",
    "CsrfError",
    "PermissionDeniedError",
    "InvalidInputError",
    "UpstreamError",
    "BudgetError",
    "RateLimitError",
    "MalformedEventError",
    "SecretDecryptError",
    "ProviderNotConfiguredError",
    "ProviderKeyNotFoundError",
    "MemberUserNotFoundError",
    "AlreadyMemberError",
    "WorkspaceNotFoundError",
    "RunNotFoundError",
    "IllegalRunTransition",
    "RunAlreadyRunningError",
    "IdempotencyMismatchError",
    "InterviewTurnNotFoundError",
    "QuestionAlreadyOpenError",
    "RunEnqueueError",
    "ResearchNotFoundError",
    "SnapshotNotFoundError",
    "SnapshotClosedError",
    "ResearchSourceMissingError",
    "CompetitorNotFoundError",
]


class IdeaNotFoundError(NotFoundError):
    """404: no such idea in the caller's workspace (also unknown, archived or foreign ideas)."""

    code: ErrorCode = ErrorCode.IDEA_NOT_FOUND


class IdeaNotOwnerError(PermissionDeniedError):
    """403: only the idea's creator or a workspace owner may change it."""

    code: ErrorCode = ErrorCode.IDEA_NOT_OWNER


class IllegalTransition(MetisError):  # noqa: N818  (the catalog and issue call it this)
    """409: the idea cannot move from its stage to the requested one."""

    code: ErrorCode = ErrorCode.IDEA_INVALID_TRANSITION
