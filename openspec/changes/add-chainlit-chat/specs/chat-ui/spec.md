# Spec Delta

## Purpose

Defines the minimal web chat a person uses to talk to the Fornada attendant: how a chat session maps to an API conversation, how messages and replies flow, what the person sees when the API fails, and how the chat is configured and launched.

## ADDED Requirements

### Requirement: One conversation id per chat session
Each new chat session SHALL generate a new UUID4 conversation id and use it for every message sent in that session. Starting a new chat SHALL generate a different id.

#### Scenario: Messages in one session share an id
- **WHEN** a person sends two messages in the same chat session
- **THEN** both are posted to the API under the same conversation id

#### Scenario: New chat gets a new id
- **WHEN** a person starts a new chat after sending messages in a previous one
- **THEN** the next message is posted under a conversation id different from the previous session's

### Requirement: Messages go to the conversation API
Each message the person sends SHALL be posted, unchanged, as `{"text": ...}` to `POST /conversations/{conversation_id}/messages` on the configured API. The chat SHALL NOT generate replies itself and SHALL NOT access the database.

#### Scenario: Person sends a message
- **WHEN** a person types `Oi, quero um bolo de chocolate` and sends it
- **THEN** the API receives one request to `/conversations/<session id>/messages` with body `{"text": "Oi, quero um bolo de chocolate"}`

### Requirement: Every reply is shown in order
For a successful API response, the chat SHALL show each item of `replies` as its own bot message, with its `text` unchanged, in the order the API returned them.

#### Scenario: Two replies in one turn
- **WHEN** the API answers a message with replies `["Orçamento: R$ 180,00", "Link de pagamento: …"]`
- **THEN** the chat shows two bot messages, `Orçamento: R$ 180,00` first and `Link de pagamento: …` second

### Requirement: API failures show a fixed error message
When the API cannot be reached, does not answer within the request timeout, or answers with a non-200 status, the chat SHALL show one fixed Brazilian Portuguese error message, show no partial reply, and keep the session and its conversation id usable for the next message.

#### Scenario: API is down
- **WHEN** a person sends a message while the API is not running
- **THEN** the chat shows the fixed error message and no other bot message for that turn

#### Scenario: API returns an error status
- **WHEN** the API answers a message with HTTP 500
- **THEN** the chat shows the fixed error message

#### Scenario: Recovers after a failure
- **WHEN** a message fails because the API is down, the API comes back, and the person sends another message in the same session
- **THEN** that message is posted under the same conversation id and its replies are shown

### Requirement: Configurable API address
The chat SHALL read the API base URL from the `CHAT__API_URL` environment variable and SHALL use `http://localhost:8000` when it is not set.

#### Scenario: Default address
- **WHEN** the chat runs without `CHAT__API_URL`
- **THEN** messages are posted to `http://localhost:8000/conversations/<id>/messages`

#### Scenario: Custom address
- **WHEN** the chat runs with `CHAT__API_URL=http://api.local:9000`
- **THEN** messages are posted to `http://api.local:9000/conversations/<id>/messages`

### Requirement: Message text is never logged
The chat SHALL NOT write the person's message text or the bot's reply text to any log.

#### Scenario: Phone number in a message
- **WHEN** a person sends `Meu telefone é 81987654321`
- **THEN** no log line written by the chat contains `81987654321`

### Requirement: Text-only input
The chat SHALL accept only typed text. Attaching files and editing a message that was already sent SHALL be unavailable, because the API takes text only and cannot rewind a conversation.

#### Scenario: No attachments
- **WHEN** a person opens the chat
- **THEN** there is no control to attach a file

#### Scenario: No editing sent messages
- **WHEN** a person has sent a message
- **THEN** there is no control to edit that message

### Requirement: Development launch command
The repository SHALL document one command that serves the chat with auto-reload on `localhost:8001`, so it can run next to the API on port 8000.

#### Scenario: Developer starts both apps
- **WHEN** a developer starts the API and then the chat with their documented commands in the dev container
- **THEN** the chat page loads on `http://localhost:8001` and a message sent there gets the API's reply
