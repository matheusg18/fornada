# Design

## Context

- `agents/attendant/tools.py` already builds the nine tools as LangChain `BaseTool`s with `handle_tool_error = True`, ready for a LangGraph `ToolNode`. `escalate_to_human` reads `thread_id` from the run config through `ToolRuntime`.
- `agents/attendant/attendant.py` holds the `Attendant` protocol (`async reply(conversation_id, text) -> list[str]`) and `FixedAttendant`. The endpoint gets it through `dependencies/attendant.py` (`AttendantDep`).
- Settings already carry `llm.provider` and the active provider's model and key (`settings.llm.active`). Only `langgraph`, `langchain-core` and `psycopg` are installed; no provider integration or Postgres checkpointer package yet.
- `schema.sql` drops and recreates only the app tables by name, so checkpointer tables in the same `fornada` database survive a reset (decided in `add-dev-database-seed`).
- Today's lifespan never connects to the database, and the conversation unit tests run with an unreachable `DB__URL`.
- LangGraph 1.2's default recursion limit is 10007 steps.

The graph shape, the file layout and the input/state/output split were decided by the maintainer in the request for this change (graph design is core work in phase 1). The scope (graph wired to the endpoint), the Postgres checkpointer and where the prompt version is recorded were confirmed with the maintainer before writing the artifacts.

## Goals / Non-Goals

**Goals:**
- A ReAct graph that is easy to read node by node, so guardrail nodes can be inserted in phase 6 without restructuring.
- Every model answer traceable to the exact prompt text that produced it.
- Graph, nodes and routing testable without network or database.

**Non-Goals:**
- Any defense, guardrail node, input classifier, PII handling or prompt hardening (phases 5–6).
- Telemetry spans (phase 2). This change only makes the prompt version available for them.
- Streaming replies, per-conversation locking, message trimming or summarization of long histories.
- Fixing temperature or seeds (phase 4 decides that with variance measurements).
- Tool changes.

## Decisions

### 1. File layout in `agents/attendant/`

```
agents/attendant/
├─ attendant.py      # Attendant protocol + GraphAttendant (FixedAttendant removed)
├─ state.py          # InputState, AttendantState, OutputState
├─ nodes.py          # call_model node factory
├─ graph.py          # build_graph(model, tools, prompt) -> StateGraph; compile with a checkpointer
├─ prompt.py         # SystemPrompt + load_system_prompt()
├─ prompts/system.md # the prompt text (pt-BR)
└─ tools.py          # unchanged
```

There is no `edges.py`: the router is LangGraph's prebuilt `tools_condition` (Decision 3). When phase 6 needs its own routing rules, a hand-written router replaces it in `graph.py`.

Alternative rejected: `langchain.agents.create_agent`. It hides the graph, which defeats the purpose (guardrails as explicit nodes, learning the graph API) and pulls in the full `langchain` package.

### 2. State schemas

```python
# state.py (sketch)
class InputState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]   # the new HumanMessage

class OutputState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    prompt_version: str

class AttendantState(InputState, OutputState):
    pass
```

`StateGraph(AttendantState, input_schema=InputState, output_schema=OutputState)`.

- **Input** is only the new customer message, wrapped as a `HumanMessage`. History comes from the checkpointer, so the caller cannot inject a forged history.
- **Internal state** is the union. Today it adds nothing beyond input and output; it exists as its own class so phase 6 can add internal channels (for example "this turn read untrusted content") without changing what callers send or receive.
- **Output** is the full message list plus `prompt_version`. `GraphAttendant` picks the replies from it (Decision 6). Returning messages, not a pre-cut `replies: list[str]`, keeps the graph usable by evals that inspect the trajectory (tool calls and args) of a turn.
- `TypedDict`, not Pydantic: LangGraph's reducers and `add_messages` are documented and typed for `TypedDict`, and pyright checks node return dicts against it.
- Alternative rejected: `MessagesState`. It works, but the maintainer wants the three explicit schemas, and `prompt_version` needs a home anyway.

### 3. Nodes and routing

