# Spec Delta

## ADDED Requirements

### Requirement: Tool database statements are traced
With tracing enabled, each SQL statement a tool runs SHALL produce one span of kind CLIENT in the turn's trace, under that tool's span. The span SHALL name the database system and the database, and SHALL carry the statement text.

#### Scenario: Catalog lookup inside a turn
- **WHEN** tracing is enabled and a posted customer message makes the agent call `search_catalog`
- **THEN** the exported trace has a CLIENT span for each statement the tool ran, with the `execute_tool search_catalog` span as its ancestor, `db.system.name` = `postgresql`, `db.namespace` = `fornada` and the statement in `db.query.text`

### Requirement: Conversation-state statements are traced
With tracing enabled, each SQL statement the API runs to load or save a conversation's state SHALL produce one span of kind CLIENT in the trace of the turn that needed it.

#### Scenario: Checkpoint read and write during a turn
- **WHEN** tracing is enabled and a customer posts a message to an existing conversation
- **THEN** the turn's trace has CLIENT spans for the statements that read the conversation's saved state and for those that save the new state, under the turn's SERVER span

### Requirement: Each database statement is traced once
A SQL statement SHALL produce exactly one database CLIENT span, whichever database path ran it.

#### Scenario: Tool statement not duplicated
- **WHEN** tracing is enabled and a tool runs one statement
- **THEN** the trace has one CLIENT span with that statement's text, not two

### Requirement: Database spans carry no bound values
Database spans SHALL carry the SQL text with its placeholders, and SHALL NOT carry the values bound to them, in any attribute.

#### Scenario: Order created with a customer's details
- **WHEN** tracing is enabled and `create_order` inserts a customer's name, phone and address
- **THEN** the INSERT's span shows placeholders where the values go, and no attribute of any database span contains that name, phone or address

### Requirement: Failed tool statements are marked without the server's detail
With tracing enabled, a tool statement that fails SHALL end its span with error status. The status description SHALL NOT contain the `DETAIL:` line PostgreSQL adds to the error, which holds the offending row values.

#### Scenario: Unique violation on insert
- **WHEN** tracing is enabled and a tool's INSERT fails with a unique violation
- **THEN** the statement's span has status ERROR, and its status description has no `DETAIL:` line and none of the inserted values

### Requirement: No database instrumentation when tracing is off
When tracing is disabled, the API SHALL NOT instrument either database path, and database statements SHALL run as they would without telemetry.

#### Scenario: Tracing disabled
- **WHEN** the API starts with tracing disabled and a customer posts a message that makes a tool query the database
- **THEN** no database span is created and the turn's response is the same as with tracing enabled
