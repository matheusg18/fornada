# Spec Delta

## Purpose

Gives tests a PostgreSQL that exists only for them, loaded with the seed for a fixed day, so test results depend neither on the dev database's contents nor on the date the tests run.

## ADDED Requirements

### Requirement: The dev environment provides a test-only database
The dev environment SHALL run a PostgreSQL server for tests only, separate from the dev `postgres` service, with the same image and tag. It SHALL start with the dev environment, keep no data across restarts, publish no host port and use its own role and password. The `dev` service SHALL receive its connection URL as `TEST_DATABASE_URI`, in the plain `postgresql://` form.

#### Scenario: Reachable from the dev container
- **WHEN** the dev environment has started
- **THEN** `psql "$TEST_DATABASE_URI" -c 'SELECT 1'` succeeds from the dev container, and the server reports the same PostgreSQL version as the dev database

#### Scenario: Empty after a restart
- **WHEN** the test service restarts after a test session loaded data into it
- **THEN** it holds no app tables until a test session loads them again

#### Scenario: Dev database untouched
- **WHEN** a full integration test session has run
- **THEN** the dev database's orders, customers and sent messages are the same as before the session

### Requirement: Tests use a fixed seed day
Tests that read seeded data SHALL load the seed for one fixed seed day, defined once in the test code, and SHALL compute every expected date from that day, never from the wall clock. Code under test that needs the current date SHALL receive a clock fixed at the seed day.

#### Scenario: Same result on any calendar day
- **WHEN** the integration tests run on two different calendar days without any database reset in between
- **THEN** both runs have the same outcomes and the same number of skipped tests

#### Scenario: Full day is known in advance
- **WHEN** a test needs the seeded full day
- **THEN** it uses the seed day plus 3, which holds exactly 15 kg of non-cancelled orders

### Requirement: Each test session starts from a fresh seed
At the start of each test session, the integration tests SHALL recreate the app tables in the test database and load the seed for the fixed seed day, so data left by an earlier session cannot change the result.

#### Scenario: Leftover order from an earlier session
- **WHEN** an earlier session committed an order on the seed day plus 8, and a new session starts
- **THEN** the new session sees the seeded orders only

### Requirement: Integration tests skip without the test database
When `TEST_DATABASE_URI` is not set, the tests that need the database SHALL be skipped with a reason that names the variable. Tests SHALL NOT fall back to `DATABASE_URI`.

#### Scenario: Outside the dev container
- **WHEN** the API's test suite runs without `TEST_DATABASE_URI`
- **THEN** the unit tests run, and each integration test is reported as skipped because `TEST_DATABASE_URI` is not set
