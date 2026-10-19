# Tasks

## 1. Scenario catalog

- [x] 1.1 Add `apps/simulator/src/fornada_simulator/scenarios.py` with the five intents, the five complications (pt-BR texts per design.md) and `Cell` with its `goal`; verify with unit tests in `tests/unit/test_scenarios.py`: five distinct ids per catalog, no forbidden word (reuse the persona test's pattern), `nenhuma` adds nothing, the same cell builds the same goal, `data_lotada` asks for 3 days from today, `ferramenta_fora` names a date and no failure, `troca_sabor` and `tamanho_ambiguo` keep their anchors in every intent
- [x] 1.2 Add `plan_matrix(complications)` (interleaved, default without `ferramenta_fora`, unknown id raises) and verify with tests: 125 cells for the full list, 100 by default, 25 for `ferramenta_fora`, the first five cells cover the five personas, an unknown id names itself in the error

## 2. Transcript and client span fields

- [x] 2.1 Add optional `intent_id` and `complication_id` to `Transcript`; verify that an old run file in `runs/` still loads with both null and that a matrix transcript round-trips through `append_jsonl`/`read_jsonl`
- [x] 2.2 Pass the cell through `run_conversation` and `send_message` and set `fornada.simulator.intent.id` and `fornada.simulator.complication.id` on the client span only when present; verify with the in-memory exporter that matrix spans carry both, persona batch spans carry neither, and the `baggage` header still carries only the persona

## 3. Matrix batch, resume and CLI

- [x] 3.1 Add `run_matrix(settings, model, runs_dir, complications, run_id, limit)` that skips cells whose last recorded outcome is `completed` or `max_turns` and appends to the run file; verify with tests using the scripted model and mock transport: a resumed run plays only the missing cells, an `api_error` cell is replayed, a filtered resume appends to the same file
- [x] 3.2 Add `summarize_by(transcripts, key)` with last-line-per-cell dedupe and verify with unit tests for per-complication and per-intent rows
- [x] 3.3 Add `python -m fornada_simulator.matrix` (`--complications`, `--run-id`, `--limit`) and the taskipy task `matrix`; verify that an unknown complication exits before any conversation and that `uv run task matrix --limit 0` (or the help) runs without errors
- [x] 3.4 Run `uv run task check` in `apps/simulator` and verify it passes

## 4. Docs and notebook

- [x] 4.1 Update `apps/simulator/README.md` (matrix, filter, resume, fields) and `AGENTS.md` (the two launches: DB reset, chaos settings for `ferramenta_fora`, the `fornada.chaos.enabled` check); verify the documented commands match the CLI's `--help`
- [x] 4.2 Add a notebook cell that loads a matrix run file and shows the per-axis summary, committed with outputs cleared; verify with `jq '[.cells[].outputs | length] | add'` returning 0

## 5. Pilot and full run

- [x] 5.0 Add the matrix end rule to the persona's instructions (matrix conversations only), verify with unit tests that the matrix prompt has it and the persona batch prompt is unchanged, run `uv run task check`, then reset the DB and re-run the 5-cell pilot and verify no conversation ends with a bare `[FIM]` after one turn
- [x] 5.1 Reset the DB, start the API with telemetry on, run `uv run task matrix --limit 5`; verify 5 lines in the run file, 5 Langfuse sessions with the cell attributes on the client spans, and record the cost per conversation (projection for 125 must stay under US$ 10)
- [ ] 5.2 Reset the DB and run the 100 default cells; verify the printout shows 20 cells per complication and the run file has 100 cells counted once
- [ ] 5.3 Reset the DB, restart the API with `CHAOS__ENABLED=true CHAOS__CAPACITY_FAILURE_RATE=1`, resume the run with `--complications ferramenta_fora`; verify 125 cells in the file and that only `ferramenta_fora` turns have `fornada.chaos.enabled`
- [ ] 5.4 Build the conversation viewer as a private Claude artifact from the run file, following the `v0` viewer (index, chat, persona and outcome filters) plus intent and complication filters and a clickable 5 × 5 grid per persona; verify it loads all 125 conversations and each filter narrows the index

## Workflow follow-up

- Commit the run file `apps/simulator/runs/<run_id>.jsonl` (simulated, fictional data) as the phase 3 dataset.
- Archive the change after review.
