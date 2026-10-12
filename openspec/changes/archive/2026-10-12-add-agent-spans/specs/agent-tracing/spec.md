# Spec Delta

## Purpose

Defines the spans the attendant agent emits for each conversation turn, model call and tool call, so a trace shows what the graph did, what it cost, which prompt version answered and which conversation it belongs to.

## ADDED Requirements

### Requirement: One agent span per turn
With tracing enabled, each conversation turn SHALL produce exactly one span named `invoke_agent fornada-attendant`, of kind INTERNAL, under the SERVER span of the request that carried the customer message. It SHALL carry `gen_ai.operation.name` = `invoke_agent` and `gen_ai.agent.name` = `fornada-attendant`.

#### Scenario: One customer message
- **WHEN** tracing is enabled and a client posts one customer message
- **THEN** the trace has one `invoke_agent fornada-attendant` span of kind INTERNAL, whose parent is the request's SERVER span

#### Scenario: Two messages in one conversation
- **WHEN** a client posts two messages to the same conversation
- **THEN** there are two traces, each with exactly one `invoke_agent` span

### Requirement: One chat span per model call
Each call to the chat model SHALL produce one span named `chat {gen_ai.request.model}`, of kind CLIENT, as a child of the turn's `invoke_agent` span. The HTTP CLIENT span of the provider request SHALL be a child of that `chat` span.

#### Scenario: Turn with one tool round
- **WHEN** the model first requests `search_catalog` and then answers with text
- **THEN** the `invoke_agent` span has two `chat` children, and each provider HTTP CLIENT span sits under one of them

### Requirement: One tool span per tool call
Each tool call the model requests SHALL produce one span named `execute_tool {gen_ai.tool.name}`, of kind INTERNAL, as a child of the turn's `invoke_agent` span. It SHALL carry `gen_ai.operation.name` = `execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id` and `gen_ai.tool.type` = `function`.

#### Scenario: Two tools in one answer
- **WHEN** one model answer requests `check_capacity` and `calculate_quote` together
- **THEN** the `invoke_agent` span has one `execute_tool check_capacity` and one `execute_tool calculate_quote` child, each with the call id from the model's answer

#### Scenario: Tool span carries the call id
- **WHEN** the model requests `search_catalog` with call id `toolu_01`
- **THEN** the `execute_tool search_catalog` span has `gen_ai.tool.call.id` = `toolu_01`

### Requirement: The span tree follows the graph
The children of a turn's `invoke_agent` span, ordered by start time, SHALL match the order of the model calls and tool rounds the graph ran. Tool calls that ran in the same round SHALL start after the `chat` span that requested them ends and before the next `chat` span starts.

#### Scenario: Waterfall of a two-round turn
- **WHEN** the graph runs model → `check_capacity` → model → `calculate_quote` → model
- **THEN** the children of `invoke_agent`, by start time, are `chat`, `execute_tool check_capacity`, `chat`, `execute_tool calculate_quote`, `chat`

### Requirement: Chat spans name the provider and model
Each `chat` span SHALL carry `gen_ai.provider.name` (`anthropic` or `openai`) and `gen_ai.request.model` (the model the agent is configured with), plus `gen_ai.response.model` and `gen_ai.response.id` when the provider returns them. The `invoke_agent` span SHALL NOT carry provider or model attributes; its `chat` children do.

#### Scenario: Anthropic by default
- **WHEN** the agent runs with `LLM__PROVIDER=anthropic` and model `claude-haiku-4-5`
- **THEN** each `chat` span is named `chat claude-haiku-4-5` and carries `gen_ai.provider.name` = `anthropic` and `gen_ai.request.model` = `claude-haiku-4-5`

#### Scenario: OpenAI
- **WHEN** the agent runs with `LLM__PROVIDER=openai` and model `gpt-5-mini`
- **THEN** each `chat` span is named `chat gpt-5-mini` and carries `gen_ai.provider.name` = `openai`

#### Scenario: No model on the turn span
- **WHEN** a turn ends
- **THEN** its `invoke_agent` span has no `gen_ai.provider.name` and no `gen_ai.request.model`

### Requirement: Chat spans carry token usage
A `chat` span SHALL carry `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` as integers when the model's answer reports usage, and `gen_ai.response.finish_reasons` when it reports a finish reason. Missing values SHALL be left out, never set to zero. Token counts SHALL appear only on `chat` spans, so no span repeats another span's tokens.

