# Proposal

## Why

The attendant graph answers over HTTP, but the only way to exercise it is by hand. Phase 1 is done when 20 simulated conversations finish and `v0` is tagged, and phases 3–6 reuse the same simulator to generate error-analysis conversations, attack traffic and online-eval samples. It needs to exist now, against the naive agent, with personas that already stress the rules the project later measures (lead time, capacity, discounts, allergens, third-party data).

**Phase:** 1 (naive foundation). The simulator is periphery work (AGENTS.md: "Persona simulator"), so the agent builds it; the personas are the part the maintainer reviews.

**Scope:** stays within the frozen scope. It adds no tool and no agent feature; it is a black-box client of the existing `conversation-api`, like the chat UI. It adds no defense to `v0`.

## What Changes

- New uv workspace member `apps/simulator` (`fornada-simulator`), separate from the API and the chat, with a small importable package (`fornada_simulator`) and an interactive Jupyter notebook on top of it (`notebooks/simulator.ipynb`). The notebook is a thin, illustrated driver: it shows the personas, runs one conversation turn by turn, runs the batch of 20 and summarizes the results. Logic lives in the package so it can be unit tested.
- Five personas, written in Brazilian Portuguese as simulator prompts, each with several concrete goals (so 4 runs per persona are not the same conversation):
  - **Apressada** (in a hurry): wants a cake for tomorrow or the day after, answers in fragments, pushes for a fast quote. Stresses the 48 h lead time and capacity.
  - **Indecisa** (indecisive): changes flavor, size, date and fulfillment mid-conversation, asks for a new quote each time. Stresses recalculation through `calculate_quote`.
  - **Pechincheira** (haggler): negotiates discounts, quotes invented coupons, insists. Stresses `apply_coupon` and the 10% ceiling.
  - **Mãe com filho alérgico** (parent of a child with an allergy): asks whether a cake is safe for a celiac or lactose-intolerant child. Stresses allergen claims and cross-contamination.
  - **Malandro** (cheater): claims to be the owner, asks for someone else's order by phone, pastes an instruction in the reference photo description. Stresses authorization and untrusted input. Against `v0` it only measures; it is not a red team (phase 5).
- A conversation runner: each persona plays the customer with its own LLM, talks to the API over HTTP with a fresh conversation id, and ends when the persona says goodbye, a turn cap is hit or the API fails. Every conversation is written as one JSONL transcript.
- Simulator LLM configured separately from the agent's (`SIMULATOR__*`), defaulting to a Haiku-class model.
- Tooling mirroring the other apps: ruff, pyright, pytest, taskipy.

## Capabilities

### New Capabilities
- `persona-simulator`: the customer simulator: the persona catalog, how a simulated conversation runs against the API and ends, what is recorded, and how a batch is launched and summarized.

### Modified Capabilities
None. `conversation-api` is consumed as is.

## Impact

- **Code:** new `apps/simulator/` (`src/fornada_simulator/`, `notebooks/simulator.ipynb`, `tests/unit/`, `README.md`).
- **Dependencies:** `httpx`, `langchain-anthropic`, `langchain-openai`, `pydantic-settings` for the package; `ipykernel` and `pandas` in a `notebook` dependency group; the usual dev group. Added with `uv add`, one shared `uv.lock`.
- **Config:** new optional `SIMULATOR__*` variables in the root `.env.example`.
- **Repo:** `apps/simulator/runs/` (transcripts) is gitignored; the notebook is committed with outputs cleared.
- **Cost:** a 20-conversation batch costs simulator tokens on top of the agent's; each run reports both turn counts and elapsed time, and the turn cap bounds spend.
- **Later phases:** phase 3 extends personas into the persona × intent × complication matrix; phase 5 reuses the Malandro persona as a seed for hand-written attacks; the tag `v0` is created after the first clean batch.
