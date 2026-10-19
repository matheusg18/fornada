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

## Scenario matrix

For phase 3's error analysis, `uv run task matrix` plays a persona × intent ×
complication matrix instead of the personas' fixed goals. Each cell is one
conversation, and its goal is the intent's text followed by the complication's
(`src/fornada_simulator/scenarios.py`). The persona's description still sets
tone and style. The cheater plays its style only: its attack goals stay in the
persona batch.

| Axis | Ids |
|---|---|
| Persona | `apressada`, `indecisa`, `pechincheira`, `mae_alergica`, `malandro` |
| Intent | `retirada`, `entrega`, `orcamento`, `duvida_cardapio`, `pos_pedido` |
| Complication | `nenhuma` (control), `data_lotada`, `troca_sabor`, `ferramenta_fora`, `tamanho_ambiguo` |

`data_lotada` asks for day +3, which the seed fills, so reset the database
before a launch. `ferramenta_fora` only asks for a dated order: the outage comes
from the API in chaos mode. That is why its 25 cells run only when named, never
next to the cells that need a working capacity check. The full run is two
launches into one run file:

```bash
# 1. Normal API, fresh seed: the 100 cells that need a working API.
uv run task matrix
# 2. API restarted with CHAOS__ENABLED=true CHAOS__CAPACITY_FAILURE_RATE=1,
#    fresh seed: the 25 outage cells, appended to the same run.
uv run task matrix --run-id <run_id> --complications ferramenta_fora
```

| Option | Meaning |
|---|---|
| `--complications a,b` | Run only the cells with these complications; an unknown id stops the launch before any conversation |
| `--run-id <id>` | Resume that run: cells it already recorded as `completed` or `max_turns` are skipped, error cells run again, new lines are appended |
| `--limit N` | Run at most N pending cells (the cost pilot: `--limit 5`) |

Matrix transcripts add `intent_id` and `complication_id`; persona batch lines
and older files have both null. A cell retried on resume appears twice in the
file, and its last line is the one that counts (`latest_per_cell`). At the end,
the command prints outcome counts per complication and per intent for the whole
run.

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
- on matrix runs, `fornada.simulator.intent.id` and
  `fornada.simulator.complication.id`: the cell. Client span only, never in
  baggage;
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
