# Design

## Context

- **Inputs from phase 3.** `docs/error-analysis/phase-3-taxonomy.md` gives the categories, their counts and the decision per category (section 6). `phase-3-open-codes.md` gives one coded conversation per matrix cell, which is where each golden case comes from. See proposal.md, Why.
- **The agent.**
  - `build_graph(model, tools, prompt)` compiles with any checkpointer.
  - `build_tools(sessionmaker, clock=…, daily_capacity_kg=…, chaos=…)` takes its session factory, clock and chaos engine as arguments, so a harness can inject all three without touching app code.
  - Tool errors come back as `ToolMessage(status="error")`.
  - The prompt has not changed since the `v0` tag (only instrumentation and chaos mode were added to tools and graph since), so a baseline run on the current code measures `v0`'s behavior.
- **The database.**
  - The seed dates everything from `CURRENT_DATE` when it is loaded. It fills run day +3 and +4, and the server's time zone is UTC.
  - `schema.sql` creates unqualified tables, so it loads into whatever `search_path` names. The `fornada` role owns the database and can create schemas, but it cannot create databases. Loading `schema.sql` and `seed.sql` into a fresh schema takes about 0.26 s.
  - The graph's `ToolNode` runs a turn's tool calls concurrently (`asyncio.gather`). Phase 3 saw 7 parallel `check_capacity` calls, so a single shared connection rolled back at the end (`rollback_sessionmaker` in the API's integration tests) would break under concurrent sessions.
- **DeepEval 4.3.1** (2026-10-16), read from its docs and its installed source:
  - multi-turn cases are `ConversationalTestCase(turns=[Turn(role, content, tools_called=[ToolCall(name, input_parameters, output)])], metadata=…)`;
  - `EvaluationDataset.add_goldens_from_jsonl_file` reads `ConversationalGolden`s from lines with `scenario`, `turns`, `name`, `expected_outcome` and `additional_metadata`;
  - custom metrics subclass `BaseConversationalMetric` and implement `measure`, `a_measure`, `is_successful` and `__name__`; a non-LLM metric's `a_measure` just calls `measure`;
  - pytest integration: `assert_test(test_case, metrics)` run by `deepeval test run` (the docs advise against plain `pytest`), whose flags include `-n` (xdist), `-r` (pytest-repeat `--count`), `-id`, `-d failing`, `-m`, `-i` and `-c`;
  - `LLMTestCase` and `ConversationalTestCase` take `flaky=True`, which turns a failing assertion into a warning;
  - the agent trajectory metrics (`TaskCompletionMetric`, `StepEfficiencyMetric`, `PlanAdherenceMetric`, `PlanQualityMetric`) and component metrics on spans need DeepEval's own tracing (`@observe` or its LangChain callback) and an LLM judge;
  - `deepeval` auto-loads a `.env` from the working directory on import, sends anonymous usage telemetry (PostHog) unless `DEEPEVAL_TELEMETRY_OPT_OUT=1`, and registers a pytest plugin that loads wherever it is installed.

## Goals / Non-Goals

**Goals:**

- A failing case for each category marked "eval" in the phase 3 decisions (DATE, CAPACITY, OUTAGE, MESSAGE/ESCALATION, SIZE, PRICE), runnable on demand, with verdicts that do not depend on an LLM.
- Isolation strong enough that a case's verdict depends only on the case and the agent, not on run order or dev data.
- A `v0` baseline with its variance, so the gate's thresholds are set from data.

**Non-Goals:**

- The CI workflow (`add-ci-eval-gate`).
- LLM judges and the cases that need them: allergens, a price gated on the date, invented facts (`add-allergen-judge`).
- Fixing the agent, giving it the serving rule, or changing its model settings.
- Sending eval traces to Langfuse. The runner sets up no telemetry; that can come later if failures prove hard to read from the report.

## Decisions

### 1. A separate workspace app, `apps/evals`

`fornada-evals` depends on `fornada-api` (a workspace dependency) and `deepeval`. Layout:

```
apps/evals/
├─ pyproject.toml            # deepeval, fornada-api; ruff/pyright/pytest/taskipy like the other apps
├─ datasets/golden.jsonl
├─ gate.toml                 # min rate, cost and p95 ceilings
├─ src/fornada_evals/
│  ├─ dataset.py             # load + validate cases, render dates
│  ├─ isolation.py           # per-case schema
│  ├─ runner.py              # play a case, build the ConversationalTestCase
│  ├─ checks.py              # the nine checks as DeepEval metrics
│  └─ report.py              # aggregate results, gate, Markdown + JSON
├─ evals/test_golden.py      # the DeepEval suite (deepeval test run)
└─ tests/unit/               # the harness's own tests, in task check
```

- `tests/unit` covers the checks on recorded conversations, date rendering, dataset validation and the reporter's math. It uses no model and no database, so it joins `task check`.
- `evals/` is the paid suite and runs only through `uv run task evals`.

*Alternative:* `apps/api/tests/evals`. Rejected: it would put DeepEval and its plugins in the API's dependency list and make it easy to run the paid suite by accident with `task test`.

### 2. What DeepEval is used for, and what not

**Used:**
- `ConversationalGolden` JSONL as the dataset format;
- `ConversationalTestCase`, `Turn` and `ToolCall` as the record of a run;
- custom `BaseConversationalMetric`s for every check;
- `assert_test`, and `deepeval test run` with `-n`;
- `flaky=True` on non-critical cases.

This is the documented path for multi-turn, tool-using agents without tracing.

**Not used, and why:**

| DeepEval feature | Why not, here |
|---|---|
| `@observe` / LangChain callback tracing, and the trajectory metrics that need it (`TaskCompletion`, `StepEfficiency`, `PlanAdherence`) | It would put a vendor SDK in app code, which AGENTS.md rules out. These metrics are LLM-judged, and judges need calibration first. The tool calls are already in the graph's messages. |
| `ToolCorrectnessMetric` | It compares a single-turn `LLMTestCase`'s `tools_called` against a fixed `expected_tools` list. Our rules are conditional ("no order unless an earlier check showed capacity"), not a fixed list. |
| `ArgumentCorrectnessMetric`, `ToolUseMetric`, `GoalAccuracyMetric`, `ConversationalGEval`, `Expectations` | LLM-judged; they belong to phase 4's layer 3, after calibration. |
| `ConversationSimulator` | A second LLM per turn adds variance and cost to a gate. Exploration already has the persona simulator. |
| `-r` / `--repeat` | It repeats every test, critical or not, as unrelated items, so it has no per-case pass^3 and no minimum rate. |
| Confident AI (`deepeval login`, `--official`, `dataset.pull`) | It sends results and conversations to a third party. Customer-shaped data stays local (LGPD), and the report lives in the repo. |

### 3. Isolation: one PostgreSQL schema per run

For each run of a case:

1. `CREATE SCHEMA eval_<hex>`.
2. Execute `schema.sql` and `seed.sql` with `SET search_path TO eval_<hex>`, through psycopg on one connection, since each file is a multi-statement script.
3. Read `SELECT CURRENT_DATE` in that session as the run day.
4. Build an async engine with `connect_args={"options": "-c search_path=eval_<hex>"}`, and hand its `async_sessionmaker` to `build_tools`.
5. Run the case.
6. Dispose the engine and `DROP SCHEMA … CASCADE` in a `finally`.

A session-start sweep drops `eval_*` schemas left by a killed run.

- Each run has its own copy of the seed, so parallel tool calls and xdist workers are safe, and `public` is never touched (spec: "Each case runs in isolation").
- The run day comes from the database, not from `America/Sao_Paulo`. The seed is dated from the server's UTC `CURRENT_DATE`, and the two disagree from 21:00 to 24:00 in Brazil. The tools get `FixedClock(run_day)`, so the agent's lead-time math and the seed's full days line up.
- The engine keeps the API's `hide_parameters=True`.

*Alternatives:*
- **Shared connection with an outer transaction** (as in the integration tests): breaks under concurrent tool calls.
- **A database per case from a template**: needs `CREATEDB`, which the role lacks.
- **Resetting `public` per case**: destroys dev data and forces serial runs.

### 4. The runner: real graph, real model, in-process

`run_case(golden, run_index)`:

- **Graph:** `build_graph(build_chat_model(settings.llm), tools, load_system_prompt())`, compiled with LangGraph's in-memory saver, so the Postgres checkpointer tables stay clean. The thread id is a fresh UUID.
- **Tools:** `build_tools(sessionmaker, clock=FixedClock(run_day), daily_capacity_kg=settings.app.daily_capacity_kg, chaos=…)`. Chaos is `None`, except in outage cases (decision 5).
- **Turns:** the scripted customer turns are rendered (decision 6) and sent in order with `graph.ainvoke({"messages": [HumanMessage(text)]}, config)` and the API's recursion limit (25).
- **Recording each turn:**
  - the new messages map to one assistant `Turn`, whose content is the replies joined (the API's `turn_replies` rule);
  - each `AIMessage.tool_calls` entry is paired with its `ToolMessage` by `tool_call_id`, giving `ToolCall(name, input_parameters=args, output=content, …)`, with the error status in `Turn.metadata`;
  - latency is `time.perf_counter()` around `ainvoke`;
  - tokens come from each `AIMessage.usage_metadata`, and cost from `TokenPrices` with the configured prices, as the API's cost metric computes it.
- **The test case:** `metadata` holds the run day, the prompt version (`load_system_prompt().version`), the model, the case's metadata, per-turn latencies, total tokens and cost, and the error if a turn raised. A raised turn stops the run and marks it failed (spec: "A run records the conversation…").
- **Settings and keys:** the runner reads the API's settings (`get_settings()`), so the model, provider, keys and prices come from the root `.env`, as in dev. The `evals` task runs from the repo root, like the API's `dev` task.

### 5. Outage cases reuse chaos mode

An outage case gets `Chaos(ChaosSettings(enabled=True, latency_min_ms=0, latency_max_ms=0, capacity_failure_rate=1, seed=0))`. Every `check_capacity` then fails with the tool's generic error text, exactly as in the phase 3 `ferramenta_fora` cells, and nothing else is delayed.

Side effect: `price_increase_pct` must be above 0, so a second quote in an outage case is 10% higher. `price_from_tool` compares replies with the tools' own results, which already carry the raise, so the check stays correct. The case's scripted turns avoid a second quote.

*Alternative:* a test-only tool wrapper that fails `check_capacity`. Rejected: chaos mode already produces the same error the agent saw in phase 3, through the same code path.

### 6. Dataset format

One JSON object per line, readable by `add_goldens_from_jsonl_file`:

```json
{"name": "date-full-day-plus-3",
 "scenario": "Cliente com pressa pede bolo para daqui a 3 dias, dia lotado.",
 "expected_outcome": "Recusa o dia lotado, oferece a próxima data livre e não cria pedido.",
 "turns": [{"role": "user", "content": "Oi! Quero um bolo de chocolate de 2 kg pra retirar dia {d+3:dd/mm}. Meu nome é Ana, telefone 81 99999-1234."}],
 "additional_metadata": {"category": "CAPACITY", "source": "#6", "critical": true,
   "checks": ["no_past_date", "order_on_open_date", "confirmation_before_order"],
   "outage": false, "party_size": null, "flavor_change": null}}
```

- **Placeholders:**
  - `{d+N:dd/mm}`, `{d+N:dd/mm/aaaa}` and `{d+N:dia-semana}` (a pt-BR weekday name, such as "sexta-feira");
  - `N` may be negative, for a past-date case;
  - rendering is a regex substitution, not `str.format`, so customer text can contain braces.
- **`flavor_change`:** `{"turn": 3, "product": "bolo-limao"}` for `requote_after_change`.
- **Validation:** the loader validates `additional_metadata` with a Pydantic model: a known category, a source like `#n`, a non-empty list of known checks, and a party size required when `serving_rule` is listed. The loader fails on the first bad case (spec: "Every golden case traces back…").
- **Self-contained turns:** a scripted case cannot answer a question the agent improvises. Turns state everything up front (product, weight or party size, date, pickup or delivery, name, phone), and cases stay at 1–4 turns. A case whose turns stop matching what the agent asks is a dataset bug, found when reading its report.

### 7. Checks as custom DeepEval metrics

Each check is a `BaseConversationalMetric` with `threshold = 1.0`, `strict_mode = True`, `async_mode` delegating to `measure`, a binary score, and a `reason` listing each violation with its turn. A registry maps each check id from the dataset to its class.

The rule each check enforces is the maintainer's (AGENTS.md, phase 4 core: deterministic asserts). The agent writes:
- the metric plumbing;
- the helpers below;
- unit tests built from the phase 3 conversations, with one failing and one passing conversation per check, taken from the cited open codes.

The predicate bodies are `TODO(human)` with a commented sketch.

Shared helpers:

- `tool_calls(test_case) -> list[(turn_index, ToolCall)]`, in order.
- `reais(text) -> list[Decimal]`: parses `R$ 1.234,56`, `R$194,80` and `R$ 80`. The money fields are `price_per_kg`, `subtotal`, `delivery_fee`, `discount`, `total` and `deposit`.
- `OWNER_WORDS`: `dono`, `dona`, `proprietário`, `proprietária`, matched as whole words, case- and accent-insensitive, in vocative or recipient position (at the start, after "olá"/"oi", or after "para o/a").
- The expected weight for the serving rule: `max(1.0, ceil(0.15 × N / 0.5) × 0.5)` kg.

Sketch of one predicate, as it will appear under its marker:

```python
# TODO(human): no_past_date (DATE). Suggested sketch:
# for turn, call in tool_calls(test_case):
#     arg = {"check_capacity": "date", "create_order": "delivery_date"}.get(call.name)
#     if arg and (value := call.input_parameters.get(arg)):
#         if dt.date.fromisoformat(str(value)) < run_day:
#             violations.append(f"turn {turn}: {call.name}.{arg}={value} < {run_day}")
# Points to weigh: a malformed date string (count it as a violation, or skip?).
```

### 8. Gate, pass^k and the report

- **The suite.** `evals/test_golden.py` parametrizes over `(case, run_index)`. Critical cases get runs 1–3, non-critical cases get run 1, and test ids read like `date-full-day-plus-3[run2]`.
  - Each test calls `run_case`, then `assert_test(test_case, metrics)`. A non-critical test case has `flaky=True`, so its failure warns instead of failing pytest.
  - With that split, pytest's exit status already means "some critical run failed".
  - Each test also appends one JSON line (case, run, verdict per check, reasons, latencies, tokens, cost, prompt version, model) to `apps/evals/reports/<run-id>/results-<xdist worker>.jsonl`. Per-worker files avoid concurrent appends.
- **The reporter.** `fornada_evals.report`, behind `uv run task evals:report <run-id> [<run-id>…]`, reads the result lines and computes:
  - **pass^k per case.** `TODO(human)` (AGENTS.md: the pass^3 calculation is core). The sketch is τ-bench's unbiased estimator, `pass^k = C(c, k) / C(n, k)` for `c` passing runs out of `n`. With `n = k = 3` it is 1 only when all 3 pass, which is the gate. Over two suite runs (`n = 6`) it estimates the same quantity with less noise. pass@1 (`c / n`) is reported next to it.
  - **The non-critical pass rate.**
  - **Mean cost per run, and p95 turn latency** (nearest rank over every turn of every run).
  - **Variance:** cases whose verdict differs between the given run ids, and their share.

  It writes `report.md` and `summary.json` into the run's folder and exits with status 1 when the gate fails.
- **Gate settings.** `apps/evals/gate.toml` holds `min_noncritical_rate`, `max_cost_per_run_usd` and `max_p95_turn_latency_s`. They start empty, and the reporter then reports without gating on them. The maintainer sets them from the baseline.
- **`uv run task evals`** runs `deepeval test run apps/evals/evals -n 4 -id <run-id> -d failing`, then the reporter, with `DEEPEVAL_TELEMETRY_OPT_OUT=1`. `-n 4` keeps about 4 conversations in flight, which is within the Anthropic rate limits at Haiku volume. A variable overrides it.
- **How the effect is measured.**
  - Correctness: pass^3 per critical case, the non-critical pass rate and pass@1 per case.
  - Cost: the mean US$ per conversation, from the agent's own token usage and the configured prices. Spot-check it against Langfuse when tracing is on.
  - Latency: p95 per turn.
  - Stability: the share of cases that flip between two runs on the same commit.

### 9. Model settings: evaluated as shipped

The suite runs the agent with the provider's default temperature, as the API does. The roadmap's advice to "fix temperature and seeds where possible" is honored by measuring first: the baseline runs twice, and the variance section shows how unstable the gate would be.

If the flip share is high, a separate change adds a temperature setting to `app-config`, used by the API and the suite alike, so the gate never tests a configuration that does not ship. Anthropic's API has no sampling seed.

*Alternative:* temperature 0 in the suite only. Rejected: the gate would pass a configuration customers never talk to.

### 10. Keeping DeepEval out of the other apps' way

The workspace has one virtualenv, so `deepeval`'s pytest plugin and its dependencies (`pytest-asyncio`, `pytest-xdist`, `pytest-repeat`, `pytest-rerunfailures`) load in every app's pytest.

- DeepEval's plugin is quiet for sessions with no DeepEval assertions.
- The tasks check that `apps/api`, `apps/chat` and `apps/simulator` still pass `task check` with identical counts. If a plugin changes anything (for example, `pytest-asyncio` warnings next to `anyio`), it is disabled with `-p no:<plugin>` in that app's `addopts`.
- `.deepeval/` (DeepEval's cache) and `apps/evals/reports/` are gitignored.

### 11. Building the dataset

About 30 cases, drafted by the agent from the open codes, each citing its `#n`. The target mix covers every eval category and every final scenario this layer can check:

| Category / scenario | Cases | Checks |
|---|---|---|
| DATE (wrong year, "que dia é hoje?", DD/MM without year, weekday) | 6 | `no_past_date` |
| CAPACITY: full day +3 (final scenario), short day, unchecked date | 5 | `order_on_open_date`, `no_past_date` |
| OUTAGE (final scenario `check_capacity` down) | 4 | `no_order_after_outage`, `order_on_open_date` |
| PRICE: math by hand, double delivery fee | 4 | `price_from_tool` |
| Flavor change after the quote (final scenario) | 3 | `requote_after_change`, `price_from_tool` |
| SIZE: 40 people (final scenario) and other party sizes | 3 | `serving_rule` |
| MESSAGE / ESCALATION | 4 | `no_message_to_owner`, `escalation_has_phone` |
| Confirmation before the order | 3 | `confirmation_before_order` |

- Allergen and "price gated on the date" cases wait for the judge change, which brings the dataset to about 50.
- **Which cases are critical is the maintainer's call** (AGENTS.md, phase 4 core). The agent drafts every case with `"critical": null`, and the loader rejects `null`, so the suite cannot run until each case is marked. The suggestion is that the cases behind the final scenarios (full day, outage, 40 people, flavor change) are critical.

## Risks / Trade-offs

- **[Scripted turns drift from the conversation]** The agent asks something the script does not answer, and later turns stop making sense. → Self-contained turns and 1–4 turns per case. The report shows the full conversation of a failed run, so drift is visible and gets fixed in the dataset, not in the check.
- **[Regex checks give false verdicts]** `price_from_tool` reads amounts and `no_message_to_owner` reads words; phrasing can fool both. → Unit tests from the phase 3 conversations, with passing and failing examples. Every reason quotes the matched text, so a wrong verdict is visible in the report. A check that proves unreliable moves to the judge change.
- **[`price_from_tool` is strict]** Restating an earlier quote in a later turn, without calling the tool again, fails it, as the phase 3 decision states ("in the same turn"). → Kept as decided. If the baseline shows that this flags harmless restatements, the maintainer can relax it to "same or earlier turn, with no change to product, weight or delivery since". That is a check change, not a design change.
- **[Flaky gate]** LLM output varies between runs. → pass^3 on critical cases, the baseline run twice with a variance section, and decision 9.
- **[Cost]** About US$ 1–2 per full run, the agent's model calls only. → The suite is opt-in (not in `task check`), each run reports its cost, and a cost ceiling is part of the gate.
- **[DeepEval API churn]** 4.x moves fast (4.3.1 shipped 5 days before this design). → `uv.lock` pins it. Only stable, documented classes are used (`ConversationalTestCase`, `Turn`, `ToolCall`, `BaseConversationalMetric`, `assert_test`, the JSONL loader).
- **[`.env` auto-load]** `import deepeval` reads `.env` from the working directory. → The suite runs from the repo root, whose `.env` the API already reads. Nothing new is loaded.
- **[Leftover schemas]** A killed run leaves `eval_*` schemas behind. → The sweep at session start, plus the reset command in `.devcontainer/db/README.md`.

## Migration Plan

Additive only. `uv sync` installs the new app, and nothing in the API, chat or simulator changes behavior. Rollback means removing `apps/evals` and its lockfile entries.

## Open Questions

- The gate thresholds (`min_noncritical_rate`, the cost ceiling and the p95 ceiling) are set by the maintainer after the baseline. They live in `gate.toml`, so setting them changes no spec or task.
