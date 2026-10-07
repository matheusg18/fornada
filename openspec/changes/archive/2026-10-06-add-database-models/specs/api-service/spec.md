# Spec Delta

## Purpose

Defines the Fornada HTTP application: how it starts and stops, how it is launched in development, and the endpoints it exposes for operating it.

## ADDED Requirements

### Requirement: App loads settings and logging at startup
The API SHALL load its settings and configure JSON logging before serving requests. Invalid settings SHALL stop startup with the settings error, before any request is served.

#### Scenario: Missing database URL
- **WHEN** the API starts without `DB__URL`
- **THEN** startup fails with an error that names `DB__URL`

### Requirement: Database pool lives with the app
The API SHALL open its database connection pool when it starts and release every pooled connection when it shuts down.

#### Scenario: Clean shutdown
- **WHEN** the API starts, serves a request that uses the database and then shuts down
- **THEN** no connection from the API remains open on the database server

### Requirement: Development server command
The repository SHALL document one command, run from the repo root, that serves the API with auto-reload for development.

#### Scenario: Developer starts the API
- **WHEN** a developer runs the documented command in the dev container with a valid root `.env`
- **THEN** the API answers HTTP requests on `localhost:8000`

### Requirement: Database health endpoint
`GET /health/db` SHALL load data through every model and return status `ok` with the row count of each app table, keyed by table name. It SHALL return counts only, never row contents.

#### Scenario: Seeded database
- **WHEN** `GET /health/db` is called against the freshly seeded database
- **THEN** the response is HTTP 200 with status `ok`, a count for each of the 11 app tables, `12` for `products` and `8` for `neighborhoods`

#### Scenario: No personal data in the response
- **WHEN** `GET /health/db` is called
- **THEN** the response body contains no customer name, phone or address

### Requirement: Health endpoint reports an unreachable database
When the database cannot be reached or a model fails to load, `GET /health/db` SHALL return HTTP 503 with status `unavailable`. The response SHALL NOT contain the connection URL, credentials or the driver's error text; the error SHALL be logged instead.

#### Scenario: Database down
- **WHEN** `GET /health/db` is called while PostgreSQL is not reachable
- **THEN** the response is HTTP 503 with status `unavailable`, and its body does not contain the database password or host
