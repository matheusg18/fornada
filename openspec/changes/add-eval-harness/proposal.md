# Proposal

## Why

Phase 3 left a failure taxonomy with counts and a decision per category (`docs/error-analysis/phase-3-taxonomy.md`, section 6), but no way to measure those failures again. Every later fix (today's date in the agent's state, `create_order` refusing a full day) needs a failing case first, and phase 4 needs a suite that a PR cannot pass while it makes the agent worse. This change builds that suite's first two layers and records the `v0` baseline. The deterministic checks and trajectory checks come first because they need no calibrated judge.

## What Changes

- A new workspace app, `apps/evals` (`fornada-evals`), built on **DeepEval** 4.x with pytest. It is kept out of `fornada-api`, so the API's dependencies and its `task check` stay as they are.
- A **golden dataset** in JSONL (`apps/evals/datasets/golden.jsonl`), in DeepEval's `ConversationalGolden` shape:
  - each case has a name, a scenario, the expected outcome and scripted customer turns;
  - its metadata names the taxonomy category, the phase 3 conversation it reproduces, which checks apply, whether it is critical and any setup (a `check_capacity` outage, the party size);
  - dates in the turns are written relative to the run day and rendered when the case runs.
- An **in-process runner**:
  - it plays a case's turns through the real attendant graph and the real model, with the nine real tools;
  - each case gets its own PostgreSQL schema, loaded from the dev schema and seed, so no case sees another's orders. This was a phase 3 caveat;
  - the clock is fixed to the seed's day, and an in-memory checkpointer is used;
  - the conversation becomes a DeepEval `ConversationalTestCase`, with each assistant turn's tool calls as `ToolCall`s (name, arguments, result), plus per-turn latency and token cost.
- **Layer 1, deterministic checks**, as DeepEval custom metrics (`BaseConversationalMetric`, no LLM):
  - DATE: no date argument earlier than the run day;
  - CAPACITY: `create_order` only for a date that a successful `check_capacity` showed open, with enough free kg and within the lead time;
  - PRICE: every price in a reply appears in a `calculate_quote` or `create_order` result of the same turn;
  - ESCALATION: `escalate_to_human` always carries a phone;
  - SIZE: a suggested weight follows the new 150 g per person rule.
- **Layer 2, trajectory checks**, also deterministic:
  - OUTAGE: no `create_order` after a failed `check_capacity` for that date;
  - confirmation: no `create_order` in the turn that first showed the quote;
  - flavor change: a new `calculate_quote` with the new product before any new price;
  - MESSAGE: no `send_message` written to the owner.
- **The gate.** Critical cases run 3 times and pass only when all 3 pass (pass^3). Non-critical cases run once and must reach a minimum pass rate. Mean cost per conversation and p95 turn latency are checks too. A reporter aggregates the run into a Markdown and JSON report listing each case, its runs and the checks that failed.
- **The `v0` baseline:** the suite runs twice on the current agent. The report records its numbers and the cases whose outcome changed between the two runs (the suite's variance).
- Not in this change:
  - the GitHub Actions gate, next change: `add-ci-eval-gate`;
  - the LLM judge for allergens and for "price gated on the date", which needs calibration first: `add-allergen-judge`;
  - any fix to the agent. The fixes come after this change, each one with its case already failing.

Phase: 4 (evals and CI gate). It stays within the frozen scope: no tool, feature or prompt change; the agent runs as it is. The checks map one to one to the categories marked "eval" in the phase 3 decisions.

## Capabilities

### New Capabilities

- `agent-evals`: the offline evaluation suite. It covers the golden dataset's format, how a case runs in isolation, the deterministic and trajectory checks, the pass^3 and minimum-rate gate, the cost and latency checks, and the run report.

### Modified Capabilities

None. The 150 g per person rule is a product decision recorded in the taxonomy. This change only checks it; giving the agent that rule is a fix for later.

## Impact

- **New:** `apps/evals/` (package, dataset, metrics, runner, reporter, unit tests). The workspace's `apps/*` glob picks it up.
- **Dependencies:** `deepeval` (latest, 4.3.1 at the time of writing), added to `fornada-evals` only. The workspace has one virtualenv, so DeepEval's pytest plugins (its own, `pytest-asyncio`, `pytest-xdist`, `pytest-repeat`, `pytest-rerunfailures`) become importable from every app. The other apps' suites must stay green, and any plugin that interferes is disabled in that app's `addopts`.
- **Telemetry:** DeepEval's anonymous usage telemetry is turned off for eval runs (`DEEPEVAL_TELEMETRY_OPT_OUT=1`). No result goes to Confident AI. DeepEval is never imported by app code: the runner reads tool calls from the graph's messages, not from DeepEval's `@observe` tracing.
- **Database:** each case creates and drops a schema named `eval_<id>` in the `fornada` database. The role already owns that database, so no new privilege is needed, and the `public` schema is never touched.
- **Cost:** the agent's model calls only, since this change has no LLM judge. About US$ 0.02–0.04 per conversation (phase 2 measured US$ 0.0375 per conversation of up to 8 turns), so a full run of about 30 cases with the critical ones tripled costs roughly US$ 1–2, within the US$ 20/month budget.
- **Docs:** `apps/evals/README.md` explains how to run it, and `AGENTS.md` gets a short section. The baseline report goes to `docs/evals/`.
