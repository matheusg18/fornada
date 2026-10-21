# Proposal

## Why

Phase 3 (error analysis) needs 100–150 conversations that cover a persona × intent × complication matrix, so the first error in each trace can be coded and counted per cell. Today the simulator has only five personas with four fixed goals each (20 conversations), and complications such as a full date or a flavor change appear only inside a few goals and cannot be combined. Without the matrix, the failure taxonomy would only reflect the scenarios the goals happened to cover.

## What Changes

- A catalog of **five intents**: order with pickup, order with delivery, quote only, catalog or allergen question followed by an order, and placing an order and then asking about its status or cancelling it in the same conversation.
- A catalog of **five complications**: none (the control), full date, flavor change after the quote, tool down (`check_capacity` unavailable) and size ambiguity.
- A **matrix batch**: every persona × intent × complication cell is planned once (125 conversations). The customer's goal is built from the cell's intent and complication. The persona's description, which sets tone and writing style, is unchanged. The cheater plays its style only; its attack goals stay out of the matrix and belong to phase 5.
- The batch can be **filtered** to a subset of complications and can **resume** a partial run without replaying cells that already finished. That is how the 25 tool-down cells run apart from the rest, against an API started with chaos mode and a capacity failure rate of 1.
- Matrix transcripts record the cell's `intent_id` and `complication_id`, and matrix client spans carry them as attributes, so an annotated trace maps back to its cell.
- The existing persona batch (20 conversations with the legacy goals) stays unchanged, so it remains comparable with `v0`.
- After the full run, a private Claude artifact shows the conversations. It follows the `v0` viewer (conversation index, chat, persona and outcome filters) and adds intent and complication filters and a clickable matrix grid. The artifact lives outside the repo and is not specified here.

Phase: 3 (error analysis), its first item. It stays within the frozen scope: only the simulator changes. The API, the agent, its prompt and its tools are untouched, and chaos mode is used as it already exists.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `persona-simulator`: adds the intent and complication catalogs, the matrix batch with filter and resume, and the cell fields in the transcript. The persona batch and its requirements stay unchanged.
- `client-tracing`: matrix client spans also carry the intent and the complication. The rule that these simulator attributes stay at the client applies to them too.

## Impact

- `apps/simulator`: new scenario catalog module (intents, complications, goal composition), transcript model (two optional fields), planner and batch (matrix mode, filter, resume), client span attributes, CLI entry point and taskipy task, the notebook's summary (per intent and complication), tests and README.
- `AGENTS.md`: how to run the matrix, including the database reset before each run and the chaos settings for the tool-down cells.
- No API, database schema or seed changes, and no new dependencies.
- Cost: about 125 conversations with Haiku-class models on both sides. A 5-conversation pilot measures the cost per conversation before the full run.
