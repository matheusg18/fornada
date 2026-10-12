# fornada-simulator

LLM personas that play customers against `fornada-api` over HTTP. Five
personas (in a hurry, indecisive, haggler, parent of a child with an allergy,
cheater), each with several goals. The simulator never touches the database
or imports the API's code.

## Running

Start the API first (see `apps/api/README.md`). Then, from `apps/simulator`:

```bash
uv run task batch    # default batch: 4 runs × 5 personas = 20 conversations
```

Each conversation is appended to `apps/simulator/runs/<run_id>.jsonl` as it
finishes, with its persona, goal, conversation id, outcome and messages. The
notebook in `notebooks/simulator.ipynb` runs one conversation turn by turn, runs
a batch and summarizes it per persona. Its kernel is the root `.venv`, with the
notebook group installed (`uv sync --group notebook`).

## Configuration

Settings come from the environment and the root `.env` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `SIMULATOR__PROVIDER` | `anthropic` | `anthropic` or `openai`; its API key is required |
| `SIMULATOR__ANTHROPIC__API_KEY`, `SIMULATOR__ANTHROPIC__MODEL` | —, `claude-haiku-4-5` | The persona's model, configured apart from the agent's |
| `SIMULATOR__OPENAI__API_KEY`, `SIMULATOR__OPENAI__MODEL` | —, `gpt-5-mini` | Same, for OpenAI |
| `SIMULATOR__API_URL` | `http://localhost:8000` | Base URL of `fornada-api` |
| `SIMULATOR__MAX_TURNS` | `12` | Customer messages before a conversation is cut off |
| `SIMULATOR__CONCURRENCY` | `1` | Conversations running at once |
| `SIMULATOR__RUNS_PER_PERSONA` | `4` | Conversations per persona in a batch |
| `TELEMETRY__ENABLED` | `false` | Send traces to the Collector; shared with the API |
| `TELEMETRY__OTLP_ENDPOINT` | `http://edot-collector:4318` | Collector's OTLP/HTTP base URL; shared with the API |

## Tracing

With `TELEMETRY__ENABLED=true`, each customer message the simulator posts is one
span of kind CLIENT, `POST /conversations/{conversation_id}/messages`, from the
service `fornada-simulator`. It is the root of that turn's trace: the request
carries its context in a W3C `traceparent` header, so the API's SERVER span and
the agent's spans join the same trace. One trace per turn; the conversation is
the Langfuse session.

The client span carries:

- `session.id` and `gen_ai.conversation.id`: the conversation id;
- `fornada.simulator.persona.id` and `fornada.simulator.run.id`: the persona
  and the batch. They stay on this span; the API reads nothing from the
  request but `traceparent`;
- `http.request.method`, `url.template`, `server.address`, `server.port` and
  `http.response.status_code`.

A failed post (connection, timeout, non-200 status, unreadable body) sets the
span's status to ERROR, with no description. `error.type` is the status code
for a non-200 and `connect`, `timeout` or `bad_body` otherwise. No message or
reply text goes into a span.

The persona's own LLM calls are not traced, so a session's cost in Langfuse is
the agent's cost only.

Spans are exported in batches. `run_batch` flushes them before it returns, and
the batch command shuts the pipeline down at exit, so a run that exits right
away still exports every trace root. In the notebook, the setup cell registers
tracing once per kernel, and the single-conversation cell calls
`flush_tracing()`.

`fornada_simulator/telemetry.py` builds the pipeline; `client.py` makes the span.

## Checks and tests

```bash
uv run task check    # ruff, format check, pyright, pytest
```
