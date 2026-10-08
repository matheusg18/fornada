# Tasks

## 1. Simulator app scaffolding

- [x] 1.1 Create the member with `uv init --package apps/simulator` (name `fornada-simulator`); add `httpx`, `langchain-anthropic`, `langchain-openai`, `pydantic-settings` with `uv add --package fornada-simulator`, the dev group (`ruff`, `pyright`, `pytest`, `taskipy`) with `--dev`, and `ipykernel`, `pandas` with `--group notebook`; verify `uv sync` resolves
- [x] 1.2 Configure ruff, pyright and pytest in `apps/simulator/pyproject.toml` like `apps/chat` (py313, `--import-mode=importlib`), add taskipy tasks `test`, `lint`, `lint:fix`, `format`, `format:check`, `typecheck`, `check` and `batch` (runs a default batch from a module entry point); drop the placeholder script; verify `uv run task --list` shows them
- [x] 1.3 Add `apps/simulator/runs/` to `.gitignore` and a "Simulator" section with commented `SIMULATOR__*` variables to the root `.env.example`

## 2. Settings (`persona-simulator`: batches, missing key)

- [ ] 2.1 Add `fornada_simulator/settings.py` (`SimulatorSettings`: provider, per-provider model and key, `api_url` default `http://localhost:8000`, `max_turns` 12, `concurrency` 1, `runs_per_persona` 4; `ConfigError` naming variables without echoing keys) and `tests/unit/test_settings.py`: defaults, overrides, missing key error names the variable and never contains the key; verify `uv run task test` passes

## 3. Personas (`persona-simulator`: five personas)

- [ ] 3.1 Review `.devcontainer/db/seed.sql` for the facts the goals use (valid and expired coupons, a third-party phone and order id, full days) and write them down in the module docstring of `fornada_simulator/personas.py`
- [ ] 3.2 Add `Persona` and the five-persona catalog with four goals each, following the table in the design; add `tests/unit/test_personas.py`: five distinct ids, at least four distinct goals each, and no persona text mentions `ferramenta`, `tool`, `prompt`, `eval` or `teste`; verify the tests pass
- [ ] 3.3 Ask the maintainer to review the persona and goal texts (core-adjacent: they define what `v0` is measured against) before moving on

## 4. API client and transcripts (`persona-simulator`: talks to the API, JSONL)

- [ ] 4.1 Add `fornada_simulator/client.py` (`send_message`, `ApiError` kinds `timeout`, `connect`, `status`, `bad_body`) and `tests/unit/test_client.py` with `httpx.MockTransport` and `pytest.mark.anyio`: path and body, replies in order, each failure kind; verify the tests pass
- [ ] 4.2 Add `fornada_simulator/transcript.py` (`Message`, `Transcript`, `append_jsonl`) and `tests/unit/test_transcript.py`: one parseable JSON line per transcript with every required field, appending twice yields two lines; verify the tests pass

## 5. Running conversations (`persona-simulator`: ends, replies reach the persona)

- [ ] 5.1 Add the persona system-prompt builder and `fornada_simulator/model.py` (provider factory from settings, temperature above 0), and `fornada_simulator/simulate.py::run_conversation` with the `[FIM]` marker, role inversion and the `completed`, `max_turns`, `api_error` and `simulator_error` outcomes
- [ ] 5.2 Add `tests/unit/test_simulate.py` with a scripted fake chat model and `MockTransport`: first message posted under a new UUID4, two replies reach the persona in order, `[FIM]` ends with `completed` and is not posted, a never-ending persona stops at the cap with `max_turns`, a 503 on turn 3 gives `api_error` with two turns kept, a fake model raising on turn 2 gives `simulator_error` with one turn kept, and a log-capture test shows no message text in log records; verify the tests pass
- [ ] 5.3 Add `run_batch` (even planning, goals in order, `asyncio.Semaphore`, appends each transcript to `runs/<run_id>.jsonl` as it finishes, one failing conversation never stops the batch) and tests: 20 planned jobs, four per persona with distinct goals, a failing conversation still leaves 20 lines; verify the tests pass

## 6. Summary and notebook (`persona-simulator`: notebook)

- [ ] 6.1 Add `fornada_simulator/summary.py` (per-persona conversations, outcome counts, average customer turns and seconds from a list of transcripts) with a unit test on a hand-made list
- [ ] 6.2 Create `notebooks/simulator.ipynb` with cells to: describe the setup and check the API is up; show the personas as a table; run one conversation and print it turn by turn; run the default batch; show the per-persona summary table; show how to load an earlier `runs/*.jsonl`. Keep cells thin (imports from the package) and clear outputs before saving
- [ ] 6.3 Document the app in `apps/simulator/README.md` (what it is, how to start the API and open the notebook in VS Code, `SIMULATOR__*` variables, runs folder, goals tied to seed facts)

## 7. Integration check

- [ ] 7.1 Run `uv run task check` in `apps/simulator`, `apps/api` and `apps/chat` and verify all pass
- [ ] 7.2 With the API running (`uv run task dev`), run the notebook end to end against the real agent: 20 conversations finish (every one with a recorded outcome), the JSONL has 20 lines, and the notebook is saved with outputs cleared; report the outcome counts and any persona that drifted
