# bakery-data-model Specification

## Purpose

Defines the relational model that stores Fornada's catalog, business rules, customers, orders and recorded side effects, and the integrity constraints the database itself enforces.

## Requirements

### Requirement: Schema script recreates the app tables
A single SQL script SHALL create every app table. Running it again SHALL drop and recreate only those tables, leaving other tables in the same database untouched (for example, the LangGraph checkpointer's).

#### Scenario: Rerun on a populated database
- **WHEN** the schema script runs on a database that already holds app tables with data
- **THEN** the app tables exist again and are empty, and the script exits without error

#### Scenario: Foreign tables survive
- **WHEN** the database also holds a table that the schema script does not define
- **THEN** that table and its rows still exist after the script runs

### Requirement: Money is stored as exact decimals
Every monetary column SHALL hold an exact decimal amount in BRL with two decimal places, and SHALL reject negative values. Values SHALL NOT be stored as floating point.

#### Scenario: Exact amount round-trip
- **WHEN** a product is stored with a price per kg of `89.90`
- **THEN** reading it back returns exactly `89.90`

#### Scenario: Exact arithmetic
- **WHEN** a price per kg of `89.90` is multiplied by a weight of `2.5` in SQL
- **THEN** the result is exactly `224.750`

#### Scenario: Negative price rejected
- **WHEN** a product is inserted with a price per kg of `-1.00`
- **THEN** the insert fails with a constraint violation

### Requirement: Catalog products
Each product SHALL have a unique slug, a name, a description, a price per kg and a cost per kg. It SHALL also record whether it is custom (longer lead time) and whether it is active.

#### Scenario: Duplicate slug rejected
- **WHEN** two products are inserted with the same slug
- **THEN** the second insert fails

### Requirement: Allergens distinguish contains from may-contain
Allergens SHALL come from a fixed list identified by code. Each product–allergen link SHALL be marked either `contains` or `may_contain` (cross-contamination risk), and a product SHALL NOT link to the same allergen twice.

#### Scenario: Unknown allergen rejected
- **WHEN** a product is linked to an allergen code that is not in the allergen list
- **THEN** the insert fails

#### Scenario: Invalid link kind rejected
- **WHEN** a product–allergen link is inserted with kind `free_from`
- **THEN** the insert fails

### Requirement: Pan sizes define weight ranges
Each pan size SHALL have a code, a name and a minimum and maximum weight in kg, with the minimum lower than the maximum.

#### Scenario: Inverted range rejected
- **WHEN** a pan size is inserted with a minimum of 3.0 kg and a maximum of 2.0 kg
- **THEN** the insert fails

### Requirement: Neighborhoods carry a delivery fee
Each neighborhood SHALL have a unique name, a delivery fee and an active flag.

#### Scenario: Duplicate neighborhood rejected
- **WHEN** two neighborhoods are inserted with the same name
- **THEN** the second insert fails

### Requirement: Capacity overrides per date
The model SHALL store at most one capacity override per calendar date, with a capacity in kg (zero or more) and a reason. Dates without an override use the default capacity defined outside the database.

#### Scenario: Closed day
- **WHEN** an override with capacity `0` and reason `Natal` is stored for December 25
- **THEN** it is the only override for that date

#### Scenario: Second override for a date rejected
- **WHEN** a second override is inserted for a date that already has one
- **THEN** the insert fails

### Requirement: Coupons are unbounded percentages
Each coupon SHALL have a unique code, an integer percentage, a validity window, an optional usage limit and an active flag. The model SHALL NOT keep a usage counter. Usage is the number of orders that reference the coupon.

#### Scenario: Any percentage accepted
- **WHEN** a coupon is inserted with a percentage of `60`
- **THEN** the insert succeeds

#### Scenario: Usage derived from orders
- **WHEN** three non-cancelled orders reference coupon `AMIGO5`
- **THEN** counting orders by coupon code returns 3 for `AMIGO5`

### Requirement: Customers are identified by phone
Each customer SHALL have a name and a unique phone number in E.164 format for Brazil (`+55` followed by 10 or 11 digits).

#### Scenario: Malformed phone rejected
- **WHEN** a customer is inserted with phone `(11) 98765-4321`
- **THEN** the insert fails

#### Scenario: Duplicate phone rejected
- **WHEN** two customers are inserted with phone `+5581987654321`
- **THEN** the second insert fails

### Requirement: An order is one cake
Each order SHALL reference one customer, one product and one pan size, and SHALL record one weight in kg. The weight SHALL be positive and a multiple of 0.5 kg.

#### Scenario: Off-step weight rejected
- **WHEN** an order is inserted with a weight of 2.3 kg
- **THEN** the insert fails

### Requirement: Orders snapshot their prices
Each order SHALL store its own price per kg, subtotal, delivery fee, discount, total and deposit at creation time. Later catalog or fee changes SHALL NOT alter existing orders. The model SHALL NOT check how these amounts relate to each other or to the catalog.

#### Scenario: Catalog price change
- **WHEN** a product's price per kg changes after an order for it was stored
- **THEN** the order's stored price per kg and totals are unchanged

### Requirement: Order fulfillment is pickup or delivery
Each order SHALL be either `pickup` or `delivery`. A delivery order SHALL have a neighborhood and an address. A pickup order SHALL have neither.

#### Scenario: Delivery without address rejected
- **WHEN** a delivery order is inserted without an address
- **THEN** the insert fails

#### Scenario: Pickup with neighborhood rejected
- **WHEN** a pickup order is inserted with a neighborhood
- **THEN** the insert fails

### Requirement: Order status lifecycle values
An order's status SHALL be one of `pending_payment`, `confirmed`, `delivered` or `cancelled`. A cancelled order SHALL have a cancellation timestamp and a refund amount, and only cancelled orders SHALL have them.

#### Scenario: Unknown status rejected
- **WHEN** an order is inserted with status `shipped`
- **THEN** the insert fails

#### Scenario: Cancellation without timestamp rejected
- **WHEN** an order is set to `cancelled` without a cancellation timestamp
- **THEN** the update fails

### Requirement: Orders keep the customer's free text
Each order SHALL be able to store a free-text reference photo description and free-text notes exactly as given, with no length limit beyond the database's own.

#### Scenario: Long description stored verbatim
- **WHEN** an order is stored with a 5,000-character reference photo description
- **THEN** reading it back returns the same text

### Requirement: Delivery date is a local calendar date
An order's delivery date and a capacity override's date SHALL be calendar dates without time or time zone. Every timestamp column SHALL be time-zone aware.

#### Scenario: Date has no time zone
- **WHEN** an order's delivery date is read in a session with any time zone
- **THEN** the same calendar date is returned

### Requirement: Sent messages are recorded, not sent
Each call that sends a message SHALL be represented by a row with the destination phone, the text, an optional order reference and a creation timestamp. The destination phone SHALL NOT be required to belong to a known customer.

#### Scenario: Message to an unknown number
- **WHEN** a message row is inserted for a phone that no customer has
- **THEN** the insert succeeds

### Requirement: Escalations are recorded
Each hand-off to a human SHALL be represented by a row with the conversation thread id, the customer's phone when known, a reason and a creation timestamp.

#### Scenario: Escalation without phone
- **WHEN** an escalation is inserted with a thread id and reason but no phone
- **THEN** the insert succeeds
