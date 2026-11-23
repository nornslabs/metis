# PRD: Fix SHIP-283 / #71 — Protect API Docs Endpoint

## Problem Statement

The API docs endpoints (`/docs`, `/redoc`, `/openapi.json`) are publicly accessible with no authentication. Anyone can browse the full API schema and Swagger UI without signing in.

**Linear Issue**: [SHIP-283](https://linear.app/heimdallabs/issue/SHIP-283/protect-api-docs-endpoint)
**GitHub Issue**: [#71](https://github.com/nornslabs/metis/issues/71)

### Steps to Reproduce
1. Navigate to `http://localhost:8000/docs` (or `/redoc`, `/openapi.json`)
2. Observe: full API documentation is visible with no sign-in required

### Expected Behavior
The API docs endpoints should require a valid session cookie (same auth as all other `/v1` protected routes). Unauthenticated users should get a 401/redirect to sign-in.

---

## Root Cause Analysis

### File: `server/metis/entrypoints/api.py`

The FastAPI app is created with default docs URLs enabled:

```python
app = FastAPI(
    title="Metis API",
    summary="HTTP API for Metis",
    description=OPENAPI_DESCRIPTION,
    version=settings.app_version,
    openapi_tags=OPENAPI_TAGS,
    lifespan=_lifespan,
)
```

FastAPI defaults:
- `docs_url="/docs"` — Swagger UI (public)
- `redoc_url="/redoc"` — ReDoc (public)  
- `openapi_url="/openapi.json"` — OpenAPI schema (public)

None of these routes use `current_user` or any auth dependency.

### All other `/v1` routes are protected

Every other module router (`identity`, `ideas`, `research`, `scoring`) uses `CurrentUserDep` / `current_user` to require a valid session. The docs endpoints bypass this entirely.

---

## Solution Strategy

Disable FastAPI's auto-generated docs endpoints and replace them with custom routes that require `current_user` authentication.

### Approach

1. **Disable default docs** in `create_app()`: set `docs_url=None, redoc_url=None, openapi_url=None`
2. **Create `web/modules/docs/` module** with a router serving:
   - `GET /v1/docs` — Swagger UI HTML (requires `current_user`)
   - `GET /v1/redoc` — ReDoc HTML (requires `current_user`)  
   - `GET /v1/openapi.json` — OpenAPI schema JSON (requires `current_user`)
3. **Include the docs router** in `api.py` alongside other routers

### Why custom routes instead of middleware

FastAPI's built-in docs/swagger UI routes don't support adding dependencies. The standard pattern is to disable defaults and serve docs HTML manually with `get_swagger_ui_html()` / `get_redoc_html()` from `fastapi.openapi.docs`, wrapping them with `current_user`.

### URL prefix

Docs endpoints will be at `/v1/docs`, `/v1/redoc`, `/v1/openapi.json` — consistent with the rest of the API being under `/v1/`.

---

## Detailed Requirements

### FR-1: Docs endpoints require authentication
**Requirement**: `GET /v1/docs`, `GET /v1/redoc`, `GET /v1/openapi.json` all require a valid session cookie via `current_user`.

**Acceptance Criteria**:
- Unauthenticated request → 401 (or redirect to sign-in)
- Authenticated request → returns docs HTML / OpenAPI JSON

### FR-2: No public docs leakage
**Requirement**: FastAPI's default docs URLs (`/docs`, `/redoc`, `/openapi.json` at root) must not be accessible.

**Acceptance Criteria**:
- `docs_url=None`, `redoc_url=None`, `openapi_url=None` in `create_app()`
- Requests to root-level `/docs` etc. return 404

### FR-3: OpenAPI schema reflects protected routes
**Requirement**: The `/v1/openapi.json` endpoint returns the same schema as before, just behind auth.

**Acceptance Criteria**:
- Schema includes all `/v1/*` routes with their auth requirements
- `OPENAPI_DESCRIPTION` and `OPENAPI_TAGS` preserved

---

## Technical Implementation Plan

### File 1: `server/metis/modules/docs/__init__.py`
Module init, exports `router`.

### File 2: `server/metis/modules/docs/controller.py`
```python
from fastapi import APIRouter, Depends
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from metis.modules.auth import CurrentUserDep

router = APIRouter(prefix="/v1/docs", tags=["docs"])

@router.get("", include_in_schema=False)
async def swagger_ui(caller: CurrentUserDep):
    return get_swagger_ui_html(openapi_url="/v1/docs/openapi.json", title="Metis API - Swagger UI")

@router.get("/openapi.json", include_in_schema=False)
async def openapi_schema(caller: CurrentUserDep):
    return get_openapi(...)

@router.get("/redoc", include_in_schema=False)
async def redoc(caller: CurrentUserDep):
    return get_redoc_html(openapi_url="/v1/docs/openapi.json", title="Metis API - ReDoc")
```

### File 3: `server/metis/entrypoints/api.py`
- Set `docs_url=None, redoc_url=None, openapi_url=None` in `FastAPI()` constructor
- Import and include `docs.router`

---

## Acceptance Criteria (Definition of Done)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | `GET /v1/docs` without session → 401 | Manual + test |
| 2 | `GET /v1/redoc` without session → 401 | Manual + test |
| 3 | `GET /v1/openapi.json` without session → 401 | Manual + test |
| 4 | `GET /v1/docs` with valid session → Swagger UI HTML | Manual test |
| 5 | Root-level `/docs`, `/redoc`, `/openapi.json` → 404 | Manual test |
| 6 | All existing tests pass | `pnpm test` / `pytest` |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Swagger UI needs `openapi.json` at same origin | Medium | Low | Serve openapi.json at `/v1/docs/openapi.json`, reference it from Swagger UI |
| OpenAPI schema generation needs app instance | Low | Low | Use `get_openapi(app=app, ...)` in the schema endpoint |

---

## Appendix: Code Pointers

| Component | Path | Relevance |
|-----------|------|-----------|
| API app creation | `server/metis/entrypoints/api.py` | Disable default docs, include docs router |
| Auth dependency | `server/metis/modules/auth/deps.py` | `current_user`, `CurrentUserDep` |
| Router pattern example | `server/metis/modules/auth/controller/__init__.py` | `APIRouter(prefix=..., tags=...)` pattern |
| OpenAPI description/tags | `server/metis/entrypoints/api.py:42-57` | Reuse for schema generation |