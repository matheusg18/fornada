# Spec Delta

## Purpose

Defines how the Fornada API reaches PostgreSQL: one shared connection pool, one session per request, and typed models that mirror the app tables defined by the schema script.

## ADDED Requirements

### Requirement: Every app table has a model
The API SHALL have one model for each app table in the schema script: products, allergens, product allergens, pan sizes, neighborhoods, capacity overrides, coupons, customers, orders, sent messages and escalations. Each model SHALL map every column of its table, with the same name, nullability and primary key.

#### Scenario: Model columns match the table
- **WHEN** each model's columns are compared with the live table's columns in the seeded database
- **THEN** both have the same column names, and each column has the same nullability

#### Scenario: Every seeded row loads
- **WHEN** every row of every app table in the seeded database is loaded through its model
- **THEN** no load fails and the number of rows loaded equals the table's row count

### Requirement: Models never change the schema
The schema script SHALL remain the only source of table definitions. Starting the API or importing the models SHALL NOT create, alter or drop any table.

#### Scenario: Startup against the seeded database
- **WHEN** the API starts and stops against the seeded database
- **THEN** the set of tables and their columns is unchanged

### Requirement: Money and weights load as exact decimals
Monetary amounts and weights SHALL load as exact decimal values, never as floating point.

#### Scenario: Price per kg round-trip
- **WHEN** the product with slug `bolo-chocolate` is loaded
- **THEN** its price per kg is the exact decimal `89.90`

### Requirement: Dates and timestamps keep their kind
Calendar-date columns SHALL load as dates without time or time zone. Timestamp columns SHALL load as time-zone-aware datetimes.

#### Scenario: Order dates
- **WHEN** a seeded order is loaded
- **THEN** its delivery date is a plain date and its creation time is a time-zone-aware datetime

### Requirement: Constrained text values are typed
Order status, order fulfillment and product–allergen kind SHALL load as typed values limited to the values the schema accepts (`pending_payment`, `confirmed`, `delivered`, `cancelled`; `pickup`, `delivery`; `contains`, `may_contain`).

#### Scenario: Known status
- **WHEN** a seeded cancelled order is loaded
- **THEN** its status equals the `cancelled` value of the order status type

### Requirement: Related rows are reachable from a model
Models SHALL expose the foreign-key relations of the schema: an order's customer, product, pan size, neighborhood and coupon; a customer's orders; a product's allergen links, each with its allergen.

#### Scenario: Product allergens
- **WHEN** the product `bolo-chocolate` is loaded with its allergen links
- **THEN** the links include `gluten` as `contains` and `soy` as `may_contain`

#### Scenario: Order customer
- **WHEN** a seeded order is loaded with its customer
- **THEN** the customer's id equals the order's customer id

### Requirement: One session per request
Each API request that needs the database SHALL receive its own session, and that session SHALL be closed when the request ends, whether it succeeded or failed. Sessions SHALL NOT be shared between concurrent requests.

#### Scenario: Session closed after a failing request
- **WHEN** a request that uses a session raises an error
- **THEN** the session is closed and its connection returns to the pool

### Requirement: No implicit commits
A request session SHALL NOT commit on its own. Changes SHALL be persisted only when the code handling the request commits explicitly; uncommitted changes SHALL be rolled back when the session closes.

#### Scenario: Uncommitted insert discarded
- **WHEN** a request session adds a row and the request ends without a commit
- **THEN** the row is not in the database

### Requirement: Connection string accepts the plain PostgreSQL form
The database connection SHALL accept a URL in the plain `postgresql://` form, the same form the dev container exposes, and SHALL connect with an asynchronous driver.

#### Scenario: Dev container URI
- **WHEN** `DB__URL` is set to the value of `DATABASE_URI` from the dev container
- **THEN** the API connects to the `fornada` database
