# Spec Delta

## ADDED Requirements

### Requirement: Chaos switch setting
`CHAOS__ENABLED` SHALL turn chaos mode on or off. It SHALL accept boolean values and default to off. A value that is not a boolean SHALL make settings loading fail with an error that names `CHAOS__ENABLED`.

#### Scenario: Default off
- **WHEN** `CHAOS__ENABLED` is not set
- **THEN** chaos mode is off

#### Scenario: Turned on
- **WHEN** `CHAOS__ENABLED=true`
- **THEN** chaos mode is on

#### Scenario: Not a boolean
- **WHEN** `CHAOS__ENABLED=maybe`
- **THEN** settings loading fails with an error that names `CHAOS__ENABLED`

### Requirement: Chaos latency settings
`CHAOS__LATENCY_MIN_MS` and `CHAOS__LATENCY_MAX_MS` SHALL set the range of the injected tool delay, in whole milliseconds, defaulting to `200` and `2000`. Each SHALL be zero or more, and the minimum SHALL NOT exceed the maximum; otherwise settings loading SHALL fail with an error that names the offending variable.

#### Scenario: Defaults
- **WHEN** neither variable is set
- **THEN** the latency range is 200 to 2000 ms

#### Scenario: Negative value
- **WHEN** `CHAOS__LATENCY_MIN_MS=-1`
- **THEN** settings loading fails with an error that names `CHAOS__LATENCY_MIN_MS`

#### Scenario: Minimum above maximum
- **WHEN** `CHAOS__LATENCY_MIN_MS=3000` and `CHAOS__LATENCY_MAX_MS=2000`
- **THEN** settings loading fails with an error that names `CHAOS__LATENCY_MIN_MS`

### Requirement: Chaos capacity failure rate setting
`CHAOS__CAPACITY_FAILURE_RATE` SHALL set the probability that a `check_capacity` call fails under chaos mode. It SHALL accept a number from 0 to 1 inclusive and default to `0.1`. A value outside that range SHALL make settings loading fail with an error that names `CHAOS__CAPACITY_FAILURE_RATE`.

#### Scenario: Default rate
- **WHEN** `CHAOS__CAPACITY_FAILURE_RATE` is not set
- **THEN** the failure rate is 0.1

#### Scenario: Out of range
- **WHEN** `CHAOS__CAPACITY_FAILURE_RATE=1.5`
- **THEN** settings loading fails with an error that names `CHAOS__CAPACITY_FAILURE_RATE`

### Requirement: Chaos price increase setting
`CHAOS__PRICE_INCREASE_PCT` SHALL set the percentage by which a conversation's price per kg rises after its first quote under chaos mode. It SHALL accept a decimal number greater than zero and at most 100, and default to `10`. A value outside that range SHALL make settings loading fail with an error that names `CHAOS__PRICE_INCREASE_PCT`.

#### Scenario: Default increase
- **WHEN** `CHAOS__PRICE_INCREASE_PCT` is not set
- **THEN** the increase is exactly 10%

#### Scenario: Zero
- **WHEN** `CHAOS__PRICE_INCREASE_PCT=0`
- **THEN** settings loading fails with an error that names `CHAOS__PRICE_INCREASE_PCT`

### Requirement: Chaos seed setting
`CHAOS__SEED` SHALL optionally set an integer seed for chaos mode's random draws. When it is not set, draws SHALL NOT be reproducible. A value that is not an integer SHALL make settings loading fail with an error that names `CHAOS__SEED`.

#### Scenario: No seed
- **WHEN** `CHAOS__SEED` is not set
- **THEN** chaos mode has no seed

#### Scenario: Not an integer
- **WHEN** `CHAOS__SEED=abc`
- **THEN** settings loading fails with an error that names `CHAOS__SEED`
