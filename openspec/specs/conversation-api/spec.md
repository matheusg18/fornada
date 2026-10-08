# conversation-api Specification

## Purpose

Defines the HTTP contract that clients (chat UI, simulator, evals, red team) use to send customer messages to the attendant and read its replies.

## Requirements

### Requirement: Send a message to a conversation
`POST /conversations/{conversation_id}/messages` SHALL accept a JSON body with a `text` string and return HTTP 200 with a JSON body holding `conversation_id` (the id from the path) and `replies`, a list of one or more objects that each hold a `text` string.

#### Scenario: Customer sends a message
- **WHEN** a client posts `{"text": "Oi, quero um bolo de chocolate"}` to `/conversations/3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11/messages`
- **THEN** the response is HTTP 200, its `conversation_id` is `3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11` and `replies` holds at least one object with a non-empty `text`

### Requirement: Client chooses the conversation id
The conversation id SHALL be a UUID chosen by the client. A message to an id the API has never seen SHALL start that conversation; no prior call to create it SHALL be needed. A path id that is not a UUID SHALL be rejected with HTTP 422.

#### Scenario: First message to a new id
- **WHEN** a client posts a message to a freshly generated UUID
- **THEN** the response is HTTP 200

#### Scenario: Id is not a UUID
- **WHEN** a client posts a message to `/conversations/482/messages`
- **THEN** the response is HTTP 422

### Requirement: Message text is required
The request SHALL be rejected with HTTP 422 when the body is not a JSON object, when `text` is missing or not a string, or when `text` is empty or only whitespace. A rejected request SHALL NOT produce a reply.

#### Scenario: Missing text
- **WHEN** a client posts `{}`
- **THEN** the response is HTTP 422

#### Scenario: Blank text
- **WHEN** a client posts `{"text": "   "}`
- **THEN** the response is HTTP 422

### Requirement: Each turn is logged without the message text
Each accepted message SHALL produce one log record that holds the conversation id and the length of the message text in characters. The message text itself SHALL NOT appear in any log record.

#### Scenario: Turn log record
- **WHEN** a client posts `{"text": "Meu telefone é 81987654321"}` to a conversation
- **THEN** one log record holds that conversation id and a length of 26, and no log record contains `81987654321`

### Requirement: Replies come from the attendant agent
Each accepted message SHALL run one turn of the attendant agent on the conversation whose id is in the path, and the response's `replies` SHALL be that turn's replies, in order. The message text SHALL reach the agent as validated.

#### Scenario: Agent answers
- **WHEN** a client posts `{"text": "Oi, quero um bolo de chocolate"}` and the agent's turn produces the replies "Olá!" and "Qual o tamanho?"
- **THEN** the response is HTTP 200 with `replies` `[{"text": "Olá!"}, {"text": "Qual o tamanho?"}]`

#### Scenario: Conversation continues
- **WHEN** a client posts two messages to the same conversation id
- **THEN** the agent's second turn sees the first message and its replies

### Requirement: A failed turn returns 503
When a turn cannot finish (the LLM provider fails, the database is unreachable, or the agent exceeds its step limit), the endpoint SHALL return HTTP 503 with a generic JSON error. The body SHALL NOT contain the exception text, the database URL, credentials or API keys. The exception SHALL be logged with the conversation id and without the message text.

#### Scenario: Database down
- **WHEN** a message is posted while PostgreSQL is not reachable
- **THEN** the response is HTTP 503, its body does not contain the database password or host, and one error log record holds the conversation id

#### Scenario: LLM provider error
- **WHEN** the chat model call raises an error during a turn
- **THEN** the response is HTTP 503 and its body does not contain the API key

### Requirement: A turn has at least one reply
When a turn ends without any model text, the endpoint SHALL return one reply with a fixed Brazilian Portuguese fallback text, so `replies` is never empty.

#### Scenario: Model returns no text
- **WHEN** the agent's turn ends with a model message whose text is empty
- **THEN** the response holds exactly one reply with the fallback text
