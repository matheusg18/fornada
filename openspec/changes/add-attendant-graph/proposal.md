# Proposal

## Why

The nine tools and the conversation endpoint exist, but the endpoint still answers with a fixed text: there is no agent. Phase 1 is done only when 20 simulated conversations finish and `v0` is tagged, and that needs a real LangGraph agent behind `POST /conversations/{id}/messages`. Every later phase also needs to know which system prompt produced each answer, so error analysis (phase 3) can say "version X of the prompt failed, not version Y" and evals (phase 4) can compare versions.

**Phase:** 1 (naive foundation). The graph is the plain ReAct loop with no defenses: every tool enabled, a one-screen prompt, no guardrail nodes, no input classifier and no limit on conversation length. The only limit is a per-turn step cap (recursion limit) that protects the token budget from a runaway tool loop; it does not restrict what the agent may do. Phases 5 and 6 measure and add those.

**Scope:** stays within the frozen scope. The graph uses exactly the nine existing tools and adds no tool or feature. Conversation memory (the LangGraph checkpointer in PostgreSQL) is already part of the planned stack.

## What Changes

- **Graph.** A LangGraph `StateGraph` with the standard ReAct shape:
  - `call_model` node: sends the system prompt plus the conversation's messages to the chat model bound to the nine tools.
  - `tools` node: runs the tool calls of the last model message.
  - A conditional edge after `call_model`: to `tools` when the model asked for tool calls, otherwise to the end of the turn. It is routing logic, not a node.
- **Code layout**, one concern per file in `agents/attendant/`: `state.py` (state schemas), `nodes.py` (the model node; the tool node and the router are LangGraph's prebuilt `ToolNode` and `tools_condition`), `prompt.py` (prompt loading and versioning), `prompts/system.md` (the prompt text), `model.py` (chat model from settings) and `graph.py` (builds and compiles the graph).
- **Three state schemas:** an input schema (what a turn receives), the internal graph state (what nodes read and write) and an output schema (what a turn returns).
- **Versioned system prompt.** The prompt lives in a Markdown file. Loading it yields the text and a version derived from a hash of the content. The version is written to the graph state and to every model message the prompt produced, so each answer in a conversation's history says which prompt generated it.
- **Conversation memory.** A PostgreSQL checkpointer (`langgraph-checkpoint-postgres`) keyed by the conversation id as LangGraph `thread_id`, so a conversation continues across turns and API restarts.
- **Chat model from settings.** The model follows `LLM__PROVIDER` and the provider's model name and key (`anthropic` or `openai`).
- **Endpoint wired to the graph.** A graph-backed attendant replaces `FixedAttendant` behind the existing `Attendant` seam. The HTTP request and response shapes do not change. **BREAKING (behavior):** replies come from the LLM instead of a fixed text, a turn needs the database and the LLM provider, and a turn that fails returns HTTP 503.
- **Removed:** `FixedAttendant` and its fixed reply.

## Capabilities

### New Capabilities
- `attendant-agent`: how the attendant runs a turn: the ReAct loop over the nine tools, the input/state/output schemas, conversation memory per conversation id, the active chat model, and which replies a turn returns.
- `prompt-versioning`: how the system prompt is stored, loaded and identified by a content-derived version, and where that version is recorded.

### Modified Capabilities
- `conversation-api`: the "Fixed reply until the agent is wired" requirement is replaced by replies from the attendant agent; a failed turn returns HTTP 503 without internal details.
- `database-access`: "Models never change the schema" is clarified to cover app tables only; the LangGraph checkpointer creates and migrates its own tables in the same database.

## Impact

- **Code:** new modules in `apps/api/src/fornada_api/agents/attendant/` (`state.py`, `nodes.py`, `prompt.py`, `model.py`, `graph.py`, `prompts/system.md`); `attendant.py` gets the graph-backed attendant and loses `FixedAttendant`; a checkpointer module in `infrastructure/`; `dependencies/attendant.py` and `main.py` (lifespan) change; `conversations.py` maps turn failures to 503.
- **Dependencies:** `langchain-anthropic`, `langchain-openai`, `langgraph-checkpoint-postgres` (with `psycopg-pool`), installed with `uv add --package fornada-api`.
- **Database:** the checkpointer's tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) are created in the `fornada` database by the library's own setup. `schema.sql` already leaves them alone.
- **Cost:** every turn now calls the LLM (Haiku-class by default), at least once per turn and once more per tool round. No cost cap in v0.
- **Tests:** unit tests for the prompt loader, routing, nodes and graph with a scripted fake chat model (no network); integration tests with the real checkpointer; existing conversation tests switch to a fake attendant.
- **Clients:** Chainlit and the simulator keep the same contract and start talking to a real agent. Phase 2 turns the prompt version into a span attribute; phase 6 adds guardrail nodes to this graph.
