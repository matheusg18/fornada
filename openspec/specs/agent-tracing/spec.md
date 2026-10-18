# agent-tracing Specification

## Purpose

Defines the spans the attendant agent emits for each conversation turn, model call and tool call, so a trace shows what the graph did, what it cost, which prompt version answered and which conversation it belongs to.

## Requirements

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
With content capture off, agent spans SHALL NOT carry message text, the system prompt, tool arguments, tool results, tool definitions or a customer phone number. With capture on, they SHALL carry only the content attributes defined in this spec. Tool definitions SHALL NOT be on spans in either mode.

#### Scenario: Customer text stays out of spans
- **WHEN** content capture is off, a customer sends a message with a phone number and the model calls `get_order` with it
- **THEN** no attribute of any agent span contains the message text or the phone number

#### Scenario: No tool definitions with capture on
- **WHEN** content capture is on and a turn calls the model
- **THEN** no agent span carries the tool definitions sent to the model

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

### Requirement: Chat spans carry the model's input and output when capture is on
With content capture on, each `chat` span SHALL carry, as JSON strings in the GenAI semantic convention format, `gen_ai.system_instructions` with the system prompt sent, `gen_ai.input.messages` with the conversation messages sent, including tool calls and tool results, and `gen_ai.output.messages` with the model's answer, including any tool calls it requests.

#### Scenario: Model answers with text
- **WHEN** capture is on, the customer writes "Quero um bolo de chocolate" and the model answers with text
- **THEN** the `chat` span's `gen_ai.input.messages` contains a user message with that text, `gen_ai.system_instructions` contains the system prompt, and `gen_ai.output.messages` contains one assistant message with the answer text

#### Scenario: Model requests a tool
- **WHEN** capture is on and the model answers with a `search_catalog` call with id `toolu_01`
- **THEN** the `chat` span's `gen_ai.output.messages` contains a tool call part with name `search_catalog`, id `toolu_01` and its arguments

#### Scenario: Provider error
- **WHEN** capture is on and the model call raises
- **THEN** the `chat` span carries `gen_ai.input.messages` and `gen_ai.system_instructions`, and no `gen_ai.output.messages`

### Requirement: Turn spans carry the turn's input and output when capture is on
With content capture on, each `invoke_agent` span SHALL carry `gen_ai.input.messages` with the customer message of the turn, and `gen_ai.output.messages` with the replies the agent returned for it. A turn that raises SHALL carry the input only.

#### Scenario: One message, two replies
- **WHEN** capture is on, the customer writes "Oi" and the turn returns two replies
- **THEN** the `invoke_agent` span's `gen_ai.input.messages` holds one user message "Oi", and its `gen_ai.output.messages` holds the two replies in order

### Requirement: Tool spans carry arguments and result when capture is on
With content capture on, each `execute_tool` span SHALL carry `gen_ai.tool.call.arguments` with the arguments the model passed, as a JSON string, and `gen_ai.tool.call.result` with the result returned to the model, including error results.

#### Scenario: Successful call
- **WHEN** capture is on and the model calls `check_capacity` with `{"date": "2026-10-20"}`
- **THEN** the `execute_tool check_capacity` span has `gen_ai.tool.call.arguments` equal to that JSON and `gen_ai.tool.call.result` equal to the content the model received

#### Scenario: Error result
- **WHEN** capture is on and `calculate_quote` returns an error result
- **THEN** the span carries that error result in `gen_ai.tool.call.result`

### Requirement: Tool spans name the customer phone when capture is on
With content capture on, the `execute_tool` span of a tool called with a phone argument SHALL carry `fornada.customer.phone` with that phone normalized to E.164. A phone that does not normalize SHALL leave the attribute out. Tools without a phone argument SHALL NOT carry it.

#### Scenario: Phone with area code
- **WHEN** capture is on and the model calls `get_order` with phone `(81) 99999-1234`
- **THEN** the `execute_tool get_order` span has `fornada.customer.phone` = `+5581999991234`

#### Scenario: Invalid phone
- **WHEN** capture is on and the model calls `send_message` with phone `abc`
- **THEN** the span has no `fornada.customer.phone`

#### Scenario: Tool without phone
- **WHEN** capture is on and the model calls `search_catalog`
- **THEN** the span has no `fornada.customer.phone`

#### Scenario: Capture off
- **WHEN** capture is off and the model calls `get_order` with a valid phone
- **THEN** the span has no `fornada.customer.phone`

### Requirement: Content capture does not change the turn
Turn replies, stored messages and tool side effects SHALL be the same with content capture on or off.

#### Scenario: Same replies with and without capture
- **WHEN** the same scripted conversation runs once with capture on and once with it off
- **THEN** both runs return the same replies and store the same messages

### Requirement: Turn spans say whether chaos was on
With chaos mode on, each `invoke_agent` span SHALL carry `fornada.chaos.enabled` = `true` from its start. With chaos mode off, the attribute SHALL be absent.

#### Scenario: Chaos on
- **WHEN** chaos mode is on and a client posts a customer message
- **THEN** the turn's `invoke_agent` span has `fornada.chaos.enabled` = `true`

#### Scenario: Chaos off
- **WHEN** chaos mode is off
- **THEN** no span carries any `fornada.chaos.*` attribute

### Requirement: Tool spans record the injected delay
With chaos mode on, each `execute_tool` span SHALL carry `fornada.chaos.delay_ms` with the delay injected into that call, as an integer, including `0`.

#### Scenario: Delayed call
- **WHEN** chaos mode is on and `search_catalog` is delayed 750 ms
- **THEN** the `execute_tool search_catalog` span has `fornada.chaos.delay_ms` = `750` and lasts at least 750 ms

### Requirement: Tool spans name the injected fault
With chaos mode on, an `execute_tool` span SHALL carry `fornada.chaos.fault` when a fault changed that call's outcome: `capacity_unavailable` for an injected `check_capacity` failure, and `price_increase` for a `calculate_quote` or `create_order` priced with the raised price. A call with no such fault SHALL NOT carry it. An injected failure SHALL also mark the span as an error, like any failed tool call.

#### Scenario: Injected outage
- **WHEN** chaos mode injects a `check_capacity` failure
- **THEN** the `execute_tool check_capacity` span has `fornada.chaos.fault` = `capacity_unavailable`, status ERROR and `error.type` = `tool_error`

#### Scenario: Raised price
- **WHEN** a conversation's second `calculate_quote` uses the raised price
- **THEN** its `execute_tool calculate_quote` span has `fornada.chaos.fault` = `price_increase`, and the first quote's span has no `fornada.chaos.fault`

#### Scenario: Latency alone is not a fault
- **WHEN** chaos mode is on and `search_catalog` is only delayed
- **THEN** its span has `fornada.chaos.delay_ms` and no `fornada.chaos.fault`
