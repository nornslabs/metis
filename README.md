# Metis

Metis is an agentic planning application.

## Structure

- `server/`: Python backend using FastAPI, LangGraph, and Arq.
- `web/`: Next.js frontend with Tailwind CSS and shadcn/ui.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management.
- [Node.js](https://nodejs.org/) and `npm` for the frontend.
- [Docker](https://www.docker.com/) for local infra (Postgres, Redis).

## Development

### Server

```bash
cd server
uv sync
# Set up .env from .env.example
uv run uvicorn metis.entrypoints.api:app --reload
```

### Web

```bash
cd web
npm install
npm run dev
```
