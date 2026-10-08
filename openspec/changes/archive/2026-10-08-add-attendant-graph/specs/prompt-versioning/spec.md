# Spec Delta

## Purpose

Defines where the attendant's system prompt lives and how each prompt is identified by a version derived from its content, so every answer can be traced to the exact prompt text that produced it.

## ADDED Requirements

### Requirement: The system prompt lives in a versioned file
The attendant's system prompt SHALL be the content of one Markdown file in the repository, written in Brazilian Portuguese. Changing the prompt SHALL mean editing that file, so every change is reviewed and kept in git history.

#### Scenario: Prompt text comes from the file
- **WHEN** the attendant loads its system prompt
- **THEN** the text sent to the model equals the file's content

### Requirement: The prompt version is derived from its content
The prompt version SHALL be `sha256:` followed by the first 12 lowercase hex digits of the SHA-256 of the prompt's UTF-8 bytes, with line endings normalized to `\n`. The same content SHALL always give the same version; any change to the content SHALL give a different one.

#### Scenario: Same content
- **WHEN** the prompt is loaded twice without changes
- **THEN** both loads give the same version

#### Scenario: One character changes
- **WHEN** one character of the prompt file changes
- **THEN** the version changes

#### Scenario: Line endings only
- **WHEN** the file is saved with `\r\n` line endings and otherwise the same content
- **THEN** the version does not change

#### Scenario: Version is reproducible outside the app
- **WHEN** someone computes the SHA-256 of the committed file with `\n` line endings
- **THEN** its first 12 hex digits match the version the app reports

### Requirement: The version travels with the prompt
Loading the prompt SHALL return its text and its version together. No code path SHALL send the prompt to the model without its version being recorded.

#### Scenario: Load result
- **WHEN** the prompt is loaded
- **THEN** the result holds the text and the version

### Requirement: Each model answer records its prompt version
Every model message the attendant adds to a conversation SHALL carry the version of the system prompt used for that call, stored with the message in the conversation's memory.

#### Scenario: History across a prompt change
- **WHEN** a conversation has a model answer made with version A, the prompt changes to version B and the next turn adds another answer
- **THEN** the stored history shows version A on the first answer and version B on the second

### Requirement: The turn state records the current prompt version
The agent's turn state SHALL hold the version of the prompt used in its latest model call, and the turn output SHALL expose it.

#### Scenario: State after a turn
- **WHEN** a turn ends with prompt version `sha256:0123456789ab`
- **THEN** the turn output's prompt version is `sha256:0123456789ab`

### Requirement: The prompt version is logged at startup
When the API starts, it SHALL log the system prompt version it loaded, without the prompt text.

#### Scenario: Startup log
- **WHEN** the API starts
- **THEN** one startup log record holds the prompt version
