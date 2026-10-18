# Proposal

## Why

Phase 3 (error analysis) generates conversations from a persona × intent × complication matrix, and two of its complications, "tool down" and a price that moves under the agent, cannot happen against today's stable API. Chaos mode is already in the frozen scope; the `add-agent-tools` design deferred it to its own change. It has to land before phase 3 so those conversations exist, and so that the final scenarios "`check_capacity` is down" and "flavor change after the quote" have real failures to observe.

## What Changes

- A chaos switch, off by default, read from the environment (`CHAOS__ENABLED`) for the whole API process, with knobs for each fault and an optional random seed.
- With chaos on, three faults:
  - **Random latency**: every tool call waits a random delay before it runs.
  - **`check_capacity` outage**: about 10% of `check_capacity` calls return the same error result an unexpected failure returns today, without reading the database.
  - **Price change mid-conversation**: after a conversation's first successful `calculate_quote`, its later quotes and orders use the product's price per kg raised by a fixed percentage. Only that conversation is affected and the database is not changed.
- Each injected fault is marked on the tool's span, and the turn span says chaos was on, so error analysis can tell an injected failure from a real one.
- The API logs a warning at startup when chaos is on.
- With chaos off, behavior is unchanged.

Phase: 1 (naive foundation), the last item of its frozen scope, built now as the input to phase 3. It stays within the frozen scope: no new tools, and no defenses. How the agent reacts to these faults is what phases 3 and 4 measure, so this change does not touch the prompt or the graph.

## Capabilities

### New Capabilities
- `chaos-mode`: opt-in fault injection for the attendant's tools (latency, `check_capacity` outage, per-conversation price increase) and how each fault behaves.

### Modified Capabilities
- `app-config`: new `CHAOS__*` settings, with defaults and validation.
- `agent-tracing`: turn and tool spans record whether chaos was on and which fault was injected.

## Impact

- `apps/api`: settings (`core/config.py`), the tools (`agents/attendant/tools.py`: delay, outage, conversation id on `calculate_quote` and `create_order`), the quote service (a price factor), a new chaos module, the turn span (`attendant.py`), tracing attribute names, lifespan wiring and startup log (`main.py`).
- `.env.example`: the `CHAOS__*` block, off.
- `AGENTS.md`: how to turn chaos on for a simulator run.
- No new dependencies, no schema or seed changes, no change to the HTTP API.
