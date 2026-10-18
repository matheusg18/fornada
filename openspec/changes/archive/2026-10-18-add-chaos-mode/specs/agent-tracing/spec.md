# Spec Delta

## ADDED Requirements

### Requirement: Turn spans say whether chaos was on
With chaos mode on, each `invoke_agent` span SHALL carry `fornada.chaos.enabled` = `true` from its start. With chaos mode off, the attribute SHALL be absent.

#### Scenario: Chaos on
- **WHEN** chaos mode is on and a client posts a customer message
- **THEN** the turn's `invoke_agent` span has `fornada.chaos.enabled` = `true`

#### Scenario: Chaos off
- **WHEN** chaos mode is off
- **THEN** no span carries any `fornada.chaos.*` attribute

### Requirement: Tool spans record the injected delay
With chaos mode on, each `execute_tool` span SHALL carry `fornada.chaos.delay_ms` with the delay injected into that call, as an integer, including `0`.

#### Scenario: Delayed call
- **WHEN** chaos mode is on and `search_catalog` is delayed 750 ms
- **THEN** the `execute_tool search_catalog` span has `fornada.chaos.delay_ms` = `750` and lasts at least 750 ms

### Requirement: Tool spans name the injected fault
With chaos mode on, an `execute_tool` span SHALL carry `fornada.chaos.fault` when a fault changed that call's outcome: `capacity_unavailable` for an injected `check_capacity` failure, and `price_increase` for a `calculate_quote` or `create_order` priced with the raised price. A call with no such fault SHALL NOT carry it. An injected failure SHALL also mark the span as an error, like any failed tool call.

#### Scenario: Injected outage
- **WHEN** chaos mode injects a `check_capacity` failure
- **THEN** the `execute_tool check_capacity` span has `fornada.chaos.fault` = `capacity_unavailable`, status ERROR and `error.type` = `tool_error`

#### Scenario: Raised price
- **WHEN** a conversation's second `calculate_quote` uses the raised price
- **THEN** its `execute_tool calculate_quote` span has `fornada.chaos.fault` = `price_increase`, and the first quote's span has no `fornada.chaos.fault`

#### Scenario: Latency alone is not a fault
- **WHEN** chaos mode is on and `search_catalog` is only delayed
- **THEN** its span has `fornada.chaos.delay_ms` and no `fornada.chaos.fault`
