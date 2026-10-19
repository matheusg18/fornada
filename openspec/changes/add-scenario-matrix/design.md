# Design

## Context

The simulator (`apps/simulator`) plays five personas against the API over HTTP. Each persona carries four fixed goals (`personas.py`). `plan_jobs` cycles through them, and `run_batch` writes one JSONL line per conversation to `apps/simulator/runs/<run_id>.jsonl`. The persona's system prompt is `description + goal + chat rules` (`build_system_prompt`). Client spans already carry the persona and run ids. Only the persona travels as baggage, because the API keeps an allowlist of persona ids as a metric dimension.

Two facts outside the simulator shape this change:

- **The seed's dates are relative to the day it was loaded.** Days +3 and +4 are full, and +5 has 2 kg free. The dev database today still holds an older seed, so the full days are today and tomorrow. Every conversation that creates an order also uses capacity on the date it books.
- **Chaos mode applies to the whole API process** (`CHAOS__*`). With `CHAOS__CAPACITY_FAILURE_RATE=1`, every `check_capacity` call fails. Chaos also adds tool latency and raises the price after the first quote. There is no way to turn it on for one conversation, and this change does not add one.

## Goals / Non-Goals

**Goals:**

- Generate the 125 matrix conversations reproducibly enough that each one can be traced back to its cell.
- Keep the persona batch and its legacy goals working as they are, for comparison with `v0`.
- Make a long run safe to interrupt and resume.

**Non-Goals:**

- Measuring or judging the conversations. That is the maintainer's open coding, and evals come in phase 4.
- Repeating cells. One conversation per cell is enough for open coding, and pass^3 belongs to phase 4.
- Attack scenarios. The cheater's legacy goals stay in the persona batch and come back in phase 5.
- Committing the viewer. It is a Claude artifact built from the run file after the run.

## Decisions

### 1. Scenario catalog as data, apart from the personas

New module `scenarios.py` with `Intent` and `Complication` frozen dataclasses (`id`, `text`), the `INTENTS` and `COMPLICATIONS` tuples, and `Cell(persona, intent, complication)` with a `goal` property: `intent.text`, plus `" " + complication.text` unless the complication is `nenhuma`. `personas.py` is unchanged.

Every intent text names a concrete need (flavor, weight, date or neighborhood where it matters), so the persona does not have to invent everything. Some complications rewrite the date or the size instead of adding to them. The intent texts then leave those slots generic ("para a semana que vem") and the complication text overrides them explicitly ("Mas você precisa dele para daqui a 3 dias..."). The persona model handles "but actually" phrasing well. Tests check the anchors of each goal (date, flavor change, size), not its full wording.

Draft texts, Brazilian Portuguese, final wording in the code:

| Id | Text (summary) |
|---|---|
| `retirada` | Bolo de um sabor do cardápio, uns 2 kg, para a semana que vem, retirada na loja |
| `entrega` | Bolo para a semana que vem, com entrega no seu bairro (Boa Viagem) |
| `orcamento` | Só quer saber quanto fica um bolo de 2 kg com entrega; não quer fechar agora |
| `duvida_cardapio` | Pergunta quais sabores existem e o que cada um leva (ingredientes, alergênicos) antes de escolher e encomendar |
| `pos_pedido` | Faz um pedido simples; depois da confirmação, pergunta o status dele e em seguida desiste e pede para cancelar |
| `nenhuma` | (nothing) |
| `data_lotada` | Precisa do bolo para daqui a 3 dias; se não der, aceita outra data próxima |
| `troca_sabor` | Depois de receber o valor, troca o sabor por outro e pergunta quanto fica agora |
| `ferramenta_fora` | Precisa do bolo para um dia específico daqui a 6 dias, e quer confirmação de que a data está garantida |
| `tamanho_ambiguo` | Não fala em quilos: diz "um bolo médio" ou "para umas 40 pessoas" e deixa a atendente decidir o tamanho |

Alternative considered: generate the goals with an LLM from the cell. Rejected, because the goals would drift between runs and the same cell would mean different things in two batches.

`pos_pedido` covers both status and cancellation in one goal, in that order. It stays 5 intents and still covers both tools. Alternative: separate `status` and `cancelamento` intents (6 × 5 × 5 = 150). Rejected to stay within 125 and inside the cost budget.

### 2. Default excludes `ferramenta_fora`; the run is two launches

`plan_matrix(complications: Sequence[str] | None)` returns the interleaved cells: for each (intent, complication) pair, all five personas. `None` means every complication except `ferramenta_fora`. The two launches:

1. API in normal mode, DB reset: `uv run task matrix` → 100 cells, new run id.
2. API restarted with `CHAOS__ENABLED=true CHAOS__CAPACITY_FAILURE_RATE=1`, DB reset: `uv run task matrix --run-id <id> --complications ferramenta_fora` → 25 cells appended to the same file.

