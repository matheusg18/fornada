# Spec Delta

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Fixed reply until the agent is wired
**Reason**: The attendant agent now answers every message; the fixed reply was a placeholder until the graph existed.
**Migration**: Replies come from the agent (see "Replies come from the attendant agent"). Tests that need a deterministic reply override the attendant dependency with a fake.
