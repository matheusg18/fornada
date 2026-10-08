# Spec Delta

## Purpose

Defines how the attendant agent runs one conversation turn: the model–tools loop over the nine tools, what a turn takes in and gives back, conversation memory, and which chat model it uses.

## ADDED Requirements

### Requirement: A turn loops between the model and the tools
Each turn SHALL call the chat model with the system prompt, the conversation history and the nine tools. When the model's answer requests tool calls, the agent SHALL run those tools, add their results to the conversation and call the model again. When the model's answer requests no tool call, the turn SHALL end.

#### Scenario: Answer without tools
- **WHEN** the model answers "Olá! Como posso ajudar?" with no tool call
- **THEN** the turn ends after one model call and runs no tool

#### Scenario: One tool round
- **WHEN** the model first requests `search_catalog` and then, after reading its result, answers with text and no tool call
- **THEN** `search_catalog` runs once, the model is called twice and the turn ends

#### Scenario: Several tool calls in one answer
- **WHEN** one model answer requests `check_capacity` and `calculate_quote` together
- **THEN** both tools run before the model is called again, and each result is matched to its call

### Requirement: Tool errors go back to the model
A tool call that fails SHALL add an error result for that call to the conversation and SHALL NOT end the turn; the model SHALL be called again with the error result.

#### Scenario: Invalid weight
- **WHEN** the model calls `calculate_quote` with 2.3 kg
- **THEN** the model's next call sees an error result for that call, and the turn continues

### Requirement: A turn takes only the new customer message
A turn's input SHALL be the new customer message. The earlier history SHALL come from the conversation's memory, never from the caller.

#### Scenario: Second message
- **WHEN** a caller sends the second message of a conversation
- **THEN** the caller sends only that message, and the model sees both customer messages and the first turn's answers

### Requirement: A turn returns the conversation messages and the prompt version
A turn's output SHALL hold the conversation's messages and the system prompt version used in the turn. It SHALL NOT expose other internal state.

#### Scenario: Output of a turn
- **WHEN** a turn ends
- **THEN** its output holds the messages, including those added in the turn, and the prompt version, and nothing else

### Requirement: Replies are the turn's model texts
The replies of a turn SHALL be the non-empty texts of the model messages added in that turn, in order. Text the model writes next to a tool call SHALL be a reply too. Tool results and earlier turns SHALL NOT be replies.

#### Scenario: Text before a tool call
- **WHEN** in one turn the model writes "Vou verificar a agenda" with a `check_capacity` call, and then "Temos 5 kg livres no dia 20"
- **THEN** the turn's replies are those two texts, in that order

#### Scenario: Only the current turn
- **WHEN** the third turn of a conversation ends with one model text
- **THEN** the replies hold only that text

### Requirement: Memory per conversation id
The agent SHALL keep each conversation's messages in PostgreSQL, keyed by the conversation id. A turn on a conversation id SHALL see every earlier message of that id and none of any other id. Memory SHALL survive an API restart.

#### Scenario: Two conversations
- **WHEN** conversation A says "Meu nome é Ana" and then conversation B asks "Qual é o meu nome?"
- **THEN** the model call in B contains no message from A

#### Scenario: Restart
- **WHEN** the API restarts between two turns of the same conversation
- **THEN** the second turn sees the first turn's messages

### Requirement: The system prompt is not stored in the conversation
The system prompt SHALL be sent with every model call and SHALL NOT be saved among the conversation's messages, so a new prompt version applies from the next model call on.

#### Scenario: Prompt changes between turns
- **WHEN** the prompt file changes and the API reloads between two turns of a conversation
- **THEN** the second turn's model call carries only the new prompt text, and the stored messages contain no system prompt

### Requirement: The chat model follows the LLM settings
The agent SHALL use the provider selected by `LLM__PROVIDER`, with that provider's model name and API key from the settings.

#### Scenario: Anthropic by default
- **WHEN** `LLM__PROVIDER` is not set and `LLM__ANTHROPIC__MODEL` is not set
- **THEN** the agent calls the Anthropic model `claude-haiku-4-5`

#### Scenario: OpenAI
- **WHEN** `LLM__PROVIDER=openai` and `LLM__OPENAI__MODEL=gpt-5-mini`
- **THEN** the agent calls the OpenAI model `gpt-5-mini`

### Requirement: The tool call knows its conversation
Each tool call SHALL run with the conversation id available as the run's thread id, so tools that record the conversation (such as `escalate_to_human`) use the real id and not a value from the model.

#### Scenario: Escalation records the conversation
- **WHEN** the model calls `escalate_to_human` in conversation `3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11`
- **THEN** the escalation is recorded with that conversation id
