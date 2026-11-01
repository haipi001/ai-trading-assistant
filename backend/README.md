# AI Trading Assistant Backend

FastAPI backend maintained alongside the React frontend in the AI Trading Assistant monorepo.

## Safety defaults

- Live trading disabled.
- Live execution disabled and dry-run only.
- Automation restricted to read-only.
- No credentials committed to the repository.
- CORS restricted to the published frontend and local development.

## Local run

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

## Render deployment

`backend/render.yaml` defines the API, Postgres database, and Key Value cache. Select this Blueprint path from the unified repository; its service root is `backend/`. Secrets belong in the deployment platform, never in Git.
