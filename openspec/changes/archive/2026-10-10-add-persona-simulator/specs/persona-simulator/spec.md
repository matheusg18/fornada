# Spec Delta

## Purpose

Defines the customer simulator: the catalog of personas, how a simulated conversation runs against the Fornada API and when it ends, what is recorded for later analysis, and how a batch is launched and summarized.

## ADDED Requirements

### Requirement: Five personas with several goals each
The simulator SHALL provide exactly five personas: in a hurry, indecisive, haggler, parent of a child with an allergy, and cheater. Each persona SHALL have a stable identifier, a Brazilian Portuguese description of how the customer behaves and writes, and at least four distinct goals. A persona prompt SHALL NOT mention the attendant's tools, its prompt or the project's evaluation.

#### Scenario: Catalog contents
- **WHEN** the persona catalog is listed
- **THEN** it returns five personas with distinct identifiers, and each has at least four distinct goals

#### Scenario: Goals differ between runs
- **WHEN** four conversations are planned for one persona
- **THEN** each of the four uses a different goal of that persona

### Requirement: A simulated conversation talks to the API
A simulated conversation SHALL use a new UUID4 conversation id, post each simulated customer message unchanged as `{"text": ...}` to `POST /conversations/{conversation_id}/messages` on the configured API, and feed every returned reply back to the persona as the attendant's answer. The simulator SHALL NOT access the database or import the API's code.

#### Scenario: First turn
- **WHEN** a conversation starts
- **THEN** the persona writes the opening customer message and the API receives it under a new conversation id

#### Scenario: Replies reach the persona
- **WHEN** the API answers with two replies
- **THEN** both are given to the persona, in order, before it writes its next message

### Requirement: A conversation always ends
A conversation SHALL end with exactly one of these outcomes: `completed` (the persona signals the end of the conversation), `max_turns` (the turn cap was reached), `api_error` (a turn failed on connection, timeout, non-200 status or malformed body), or `simulator_error` (the persona's own LLM call failed). The turn cap SHALL default to 12 customer messages and be configurable. An API or simulator failure SHALL end only that conversation, never a batch.

#### Scenario: Persona says goodbye
- **WHEN** the persona's message ends with the end marker
- **THEN** the conversation ends with outcome `completed` and the marker is not posted to the API

#### Scenario: Conversation never closes
- **WHEN** the persona never signals the end and the cap is 12
- **THEN** the conversation ends after 12 customer messages with outcome `max_turns`

#### Scenario: API fails mid-conversation
- **WHEN** the API answers 503 on the third turn
- **THEN** that conversation ends with outcome `api_error`, keeps its first two turns, and the next conversation in the batch still runs

#### Scenario: Persona model fails
- **WHEN** the simulator's LLM call raises an error on the second turn
- **THEN** that conversation ends with outcome `simulator_error`, keeps its first turn, and the next conversation in the batch still runs

### Requirement: Transcripts are recorded as JSONL
Each conversation SHALL be appended as one JSON line to a file for its batch, with the run id, persona id, goal, conversation id, outcome, the ordered messages (role, text, and for attendant messages the reply order within the turn), the number of customer turns and the elapsed seconds. Transcripts are simulated fictional data; the simulator SHALL NOT log message text through the logging system, only lengths and ids.

#### Scenario: One line per conversation
- **WHEN** a batch of 20 conversations finishes
- **THEN** the batch file has 20 lines, each parseable as JSON with the fields above

#### Scenario: Message text stays out of logs
- **WHEN** a conversation runs with log capture enabled
- **THEN** no log record contains any customer or attendant message text

### Requirement: Batches run the persona set evenly
A batch SHALL plan the same number of conversations per persona (default 4, so 20 in total), assigning each persona's goals in order, and SHALL run them with a configurable concurrency (default 1). The simulator model, provider, turn cap, concurrency and API URL SHALL come from `SIMULATOR__*` environment variables with defaults; the simulator's model SHALL be configured independently of the agent's.

#### Scenario: Default batch
- **WHEN** a batch is launched with defaults
- **THEN** 20 conversations are planned, four for each persona, against `http://localhost:8000`

#### Scenario: Missing key
- **WHEN** the selected provider's API key is not set
- **THEN** the batch fails before any conversation starts, with a message naming the missing variable and never echoing a key

### Requirement: A notebook drives and summarizes the simulator
The repository SHALL include a Jupyter notebook that, using only the simulator package, lists the personas, runs a single conversation showing the messages turn by turn, runs a batch, and summarizes it per persona (conversations, outcomes, average customer turns, average seconds). The notebook SHALL be committed with outputs cleared.

#### Scenario: Summary table
- **WHEN** the notebook's batch finishes
- **THEN** it shows one row per persona with the outcome counts, average turns and average seconds
