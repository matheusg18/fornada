# fornada-evals

The golden suite: scripted customer conversations run against the real attendant
(its graph, prompt, configured model and nine tools), scored by deterministic
checks, and gated on pass^3 for critical cases. Every case comes from a coded
phase 3 conversation (`docs/error-analysis/phase-3-open-codes.md`), and every
check from a category the phase 3 decisions marked "eval"
(`docs/error-analysis/phase-3-taxonomy.md`, section 6).

The suite calls the model, so it is paid and opt-in: `uv run task check` runs
only its own unit and integration tests, never a golden case.

## What it checks

Each case lists the checks that apply to it. A check is a DeepEval conversational
metric with a binary score and no LLM (`src/fornada_evals/checks.py`); its reason
names the turn and the tool values it saw.

| Check | Category | Fails when |
|---|---|---|
| `no_past_date` | DATE | a `check_capacity` or `create_order` date is earlier than the run day |
| `order_on_open_date` | CAPACITY | `create_order` targets a date never checked, without room for the weight, or outside the lead time |
| `no_order_after_outage` | OUTAGE | `create_order` follows a failed `check_capacity` for that date |
| `price_from_tool` | PRICE | a reply states an amount in reais that no quoting tool returned in the same turn |
| `requote_after_change` | PRICE | after the customer changes flavor, no `calculate_quote` runs for the new product |
| `serving_rule` | SIZE | the quoted or ordered weight is not 150 g a person, rounded up to the next half kilo |
| `confirmation_before_order` | CAPACITY | `create_order` runs before its quote was shown in an earlier turn |
| `escalation_has_phone` | ESCALATION | `escalate_to_human` has no phone |
| `no_message_to_owner` | MESSAGE | a `send_message` text addresses the owner ("Olá, dono") |

Allergen claims, a price gated on the date and invented facts need a calibrated
LLM judge and come in a later change.

## How a case runs

- **Dataset:** `datasets/golden.jsonl`, one case a line in DeepEval's
  `ConversationalGolden` shape. `additional_metadata` holds the category, the
  source conversation (`#n`), `critical`, the checks and any setup (`outage`,
  `party_size`, `flavor_change`). The loader rejects a case it cannot run.
- **Isolation:** each run gets its own schema `eval_<hex>` in the test database
  (`TEST_DATABASE_URI`, never the dev one), loaded with `schema.sql` and
  `seed.sql` pinned to the seed day, Monday 2026-03-09, and dropped afterwards.
  Days +3 and +4 are full, +5 has 2 kg free and +8 to +11 have 0.5 kg each.
- **Dates:** customer turns write `{d+N:dd/mm}`, `{d+N:dd/mm/aaaa}` or
  `{d+N:dia-semana}`, rendered from the seed day, so a case reads the same on
  any calendar day.
- **Outage cases** run the tools with chaos mode making every `check_capacity`
  fail, with no added latency.
- **Critical cases** run 3 times and pass only if all 3 pass. Non-critical cases
  run once; in pytest their failures only warn, and the report gates them on a
  minimum rate.

## Running

From `apps/evals`, with an LLM key in the root `.env` (the agent reads it as the
API does):

```bash
uv run task evals                                  # every case
uv run task evals -k size-40-people                # one case (any pytest -k expression)
uv run task evals --workers 2                      # conversations in flight (default 4, or EVALS__WORKERS)
uv run task evals:report <run-id> [<run-id>...]    # report again, or over several runs
```

`task evals` picks a run id (`20261026T154722-03ab`), runs `deepeval test run`
from the repo root with `DEEPEVAL_TELEMETRY_OPT_OUT=1`, and then the reporter.
The model provider is the only third party the suite calls. Without
`TEST_DATABASE_URI` it stops before any case. At the start it drops `eval_*`
schemas left by a killed run, so run one suite at a time.

Results land in `reports/<run-id>/` (gitignored):

- `results-<worker>.jsonl`: one line per case run, with each check's verdict and
  reason, latencies, tokens, cost, prompt version, model and the conversation;
- `report.md`: the gate, each case's runs passed, pass^3 and pass@1, and every
  failed run with its reasons and conversation;
- `summary.json`: the same, for scripts and CI.

The exit status is 1 when the gate fails.

Reporting over two runs (`evals:report <a> <b>`) estimates pass^3 from all their
runs (τ-bench's `C(c, 3) / C(n, 3)`) and lists the cases whose verdict flipped,
which is how to measure the suite's variance on one commit. That report is
written into the first run id's folder, replacing its single-run report.

**Cost:** a full run is 52 conversations (10 critical cases × 3 and 22 × 1). With
Claude Haiku 4.5 a conversation cost about US$ 0.017 in the first runs, so about
US$ 0.90 a run.

## The gate

`gate.toml` holds the ceilings. A key that is missing or commented out is reported
without gating:

| Key | Gate |
|---|---|
| `min_noncritical_rate` | share of non-critical runs that pass every check (0 to 1) |
| `max_cost_per_run_usd` | mean US$ per conversation run |
| `max_p95_turn_latency_s` | p95 turn latency across all runs, nearest rank |

The critical cases always gate. The ceilings are set from the `v0` baseline.

## Adding a case

1. Start from a coded conversation that shows the failure, and cite it as `source`.
2. Write self-contained customer turns (product, weight or party size, date,
   pickup or delivery with the address, name and phone), 1 to 4 of them, in
   Brazilian Portuguese, with date placeholders. A scripted case cannot answer a
   question the agent improvises.
3. Pick the date from the seed's calendar above, list only the checks the case is
   about, and add the setup a check needs (`party_size` for `serving_rule`,
   `flavor_change` for `requote_after_change`, `outage` for an outage case).
4. Mark `critical`. Every final scenario this layer covers keeps at least one
   critical case (`tests/unit/test_golden.py`).
5. Run it alone (`uv run task evals -k <name>`) and read its conversation in the
   report. A case whose turns stop matching what the agent asks is a dataset bug.
