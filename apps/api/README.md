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
| `APP__DAILY_CAPACITY_KG` | `15` | Oven capacity in kg for dates without a capacity override; must be > 0 |
| `LOG__LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `DB__URL` | – (required) | PostgreSQL URL (`postgresql://…`); in the dev container, the value of `$DATABASE_URI` |
| `TELEMETRY__ENABLED` | `false` | Export traces to the Collector (`true` in `.env.example`) |
| `TELEMETRY__OTLP_ENDPOINT` | `http://edot-collector:4318` | Base URL of the Collector's OTLP/HTTP receiver; the app adds `/v1/traces` |

Startup fails with a `ConfigError` that names the offending variable.

Logs are JSON, one object per line on stdout, with `timestamp` (UTC),
`level`, `logger` and `message`, plus any `extra` fields.

## Running the API

Tasks are defined with taskipy in `pyproject.toml`; run them from `apps/api`
(`uv run task --list` shows them all):

```bash
cd apps/api
uv run task dev      # development server with auto-reload on http://localhost:8000
```

`dev` runs from the repo root so the app finds `.env`. To serve without
reload, from the root: `uv run --package fornada-api fornada-api`.

- `GET /docs`: OpenAPI UI.
- `GET /health/db`: loads every model and returns the row count per table
  (`200 {"status": "ok", "tables": {...}}`), or `503 {"status": "unavailable"}`
  when the database cannot be reached. It never returns row contents.

## Conversations

`POST /conversations/{conversation_id}/messages` sends one customer message and
returns the bot's replies for that turn. The client generates the conversation
id (a UUID4); the first message to an unseen id starts the conversation, with
no "create" call.

```bash
curl -s -X POST "localhost:8000/conversations/$(python3 -c 'import uuid; print(uuid.uuid4())')/messages" \
  -H 'content-type: application/json' -d '{"text": "Oi, quero um bolo de chocolate"}'
# {"conversation_id":"…","replies":[{"text":"Olá! …"}]}
```

- `replies` holds one or more messages; clients must show all of them, in order.
- `422` when the id is not a UUID, or `text` is missing, not a string or blank.
- Replies come from the attendant agent (`agents/attendant/`): a LangGraph ReAct
  loop over the nine tools. It needs the LLM key and the database. A turn that
  fails (provider or database error, step limit) returns `503` with a generic
  body; the cause is logged with the conversation id.
- Memory: the conversation id is the LangGraph `thread_id`. Messages are saved
  by the PostgreSQL checkpointer (`checkpoints*` tables in the app database,
  created by the library on the first turn). They survive restarts.
- Each turn logs `conversation turn` with `conversation_id` and `text_length`.
  The message text is never logged.
- v0 has no authentication, rate limit or size cap on purpose (phase 5 measures
  those attacks first).

## System prompt and its version

The prompt is `fornada_api/agents/attendant/prompts/system.md`. Its version is
`sha256:` plus the first 12 hex digits of the SHA-256 of the file (UTF-8, `\n`
line endings), so it changes with any edit and can be reproduced with
`sha256sum`. The version is logged at startup (`prompt_version`) and saved on
every model answer (`response_metadata["prompt_version"]`) and in the graph
state, so each answer in a conversation says which prompt wrote it. Restart the
server after editing the prompt: `fastapi dev` reloads only on `.py` changes.

## Tracing

With `TELEMETRY__ENABLED=true`, the API sends traces over OTLP/HTTP to the EDOT
Collector (`TELEMETRY__OTLP_ENDPOINT`), which forwards them to Langfuse.
`fornada_api/core/telemetry.py` builds the pipeline by hand and the lifespan
starts and stops it; the app has no Langfuse SDK or credentials. Per request
you get:

- one SERVER span, `POST /conversations/{conversation_id}/messages`, from
  FastAPI's native OpenTelemetry (route template, method, status code);
- three INTERNAL children: `fastapi.dependencies`, `fastapi.endpoint` and
  `fastapi.serialization`;
- one CLIENT span per LLM HTTP call (the `httpx2` client under the Anthropic
  and OpenAI SDKs), in the same trace.

### Agent spans

The attendant makes its own spans by hand (`fornada_api/agents/attendant/`,
names in `tracing.py`), following the OpenTelemetry GenAI semantic conventions.
A turn looks like this:

```
POST /conversations/{conversation_id}/messages      SERVER   (FastAPI)
└─ invoke_agent fornada-attendant                   INTERNAL (attendant.py)
   ├─ chat claude-haiku-4-5                         CLIENT   (nodes.py, call_model)
   │  └─ POST                                       CLIENT   (httpx2, the provider call)
   ├─ execute_tool check_capacity                   INTERNAL (nodes.py, wrap_tool_call)
   ├─ execute_tool calculate_quote                  INTERNAL (same round: siblings)
   └─ chat claude-haiku-4-5                         CLIENT
      └─ POST                                       CLIENT
```

| Span | Attributes |
|---|---|
| `invoke_agent fornada-attendant` | `gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.conversation.id`, `session.id`, `fornada.prompt.version` |
| `chat {model}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.id`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.conversation.id`, `session.id`, `fornada.prompt.version` |
| `execute_tool {tool}` | `gen_ai.operation.name`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.type`, `gen_ai.conversation.id`, `session.id`; `check_capacity` adds `fornada.capacity.free_kg` |

- Tokens are only on `chat` spans. Langfuse turns each `chat` into a
  generation and prices it from the model name and usage; the turn and session
  totals are Langfuse's sums.
