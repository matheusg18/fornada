# Spec Delta

## Purpose

Opt-in fault injection for the attendant's tools, so simulated conversations meet slow tools, a `check_capacity` outage and a price that changes mid-conversation, and error analysis can observe how the naive agent reacts.

## ADDED Requirements

### Requirement: Chaos mode is off unless enabled
With chaos mode off, tools SHALL add no delay, SHALL NOT inject failures and SHALL price at the catalog's price per kg. Chaos mode SHALL apply to every conversation the API process serves while it is on.

#### Scenario: Default
- **WHEN** the API runs without any `CHAOS__*` variable
- **THEN** `check_capacity` never fails by injection and `calculate_quote` for `bolo-chocolate`, 2.5 kg, pickup returns subtotal `"224.75"` on every call

### Requirement: Tool calls are delayed at random
With chaos mode on, each tool call SHALL wait a delay drawn uniformly between the configured minimum and maximum, in milliseconds, before the tool does its work. The delay SHALL be part of the tool call's duration.

#### Scenario: Delay within range
- **WHEN** chaos mode is on with latency from 200 to 2000 ms and `search_catalog` is called
- **THEN** the call takes at least 200 ms longer than its work, and the recorded delay is between 200 and 2000 ms

#### Scenario: Zero range
- **WHEN** chaos mode is on with minimum and maximum latency both 0
- **THEN** tool calls are not delayed

### Requirement: check_capacity fails at the configured rate
With chaos mode on, each `check_capacity` call SHALL fail with probability equal to the configured failure rate. An injected failure SHALL NOT read the database and SHALL return the same error result text as an unexpected failure of `check_capacity`, so the model cannot tell it apart from a real outage.

#### Scenario: Injected outage
- **WHEN** chaos mode is on with failure rate 1.0 and `check_capacity` is called for any date
- **THEN** the tool result is marked as an error with text `internal error in check_capacity; try again later or escalate to a human`

#### Scenario: Rate zero
- **WHEN** chaos mode is on with failure rate 0.0
- **THEN** `check_capacity` returns the date's capacity report on every call

#### Scenario: Other tools never fail by injection
- **WHEN** chaos mode is on with failure rate 1.0 and `calculate_quote` is called with valid arguments
- **THEN** it returns a quote

### Requirement: Injected failures are logged
Each injected `check_capacity` failure SHALL be logged at WARNING level with the tool name and the fault, and without an exception traceback or message text.

#### Scenario: Log record
- **WHEN** chaos mode injects a `check_capacity` failure
- **THEN** one WARNING record names `check_capacity` and the fault `capacity_unavailable`

### Requirement: Price rises after a conversation's first quote
With chaos mode on, once a conversation has had one successful `calculate_quote`, its later `calculate_quote` and `create_order` calls SHALL use each product's price per kg raised by the configured percentage, rounded half up to cents. The increase SHALL apply once, not compound, and SHALL NOT change the database.

#### Scenario: Second quote in a conversation
- **WHEN** chaos mode is on with a 10% increase and one conversation calls `calculate_quote` twice for `bolo-chocolate` (89.90/kg), 2.5 kg, pickup
- **THEN** the first quote has price per kg `"89.90"` and subtotal `"224.75"`, and the second has price per kg `"98.89"` and subtotal `"247.23"`

#### Scenario: Order after the quote
- **WHEN** in that conversation `create_order` follows the first quote
- **THEN** the order is saved with price per kg `"98.89"`

#### Scenario: Increase does not compound
- **WHEN** the conversation calls `calculate_quote` a third time with the same arguments
- **THEN** the price per kg is still `"98.89"`

#### Scenario: Other conversations
- **WHEN** a second conversation calls `calculate_quote` for the first time with the same arguments
- **THEN** its price per kg is `"89.90"`

#### Scenario: Failed first quote
- **WHEN** a conversation's first `calculate_quote` fails (for example, invalid weight) and a valid one follows
- **THEN** the valid quote uses the catalog price

#### Scenario: Catalog unchanged
- **WHEN** a conversation's price has risen
- **THEN** `search_catalog` and the `products` table still show `"89.90"` for `bolo-chocolate`

### Requirement: Chaos draws are reproducible with a seed
When a chaos seed is configured, the sequence of delays and `check_capacity` failure decisions SHALL be the same for the same sequence of tool calls.

#### Scenario: Same seed
- **WHEN** two API processes start with the same seed and receive the same tool calls in the same order
- **THEN** they inject the same delays and the same failures

### Requirement: Startup warns when chaos is on
When the API starts with chaos mode on, it SHALL log one WARNING record that says chaos mode is on and gives the latency range, failure rate, price increase and whether a seed is set.

#### Scenario: Chaos on at startup
- **WHEN** the API starts with `CHAOS__ENABLED=true`
- **THEN** one WARNING record at startup reports chaos mode and its settings

#### Scenario: Chaos off at startup
- **WHEN** the API starts with chaos mode off
- **THEN** no chaos record is logged
