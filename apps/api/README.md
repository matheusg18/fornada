# fornada-api

FastAPI service that runs the LangGraph ordering agent.

## Configuration

Settings come from environment variables and the `.env` file at the repo root
(the environment wins). Copy `.env.example` to `.env` and fill in an API key
and the database URL.
Run every command from the repo root so `.env` is found.

Nested settings use a double underscore, `NAMESPACE__FIELD`:

| Variable | Default | Meaning |
|---|---|---|
| `LLM__PROVIDER` | `anthropic` | Active provider: `anthropic` or `openai` |
| `LLM__ANTHROPIC__API_KEY` / `LLM__ANTHROPIC__MODEL` | – / `claude-haiku-4-5` | Required when Anthropic is active |
| `LLM__OPENAI__API_KEY` / `LLM__OPENAI__MODEL` | – / `gpt-5-mini` | Required when OpenAI is active |
| `APP__TIMEZONE` | `America/Sao_Paulo` | IANA time zone for "now" and dates |
| `LOG__LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `DB__URL` | – (required) | PostgreSQL URL (`postgresql://…`); in the dev container, the value of `$DATABASE_URI` |

Startup fails with a `ConfigError` that names the offending variable.

Logs are JSON, one object per line on stdout, with `timestamp` (UTC),
`level`, `logger` and `message`, plus any `extra` fields.

## Running the API

From the repo root, with `.env` filled in:

```bash
# Development server with auto-reload on http://localhost:8000
uv run --package fornada-api fastapi dev apps/api/src/fornada_api/main.py

# Same app, no reload
uv run --package fornada-api fornada-api
```

- `GET /docs`: OpenAPI UI.
- `GET /health/db`: loads every model and returns the row count per table
  (`200 {"status": "ok", "tables": {...}}`), or `503 {"status": "unavailable"}`
  when the database cannot be reached. It never returns row contents.

## Database

Models live in `fornada_api/models/` and mirror `.devcontainer/db/schema.sql`,
which stays the only source of DDL: the app never creates or alters tables.
`fornada_api/infrastructure/engine.py` builds the async engine (psycopg 3) and
session factory; path operations get a session with `DbSessionDep` from
`fornada_api/dependencies`. Sessions never commit on their own. Relationships
are `lazy="raise"`: load them explicitly with `selectinload`/`joinedload`.

## Tests

```bash
uv run --package fornada-api pytest                 # everything
uv run --package fornada-api pytest -m "not integration"
```

Integration tests (`tests/integration/`) use the dev container's seeded
database through `DATABASE_URI` and are skipped when it is not set. They never
commit; reset the database with the command in `.devcontainer/db/README.md`.
