# Tasks

Tasks marked `TODO(human)` are core (AGENTS.md, phase 4: the deterministic asserts, the choice of critical cases and the pass^3 calculation). The agent leaves the marker with the commented sketch from design.md, keeps the related tests failing, then stops and waits for the maintainer. Package setup, isolation, the runner, the metric plumbing, the reporter's formatting, dataset drafting and docs are periphery. Run `uv run task check` from `apps/evals` at the end of each group that touches it.

## 1. App scaffold and dependency

- [ ] 1.1 Create `apps/evals` with `uv init --package apps/evals` (package `fornada-evals`, module `fornada_evals`). Copy the ruff, pyright, pytest and taskipy config from `apps/simulator`, and add tasks `test`, `test:unit`, `lint`, `format`, `typecheck` and `check` (no paid suite in `check`). Add `fornada-api` as a workspace dependency. Verify `uv sync` at the root succeeds and `uv run task check` passes in `apps/evals` with an empty test.
- [ ] 1.2 Check the latest `deepeval` release on PyPI and install it with `uv add --package fornada-evals deepeval`. Gitignore `.deepeval/` and `apps/evals/reports/`. Verify `uv run --package fornada-evals python -c "import deepeval"` works with `DEEPEVAL_TELEMETRY_OPT_OUT=1`.
- [ ] 1.3 Run `uv run task check` in `apps/api`, `apps/chat` and `apps/simulator`, and compare the test counts with before the install (442, 48, 99). If a DeepEval-installed plugin changes a result or adds warnings, disable it with `-p no:<plugin>` in that app's `addopts` and note why in a comment (design.md, decision 10). Verify all three pass with the same counts.

## 2. Dataset format and date rendering

- [ ] 2.1 Write failing unit tests in `apps/evals/tests/unit/test_dataset.py` for the spec's "Every golden case traces back…" and "Case dates are relative…" scenarios:
  - a complete case loads;
  - a missing source or an unknown check fails, naming the case;
  - `serving_rule` without a party size fails;
  - `critical: null` fails;
  - `{d+3:dd/mm}` on 2026-10-21 renders `24/10`, and `dd/mm/aaaa`, `dia-semana` and negative offsets render too;
  - text with other braces is left alone.

  Verify they fail.
- [ ] 2.2 Implement `fornada_evals.dataset`: a Pydantic model for `additional_metadata` (design.md, decision 6), loading through `EvaluationDataset.add_goldens_from_jsonl_file`, validation, and `render(text, run_day)`. Verify 2.1 passes.

## 3. Per-case isolation

- [ ] 3.1 Write failing integration tests in `apps/evals/tests/integration/test_isolation.py`, skipped without `DATABASE_URI` like the API's:
  - a schema gets the seed (12 products, run day +3 with 0 free kg);
  - an order written in one schema is invisible in another and in `public`;
  - the schema is dropped after the run, also when the run raises;
  - the sweep drops a leftover `eval_*` schema;
  - the run day equals the database's `CURRENT_DATE`.

  Verify they fail.
- [ ] 3.2 Implement `fornada_evals.isolation` (design.md, decision 3): an async context manager that yields the run day and an `async_sessionmaker` bound to the case's schema (with `hide_parameters=True`), plus `sweep()`. Verify 3.1 passes and that `public`'s order count is unchanged before and after the tests.

## 4. Runner

- [ ] 4.1 Write failing tests in `apps/evals/tests/integration/test_runner.py`, with a scripted fake chat model (a small local fake modeled on `apps/api/tests/unit/agents/fakes.py`, since that module is not importable across apps) and the real tools in an isolated schema:
  - a 2-turn case records 2 user turns and 2 assistant turns;
  - a turn with `check_capacity` then `calculate_quote` lists both `ToolCall`s with arguments and results, in order;
  - an error result is marked as an error in the turn's metadata;
  - an outage case fails every `check_capacity` with the generic error and delays nothing;
  - a non-outage case injects nothing;
  - a model that raises in turn 2 gives a failed run with the error recorded;
  - metadata holds the run day, prompt version, model, latencies, tokens and cost.

  Verify they fail.
- [ ] 4.2 Implement `fornada_evals.runner.run_case` (design.md, decisions 4 and 5): the graph with the in-memory saver and real tools on `FixedClock(run_day)`, chaos for outage cases, rendered turns, tool-call pairing by `tool_call_id`, latency, tokens and cost through the API's `TokenPrices`. Verify 4.1 passes and `uv run task check` passes.

## 5. Checks