- No conversation content is recorded: no message text, system prompt, tool
  arguments or tool results.
- Status: an exception marks the span ERROR with `error.type` = the exception
  class (and the turn span too, since the turn fails). A tool that returns an
  error result marks only its `execute_tool` span (`error.type` =
  `tool_error`): the model reads the error and the turn goes on. A full day is
  not an error: `check_capacity` keeps an UNSET status and records
  `fornada.capacity.free_kg = 0`. Status descriptions never carry exception
  messages.

**Sessions.** Every agent span carries the conversation id as `session.id`,
which Langfuse maps to a session. Open Sessions in the Fornada project and
search for the conversation id: the session lists one trace per turn.

Spans are exported in batches, so they reach Langfuse about 5 s after the
request (or at shutdown, which drains the queue). To see them, open
http://localhost:3000, project Fornada → Tracing. The table lists every
observation (span); filter "Is Root Observation" to `True` for one row per
request, and open a row for the tree and timeline. Span attributes are under
Metadata.

To check delivery without the UI:

```bash
# dev container: Collector counters, before and after a request
curl -s edot-collector:8888/metrics | grep -E '^otelcol_(receiver_accepted|exporter_sent|exporter_send_failed)_spans'

# host: config or export errors (`docker compose ls` shows the project name)
docker compose -p fornada_devcontainer logs edot-collector
```

`otelcol_exporter_sent_spans{exporter="otlphttp/langfuse"}` grows with every
export; a growing `send_failed_spans` usually means a 401 (wrong
`LANGFUSE_OTLP_AUTH`) or a 404 (wrong endpoint path).

With the Collector unreachable, requests still answer normally; the exporter
logs a warning and retries for a few seconds at shutdown before dropping the
spans.

## Database

Models live in `fornada_api/models/` and mirror `.devcontainer/db/schema.sql`,
which stays the only source of DDL: the app never creates or alters app tables.
The LangGraph checkpointer is the one exception: it creates its own tables.
`fornada_api/infrastructure/engine.py` builds the async engine (psycopg 3) and
session factory; path operations get a session with `DbSessionDep` from
`fornada_api/dependencies`. Sessions never commit on their own. Relationships
are `lazy="raise"`: load them explicitly with `selectinload`/`joinedload`.

## Business rules and agent tools

Three layers, each one using only the one below it:

| Layer | Folder | Does |
|---|---|---|
| Repositories | `fornada_api/repositories/` | Queries only: rows in, models out. Never commit, never decide |
| Services | `fornada_api/services/` | Business rules (quote, lead time, capacity, coupons, refunds). Depend on the repository protocols in `services/ports.py`, raise `DomainError`s, never commit |
| Agent tools | `fornada_api/agents/attendant/tools.py` | The attendant's nine LangChain tools. One session and one transaction per call |

`build_tools(sessionmaker, clock=..., daily_capacity_kg=...)` returns the
tools; `default_tools()` wires them to the app's database and settings. Run
them through a LangGraph `ToolNode` inside a graph (escalation reads the
thread id from the run config). A failed rule comes back as a `ToolMessage`
with `status="error"` and a message for the LLM; unexpected errors are logged
and return a generic message.

| Tool | Does |
|---|---|
| `search_catalog(query?)` | Active products with price, cost, allergens (contains / may contain), pan sizes, neighborhoods |
| `check_capacity(date)` | Capacity, used and free kg, override reason, earliest dates and lead-time flags |
| `calculate_quote(product_slug, weight_kg, fulfillment, neighborhood?)` | Pan size, subtotal, delivery fee, total, 50% deposit |
| `create_order(...)` | Reuses or creates the customer; saves a `pending_payment` order with a fake payment link |
| `get_order(order_id, phone)` | Order details if the phone matches; "not found" otherwise |
| `cancel_order(order_id, phone, reason)` | Cancels under the refund policy, returns the refund |
| `apply_coupon(order_id, coupon_code)` | Validates the coupon (≤ 10%) and discounts a pending order |
| `send_message(phone, text, order_id?)` | Records a message row; nothing is sent |
| `escalate_to_human(reason, phone?)` | Records an escalation for the current thread |

**Deliberate v0 gaps** (measured in phases 3 and 5, closed in phase 6):
`create_order` checks neither capacity, lead time, past dates nor
confirmation, and retries create duplicates; `get_order`, `cancel_order`,
`apply_coupon` and `send_message` trust the phone or order id the LLM passes;
`search_catalog` exposes `cost_per_kg`; `get_order` returns the reference
photo description, which is untrusted customer text.

## Checks and tests

From `apps/api`:

| Task | What it runs |
|---|---|
| `uv run task check` | Everything below: lint, format check, type check and all tests |
| `uv run task lint` / `lint:fix` | `ruff check` (with `--fix`) |
| `uv run task format` / `format:check` | `ruff format` (with `--check`) |
| `uv run task typecheck` | `pyright` (standard mode) |
| `uv run task test` | All tests |
| `uv run task test:unit` | `tests/unit` |
| `uv run task test:integration` | `tests/integration` |

Integration tests (`tests/integration/`) use the dev container's seeded
database through `DATABASE_URI` and are skipped when it is not set. Tests that
write go through the `rollback_sessionmaker` fixture, whose commits stay inside
one outer transaction that is rolled back, so the seed is never changed. To
get back to a fresh seed after manual testing, use the reset command in
`.devcontainer/db/README.md`.

Service unit tests (`tests/unit/services/`) use the in-memory repositories in
`tests/unit/services/fakes.py`, with a fixed clock.
