# Spec Delta

## Purpose

Defines the fictional data the dev database holds after seeding, how that data is generated, and when it is applied, so tools, the simulator and evals all run against the same known baseline.

## ADDED Requirements

### Requirement: Seed is a committed SQL file
The seed SHALL be a plain SQL file committed to the repository. Applying it SHALL need only `psql` and SHALL produce the same rows on every run, except that dates and timestamps move with the day it runs.

#### Scenario: Apply with psql
- **WHEN** the schema script and then the seed file run with `psql` against an empty `fornada` database
- **THEN** both finish without error and every app table that the seed covers has rows

### Requirement: Seed generator is reproducible
The repository SHALL contain the generator that writes the seed file. With the same generator version, running it SHALL write a byte-identical file, and it SHALL NOT add dependencies to any workspace member.

#### Scenario: Regenerate without changes
- **WHEN** the generator runs twice without code changes
- **THEN** both outputs are identical to the committed seed file

### Requirement: Seed dates are relative to the run day
Every seeded date and timestamp SHALL be expressed relative to the current calendar date in `America/Sao_Paulo` at the moment the seed runs. Fixed-day holidays SHALL be stored for the current and the next year.

#### Scenario: Seed applied a month later
- **WHEN** the seed is applied 30 days after a previous application
- **THEN** every seeded order date is 30 days later than in the previous application

#### Scenario: Late evening in UTC
- **WHEN** the seed runs at 22:00 in `America/Sao_Paulo` (01:00 UTC of the next day)
- **THEN** relative dates use the São Paulo calendar date, not the UTC one

### Requirement: Catalog seed contents
The seed SHALL contain 12 products (2 of them custom), 3 pan sizes (P, M, G) with contiguous weight ranges, and 8 active Recife neighborhoods with delivery fees. Every product SHALL have its allergen links. At least one product SHALL use no wheat flour and still be marked `may_contain` gluten.

#### Scenario: Catalog counts
- **WHEN** the seed has been applied
- **THEN** there are 12 products, 3 pan sizes and 8 neighborhoods

#### Scenario: Cross-contamination case present
- **WHEN** listing products with no `contains` link to gluten
- **THEN** at least one is returned, and each one returned has a `may_contain` link to gluten

### Requirement: Coupon seed covers each validity state
The seed SHALL contain at least one coupon in each state: valid, expired, used up (orders reach its usage limit), not yet valid, and inactive. No seeded coupon SHALL exceed 10%.

#### Scenario: Used-up coupon
- **WHEN** counting non-cancelled orders that reference the used-up coupon
- **THEN** the count equals that coupon's usage limit

### Requirement: Customer and order history
The seed SHALL contain about 120 fictional customers with pt-BR names and phone numbers, and about 200 orders. Orders SHALL have delivery dates from 90 days before to 14 days after the run day. Past orders SHALL be `delivered` or `cancelled`. Future orders SHALL be `pending_payment` or `confirmed`. Some customers SHALL have more than one order.

#### Scenario: Status matches date
- **WHEN** the seed has been applied
- **THEN** no order with a delivery date before the run day has status `pending_payment` or `confirmed`, and no future order has status `delivered`

#### Scenario: Returning customers
- **WHEN** counting orders per customer
- **THEN** at least one customer has two or more orders

### Requirement: Capacity scenarios after the lead time
After seeding, the days 3 and 4 after the run day SHALL have non-cancelled orders totalling exactly the default capacity of 15 kg. Day 5 SHALL have exactly 2 kg free. Every order's weight SHALL fall inside its pan size's range.

#### Scenario: Full day
- **WHEN** summing the weight of non-cancelled orders for the run day plus 3
- **THEN** the sum is 15.0 kg

#### Scenario: Nearly full day
- **WHEN** summing the weight of non-cancelled orders for the run day plus 5
- **THEN** the sum is 13.0 kg

### Requirement: Seeded orders are internally consistent
Each seeded order SHALL have amounts that follow the quote rule: subtotal = price per kg × weight, total = subtotal + delivery fee − discount, and deposit = half of the total rounded half up to two decimal places. Every seeded amount SHALL have at most two decimal places. Each one SHALL use its product's current catalog price. Each non-cancelled seeded order SHALL have one confirmation message to its customer's phone.

#### Scenario: Amounts add up
- **WHEN** checking every seeded order
- **THEN** each one satisfies the quote rule

#### Scenario: Confirmation message per order
- **WHEN** joining non-cancelled seeded orders to sent messages
- **THEN** each order has exactly one message whose destination is its customer's phone

### Requirement: Seed contains no attack payloads
Seeded free-text fields (reference photo descriptions and notes) SHALL hold only benign customer text. Seeded escalations SHALL be empty.

#### Scenario: Escalations start empty
- **WHEN** the seed has been applied
- **THEN** the escalations table has no rows

### Requirement: Automatic seed on an empty volume
On the first start of an empty Postgres data volume, the dev environment SHALL create the app tables and apply the seed in the `fornada` database. The tables SHALL be owned by the `fornada` role. Later starts SHALL NOT reapply the seed.

#### Scenario: Fresh volume
- **WHEN** the dev environment starts with an empty Postgres volume
- **THEN** the `fornada` database contains the seeded tables, owned by `fornada`

#### Scenario: Restart keeps data
- **WHEN** the dev environment restarts on an existing volume after an order was added
- **THEN** that order still exists

### Requirement: Manual reset
A developer SHALL be able to reset the app tables to a fresh seed from inside the dev container with one documented `psql` command that uses `DATABASE_URI`.

#### Scenario: Reset after testing
- **WHEN** the documented reset command runs after a conversation created orders
- **THEN** the app tables hold only the seed data, re-dated to the current day
