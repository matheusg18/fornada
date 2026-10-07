# Spec Delta

## Purpose

Defines the HTTP contract that clients (chat UI, simulator, evals, red team) use to send customer messages to the attendant and read its replies.

## ADDED Requirements

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

### Requirement: Fixed reply until the agent is wired
Until the attendant agent answers, every accepted message SHALL get exactly one reply with the same fixed Brazilian Portuguese text, whatever the message or conversation. No LLM SHALL be called and nothing about the conversation SHALL be stored.

#### Scenario: Same reply everywhere
- **WHEN** two different messages are posted to two different conversations
- **THEN** both responses hold exactly one reply, with the same text

#### Scenario: Works without the database
- **WHEN** a message is posted while PostgreSQL is not reachable
- **THEN** the response is HTTP 200 with the fixed reply

### Requirement: Each turn is logged without the message text
Each accepted message SHALL produce one log record that holds the conversation id and the length of the message text in characters. The message text itself SHALL NOT appear in any log record.

#### Scenario: Turn log record
- **WHEN** a client posts `{"text": "Meu telefone é 81987654321"}` to a conversation
- **THEN** one log record holds that conversation id and a length of 26, and no log record contains `81987654321`