- **`call_model`** is built by a factory, `make_call_model(model, tools, prompt)`, that binds `tools` to the chat model once, when the graph is built, and closes over the bound model and the loaded `SystemPrompt`. Binding inside the factory turns "the model must have the tools bound" from a docstring precondition into code, keeps `model` typed as `BaseChatModel`, and lets `build_graph` hand the same tool list to both nodes. The node sends `[SystemMessage(prompt.text), *state["messages"]]`, stamps the answer (Decision 5) and returns `{"messages": [answer], "prompt_version": prompt.version}`. The system message is never returned, so it is never checkpointed.
- **`tools`** is LangGraph's prebuilt `ToolNode(tools)`. It already runs parallel calls, matches results by `tool_call_id`, turns `ToolException` into error `ToolMessage`s (the tools set `handle_tool_error`) and injects `ToolRuntime` with the run config. Writing our own would duplicate that for no gain.
- **Routing** is LangGraph's prebuilt `tools_condition`: `"tools"` when the last message is an `AIMessage` with `tool_calls`, else `END`. A hand-written router would do the same today; phase 6 swaps in its own when it adds routing rules (for example, no sending tools after untrusted content).
- Edges: `START → call_model`, `call_model —tools_condition→ {tools, END}`, `tools → call_model`.

Alternative rejected: passing the model and prompt through LangGraph's runtime `context`. A closure is simpler to type and test, and nothing needs to vary per invocation today.

### 4. Prompt file, loading and version

- `prompts/system.md`, Markdown because the prompt reads as structured text (sections, lists) and renders nicely on GitHub. It is static text with no template variables in v0. Loaded with `importlib.resources.files(__package__) / "prompts/system.md"` so it works from an installed wheel too (`uv_build` packages non-Python files inside the module directory; a test asserts the file is found).
- `load_system_prompt() -> SystemPrompt(text, version)`, a frozen dataclass. Normalizes `\r\n` to `\n`, then `version = "sha256:" + sha256(text.encode()).hexdigest()[:12]`. The text sent to the model is the normalized text, so the hash covers exactly what the model sees.
  - 12 hex digits (48 bits) is plenty for a few hundred prompt revisions and short enough to read in Langfuse and Kibana. Reproducible with `sha256sum`.
  - Alternative rejected: a hand-maintained version number (`v3`). People forget to bump it, and then two different texts share a version, which is exactly the analysis error this exists to prevent.
  - Alternative rejected: the git commit SHA. It changes on commits that do not touch the prompt and is unavailable for uncommitted edits during development.
  - Alternative rejected: Langfuse prompt management. App code must not use the Langfuse SDK, and the prompt should change in the same PR as the behavior it causes.