#### Scenario: Usage reported
- **WHEN** the model's answer reports 1200 input tokens and 85 output tokens
- **THEN** the `chat` span has `gen_ai.usage.input_tokens` = 1200 and `gen_ai.usage.output_tokens` = 85

#### Scenario: Usage missing
- **WHEN** the model's answer reports no usage
- **THEN** the `chat` span has no `gen_ai.usage.*` attribute

#### Scenario: No tokens on the turn span
- **WHEN** a turn makes three model calls
- **THEN** the `invoke_agent` span has no `gen_ai.usage.*` attribute

### Requirement: Spans record the prompt version
Each `chat` span SHALL carry `fornada.prompt.version` with the version of the system prompt sent in that call. The `invoke_agent` span SHALL carry the prompt version of the turn's output.

#### Scenario: Prompt version on a model call
- **WHEN** the prompt version is `sha256:0123456789ab` and the agent calls the model
- **THEN** the `chat` span has `fornada.prompt.version` = `sha256:0123456789ab`, and so does the `invoke_agent` span

### Requirement: Spans carry the conversation as a session
Every `invoke_agent`, `chat` and `execute_tool` span SHALL carry the conversation id as `gen_ai.conversation.id` and as `session.id`. All turns of one conversation SHALL therefore be grouped in one Langfuse session.

#### Scenario: Session attributes on every agent span
- **WHEN** a turn runs in conversation `3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11`
- **THEN** its `invoke_agent`, `chat` and `execute_tool` spans all have `gen_ai.conversation.id` and `session.id` equal to that id

#### Scenario: Conversation grouped in Langfuse
- **WHEN** tracing is enabled, the Collector exports to Langfuse and a client posts three messages to one conversation
- **THEN** Langfuse shows one session with that conversation id, holding the three traces

### Requirement: Spans carry no conversation content
Agent spans SHALL NOT carry message text, the system prompt, tool arguments, tool results or tool definitions.

#### Scenario: Customer text stays out of spans
- **WHEN** a customer sends a message with a phone number and the model calls `get_order` with it
- **THEN** no attribute of any agent span contains the message text or the phone number

### Requirement: Failed operations mark their span as an error
When a model call raises, its `chat` span SHALL have status ERROR, `error.type` set to the exception's class name, and the exception recorded. When a turn raises, its `invoke_agent` span SHALL be marked the same way. A tool call whose result has error status SHALL mark its `execute_tool` span ERROR with an `error.type`. A failed tool call alone SHALL NOT mark the `invoke_agent` span ERROR.

#### Scenario: Provider error
- **WHEN** the model call raises an `APIConnectionError`
- **THEN** the `chat` span and the `invoke_agent` span have status ERROR and `error.type` = `APIConnectionError`

#### Scenario: Tool returns an error result
- **WHEN** the model calls `calculate_quote` with 2.3 kg and the tool returns an error result
- **THEN** the `execute_tool calculate_quote` span has status ERROR and an `error.type`, and the `invoke_agent` span does not have status ERROR

### Requirement: A full day is not an error
A `check_capacity` call that returns a capacity report SHALL leave its span status UNSET, even when the date has no free capacity. The span SHALL carry `fornada.capacity.free_kg` (a double) with the free capacity from the report.

#### Scenario: Day with no free capacity
- **WHEN** the model calls `check_capacity` for a date whose orders fill the oven
- **THEN** the `execute_tool check_capacity` span has status UNSET and `fornada.capacity.free_kg` = 0.0

#### Scenario: Day with room
- **WHEN** the model calls `check_capacity` for a date with 6.5 kg free
- **THEN** the span has status UNSET and `fornada.capacity.free_kg` = 6.5

### Requirement: Agent tracing does not change the turn
Turn replies, stored messages and tool side effects SHALL be the same with tracing enabled or disabled. With tracing disabled, the agent SHALL export no spans.

#### Scenario: Same replies with and without tracing
- **WHEN** the same scripted conversation runs once with tracing enabled and once with it disabled
- **THEN** both runs return the same replies and store the same messages

#### Scenario: Tracing disabled
- **WHEN** tracing is disabled and a client posts a message
- **THEN** no `invoke_agent`, `chat` or `execute_tool` span is exported
