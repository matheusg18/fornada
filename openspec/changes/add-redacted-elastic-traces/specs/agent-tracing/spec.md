# Spec Delta

## MODIFIED Requirements

### Requirement: Spans carry no conversation content
With content capture off, agent spans SHALL NOT carry message text, the system prompt, tool arguments, tool results, tool definitions or a customer phone number. With capture on, they SHALL carry only the content attributes defined in this spec. Tool definitions SHALL NOT be on spans in either mode.

#### Scenario: Customer text stays out of spans
- **WHEN** content capture is off, a customer sends a message with a phone number and the model calls `get_order` with it
- **THEN** no attribute of any agent span contains the message text or the phone number

#### Scenario: No tool definitions with capture on
- **WHEN** content capture is on and a turn calls the model
- **THEN** no agent span carries the tool definitions sent to the model

## ADDED Requirements

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
