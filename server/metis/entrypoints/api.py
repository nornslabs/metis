"""FastAPI application entrypoint for the API process.

This is a minimal app so the API binds and stays up. The real ``/v1`` routes
(interviews, ideas, scoring, runs, events) are added per PRD as the modules
land. See ``server-context.md`` for the API conventions.
"""

from fastapi import FastAPI

app = FastAPI(title="Metis", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "metis", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("metis.entrypoints.api:app", host="0.0.0.0", port=8000)