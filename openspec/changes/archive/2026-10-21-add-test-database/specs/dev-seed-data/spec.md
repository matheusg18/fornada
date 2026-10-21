# Spec Delta

## MODIFIED Requirements

### Requirement: Seed is a committed SQL file
The seed SHALL be a plain SQL file committed to the repository. Applying it SHALL need only `psql` and SHALL produce the same rows on every run for the same run day; dates and timestamps move with the run day.

#### Scenario: Apply with psql
- **WHEN** the schema script and then the seed file run with `psql` against an empty `fornada` database
- **THEN** both finish without error and every app table that the seed covers has rows

#### Scenario: Same run day, same rows
- **WHEN** the seed is applied twice with the same run day, on different calendar days
- **THEN** both applications produce identical rows in every seeded table, apart from generated ids and column defaults such as `created_at`

### Requirement: Seed dates are relative to the run day
Every seeded date and timestamp SHALL be expressed relative to the run day. The run day SHALL be the date given in the `fornada.seed_day` session setting when it is set, and otherwise the current calendar date in `America/Sao_Paulo` at the moment the seed runs. Fixed-day holidays SHALL be stored for the run day's year and the next.

#### Scenario: Seed applied a month later
- **WHEN** the seed is applied without `fornada.seed_day`, 30 days after a previous application without it
- **THEN** every seeded order date is 30 days later than in the previous application

#### Scenario: Late evening in UTC
- **WHEN** the seed runs without `fornada.seed_day` at 22:00 in `America/Sao_Paulo` (01:00 UTC of the next day)
- **THEN** relative dates use the São Paulo calendar date, not the UTC one

#### Scenario: Pinned run day
- **WHEN** the seed runs in a session where `fornada.seed_day` is `2026-03-09`
- **THEN** non-cancelled orders on 2026-03-12 total 15.0 kg, and the holidays stored are those of 2026 and 2027

#### Scenario: Invalid run day
- **WHEN** `fornada.seed_day` holds a value that is not an ISO date (`YYYY-MM-DD`)
- **THEN** the seed fails before inserting any row