Alternative considered: one launch of 125 cells with a 10% outage rate. Rejected, because the outage would land randomly across cells and the `ferramenta_fora` complication would rarely be exercised where it is planned. Alternative: a request header that forces the outage per conversation. Rejected, because it adds a test hook to the API's public surface and changes the API in a phase that must not touch it.

The simulator cannot see whether the API runs in chaos mode, so a mismatch is possible (outage cells against a healthy API). This is a risk, below, and the trace attribute `fornada.chaos.enabled` exposes it.

### 3. Resume by reading the run file

With `--run-id`, `run_matrix` reads the existing file (if any), takes the last line per cell key `(persona_id, intent_id, complication_id)`, and drops from the plan the cells whose last outcome is `completed` or `max_turns`. Lines are only appended, never rewritten. Readers (summary, viewer) dedupe by "last line per cell". This keeps `append_jsonl` as the only writer and an interruption costs at most the conversations in flight.

Alternative considered: a separate state file. Rejected, because the run file already is the state.

### 4. Transcript and span fields

`Transcript` gains `intent_id: str | None = None` and `complication_id: str | None = None`. The defaults keep old files readable and the persona batch writes nulls. `run_conversation` takes an optional cell. `send_message` and `request_attributes` take `intent_id` and `complication_id` and set `fornada.simulator.intent.id` and `fornada.simulator.complication.id` only when present. Baggage stays persona-only: the API's metric allowlist is unchanged, and the cell is a client-span attribute, the same as the run id.

### 5. CLI

`python -m fornada_simulator` keeps running the persona batch. A new `python -m fornada_simulator.matrix` with `argparse`: `--complications` (comma-separated, validated against the catalog before anything starts), `--run-id`, `--limit N` (first N planned cells, used for the 5-cell pilot). New taskipy task `matrix`, run from the repo root like `batch`. The printout adds outcome counts per complication and per intent (`summary.py`: `summarize_by(transcripts, key)` reusing the outcome counting).

### 6. Database state during a run

The DB is reset before each of the two launches (`psql ... schema.sql seed.sql`), so day +3 is full when the run starts. During a run, orders accumulate. Day +3 only gets fuller, which keeps `data_lotada` valid, but other dates also fill up, so a late `nenhuma` cell can hit a date that is full. This is accepted: it is realistic, and the trace's `check_capacity` result shows it during annotation. The order texts spread dates ("semana que vem", "daqui a 6 dias") to soften it.

### 7. A stricter end rule for matrix personas

The 5-cell pilot ended 2 of 5 conversations after one turn: the attendant asked for the date and gpt-5-mini answered with only `[FIM]`. The `v0` batch has the same pattern. Such a conversation never reaches its complication and counts as `completed`, so it would read as an agent success while it is a simulator failure. Matrix conversations get one more rule in the persona's instructions: answer the attendant's pending question, and send `[FIM]` only when the goal is resolved or abandoned. The persona batch keeps the current text, because changing its simulator would move the `v0` baseline.

Alternative considered: a code check that rejects a bare `[FIM]` after a question. Rejected, because telling a question apart needs a judgment, and a prompt rule is enough for a simulator, which is not a security boundary. The pilot is re-run to check the fix.

### Measurement

This change adds no eval or guardrail. What it measures is cost: the 5-cell pilot (`--limit 5`) gives the cost per conversation from Langfuse sessions (the agent's side) before the full run. The full run is projected from it and must stay under about US$ 10, half of the monthly budget. The persona model is not traced, so its cost is estimated from the provider's dashboard.

## Risks / Trade-offs

- **Outage cells run against a healthy API (or the other way around).** → AGENTS.md documents both launches. After the run, a Kibana or Langfuse filter on `fornada.chaos.enabled` per `fornada.simulator.complication.id` checks that only `ferramenta_fora` turns have chaos on.
- **Chaos also raises the price and adds latency in the outage cells.** → Accepted. Those are the conditions the chaos mode was built for, and every injected fault is marked on the span, so annotation can tell them apart.
- **The goal text dictates behavior, which is the simulator's bias.** → Phase 3 also includes 3–4 real people. The matrix is one source among two, and AGENTS.md already says to distrust simulator numbers.
- **Interleaved cells and accumulating orders make a run order-dependent.** → Accepted, since one run is the dataset. The run file and the traces keep exactly what happened.
- **A persona model that ignores the complication** (for example, it never changes the flavor). → Spotted during annotation and recorded as a simulator error, not an agent error. If it is frequent, the goal text is reworded in a follow-up.

## Migration Plan

No migration. Old run files load with null cell fields. Rollback is reverting the simulator commit, and the API is untouched.

## Open Questions

None that change the plan. Final pt-BR wording of the goals is settled in code review.