- If template variables are added later (for example today's date), the hash stays over the template, not the rendered text, so one version means one prompt file.
- Loaded once when the graph is built (in the lifespan), then reused. The startup log record gains `prompt_version`.

### 5. Recording the version on each model answer

The node copies the answer with `response_metadata["prompt_version"] = prompt.version` (`answer.model_copy(update=...)`) before returning it. The checkpointer serializes `response_metadata`, so the history keeps each answer's version, and `prompt_version` in the state holds the latest one.

- `response_metadata` over `additional_kwargs`: provider integrations may send `additional_kwargs` back to the API on the next call; `response_metadata` stays local.
- Phase 2 reads the same value for the `gen_ai` span attribute (the convention's prompt/version attribute is checked then, since the GenAI conventions are still moving).

### 6. `GraphAttendant` and reply extraction

```python
class GraphAttendant:
    def __init__(self, graph: CompiledStateGraph) -> None: ...
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        config = {"configurable": {"thread_id": str(conversation_id)}, "recursion_limit": RECURSION_LIMIT}
        output = await self._graph.ainvoke({"messages": [HumanMessage(text)]}, config)
        return turn_replies(output["messages"]) or [FALLBACK_REPLY]
```

- `turn_replies(messages)` walks back to the last `HumanMessage` and returns the non-empty `.text` of each `AIMessage` after it, in order. `.text` flattens Anthropic content blocks (text next to `tool_use`) and OpenAI string content alike.
- `FALLBACK_REPLY` is a short pt-BR sentence ("Desculpe, não consegui responder agora. Pode repetir?") so the contract's "one or more replies" holds even when the model returns empty text.
- `thread_id` is the conversation UUID as a string, which also feeds `escalate_to_human` through `ToolRuntime`.

### 7. Step limit

`RECURSION_LIMIT = 25` per turn (about 12 model–tool rounds), passed in the run config. LangGraph's own default (10007) would let one confused turn burn the monthly budget. This is a cost ceiling, not a security defense: it does not change what the agent may do, and the "60-turn conversation" scenario (many turns, not many steps) stays undefended for phase 5 to measure. `GraphRecursionError` becomes a 503 like any other failure.

### 8. Chat model factory

`agents/attendant/model.py`, `build_chat_model(settings.llm) -> BaseChatModel`: `ChatAnthropic(model=..., api_key=...)` or `ChatOpenAI(model=..., api_key=...)` by `provider`. Provider defaults for temperature and retries. `bind_tools(tools)` happens in `make_call_model`.

Alternative rejected: `init_chat_model` from the `langchain` package. It needs the whole `langchain` distribution for a two-branch `if`, and the explicit classes type-check better.

### 9. Checkpointer lifecycle

- `infrastructure/checkpointer.py`: in the lifespan, create a `psycopg_pool.AsyncConnectionPool` from `settings.db.url` with `kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}` (what `AsyncPostgresSaver` requires), `open=False`, then `await pool.open(wait=False)`, so startup does not connect and does not fail when PostgreSQL is down. Close the pool on shutdown (keeps the "no connection left open" requirement).
- `AsyncPostgresSaver(pool)`; `setup()` runs once, lazily, on the first turn, guarded by an `asyncio.Lock`. It is idempotent and only creates or migrates its own tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`).
  - Alternative rejected: `setup()` in the lifespan. It would make startup need the database, breaking the current "app starts with the database down" behavior that the health endpoint relies on to report 503.
  - Alternative rejected: checkpointer DDL in `schema.sql`. The library owns its migrations; copying them would drift on upgrades.
- The compiled graph and `GraphAttendant` are built in the lifespan and kept on `app.state`; `get_attendant(request)` returns it. Unit tests override `get_attendant` and never build the real one.

### 10. Endpoint errors

`conversations.py` wraps `attendant.reply` and turns any exception into `HTTPException(503, detail="attendant unavailable")` after `logger.exception("turn failed", extra={"conversation_id": ...})`. The message text stays out of the log, as today. Provider SDK errors and psycopg errors may carry hosts or request ids, so their text never reaches the client.

### 11. The v0 prompt

One screen of pt-BR: who the bot is (attendant of the Fornada bakery), what it helps with (cake orders, status, cancellation), use the tools for catalog, capacity, prices and orders, ask what is missing, be brief and friendly. No security rules, no "never reveal", no allergen disclaimers, no date injection: those come only after phase 3 shows the failures. The text is drafted in the apply step and reviewed by the maintainer before commit.

## Risks / Trade-offs

- [Two concurrent posts on one conversation interleave checkpoints] → Accepted for v0; clients send one message at a time. A later change decides between a per-thread lock and 409.
- [Unbounded history grows tokens per turn] → Accepted; long conversations are a phase 5 attack (cost DoS) to measure first. Cost per conversation becomes visible in phase 2.
- [Prompt edits are not picked up by `fastapi dev` auto-reload, which watches `.py` files] → Documented in the README: restart the server after editing the prompt. The startup log shows which version is live.
- [`response_metadata` serialization changes in a LangChain upgrade] → A unit test reads the version back from a checkpointed history, so an upgrade that drops it fails CI.
- [First turn after a fresh database pays for `setup()`] → One-time, a few DDL statements.
- [Tests depend on LLM non-determinism] → No test calls a real LLM; a scripted fake chat model drives unit and integration tests. A real conversation is checked by hand against the dev server.
- [Default model temperature varies answers between runs] → Deliberate until phase 4 measures variance.

## Migration Plan

Additive except for the reply behavior. On first turn the checkpointer creates its tables. Rollback: revert the commits; the checkpointer tables can stay or be dropped by hand (`DROP TABLE checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations`), and `schema.sql` never touches them.