- [ ] 5.1 Write the shared helpers in `fornada_evals.checks` (`tool_calls`, `reais`, `OWNER_WORDS` matching, the expected weight) and their unit tests: `reais` parses `R$ 1.234,56`, `R$194,80` and `R$ 80`; the owner match hits "Olá, dono!" and "para a dona" and misses "pedido do Donato"; the expected weight is 6.0 kg for 40 people and 1.0 kg for 3. Verify they pass.
- [ ] 5.2 Write failing unit tests in `apps/evals/tests/unit/test_checks.py`: for each of the nine checks, one failing and one passing recorded conversation, built as `ConversationalTestCase`s from the phase 3 open codes they cite (for example #6 for `no_past_date`, #40 for `order_on_open_date`, #16 for `no_order_after_outage`, #9 for `price_from_tool`, #63 for `escalation_has_phone`, #21 for `serving_rule`, #48 for `confirmation_before_order`, #12 for `requote_after_change`, #4 for `no_message_to_owner`), plus the spec's "Nothing to check" and "Same conversation, same verdict" scenarios. Every failing verdict's reason names the turn and the offending value. Verify they fail.
- [ ] 5.3 Write the metric plumbing: one `BaseConversationalMetric` per check (binary score, `threshold = 1.0`, `strict_mode`, `a_measure` delegating to `measure`, `is_successful` as the DeepEval docs recommend, `__name__`), and the registry from check id to class. Verify the dataset loader accepts exactly the registry's ids.
- [ ] 5.4 `TODO(human)`: in `fornada_evals.checks`, leave one marker per predicate with the commented sketch from design.md, decision 7, and the points to weigh, for `no_past_date`, `order_on_open_date`, `no_order_after_outage`, `price_from_tool`, `escalation_has_phone`, `serving_rule`, `confirmation_before_order`, `requote_after_change` and `no_message_to_owner`. Stop and wait for the maintainer; then verify 5.2 passes and `uv run task check` passes.

## 6. Golden dataset

- [ ] 6.1 Draft about 30 cases in `apps/evals/datasets/golden.jsonl` following the mix in design.md, decision 11. Each case cites its open code `#n`, uses date placeholders, and keeps self-contained turns (product, weight or party size, date, pickup or delivery, name, phone), 1–4 turns, in Brazilian Portuguese. Every case gets `"critical": null`. Verify every line parses as JSON and the loader's only error is the `null` critical mark.
- [ ] 6.2 `TODO(human)`: the maintainer marks each case `critical: true` or `false` (the suggestion: the cases behind the final scenarios, which are full day, outage, 40 people and flavor change). Stop and wait; then verify the dataset loads and a unit test asserts that every final scenario this layer covers has at least one critical case.

## 7. Suite and reporter

- [ ] 7.1 Write failing unit tests in `apps/evals/tests/unit/test_report.py` for the reporter, on handmade result lines:
  - a critical case with runs pass, pass, fail fails the gate;
  - 3 of 3 passes;
  - 7 of 10 non-critical cases against a 0.8 minimum fails and shows 70% against 80%;
  - mean cost above its ceiling fails, naming the cost check;
  - p95 uses nearest rank;
  - empty ceilings report without gating;
  - two run ids where one case flips give a variance share of 1 in N;
  - the Markdown lists the failed checks with reasons;
  - exit status 1 on a failed gate.

  Verify they fail.
- [ ] 7.2 `TODO(human)`: in `fornada_evals.report`, leave the marker with the commented sketch of the pass^k function (τ-bench estimator `C(c, k) / C(n, k)`, design.md, decision 8) and pass@1. Stop and wait; then verify the pass^k tests in 7.1 pass.
- [ ] 7.3 Implement the rest of the reporter: read `results-*.jsonl`, aggregate per case, the non-critical rate, cost, p95 and variance, `gate.toml` (empty ceilings by default), `report.md` and `summary.json`, and the exit status. Verify 7.1 passes.
- [ ] 7.4 Write `apps/evals/evals/test_golden.py`: parametrize over `(case, run_index)` (critical cases 3 runs, others 1), call `run_case`, `assert_test` with the case's metrics (`flaky=True` on non-critical cases), and append the result line to the run's per-worker file. Add the tasks `evals` (from the repo root: `DEEPEVAL_TELEMETRY_OPT_OUT=1 deepeval test run apps/evals/evals -n ${EVALS__WORKERS:-4} -id <run-id> -d failing`, then the reporter) and `evals:report`. Verify by running the suite on 2 cases (`-k`), including one critical: the run folder holds the result lines, `report.md` and `summary.json`; no `eval_*` schema is left behind; and no request goes to PostHog or Confident AI (check with `DEEPEVAL_TELEMETRY_OPT_OUT=1` set and no `CONFIDENT_API_KEY`).
- [ ] 7.5 Document the suite in `apps/evals/README.md` (what it checks and how each check maps to the taxonomy; how to run all of it, one case and the reporter over several runs; cost per run; the gate file; how to add a case) and add a short **Evals** section to `AGENTS.md` (the app, `uv run task evals`, not in `task check`, telemetry off, per-case schemas, the sweep). Verify the documented commands run as written.

## 8. `v0` baseline

- [ ] 8.1 Run the full suite twice on this commit (the prompt has not changed since `v0`) and record the cost of both runs. Verify both run folders have a `report.md`.
- [ ] 8.2 Run the reporter over both run ids and write `docs/evals/v0-baseline.md`:
  - the prompt version and model;
  - per-category results;
  - pass^3 per critical case and the non-critical rate;
  - pass@1 per case;
  - mean cost per conversation and p95 turn latency;
  - the variance section;
  - a comparison with the phase 3 counts for the same categories.

  Verify every number in the file comes from the two `summary.json` files.
- [ ] 8.3 Present the baseline to the maintainer for the gate thresholds in `gate.toml` (a core decision, not a `TODO(human)` in code) and record the chosen values and their reason in `docs/evals/v0-baseline.md`. Verify the reporter over the baseline runs applies them and reports the expected gate result: `v0` is expected to fail.

## Workflow follow-up

- Next changes: `add-ci-eval-gate` (GitHub Actions, regression report on the PR) and `add-allergen-judge` (layer 3, calibrated).
- Fixes for DATE and CAPACITY each start as their own change, with these cases already failing.
- Archive this change after review, with spec sync.
