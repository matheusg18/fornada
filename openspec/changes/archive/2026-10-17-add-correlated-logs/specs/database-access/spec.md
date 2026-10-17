# Spec Delta

## ADDED Requirements

### Requirement: Database errors carry no parameter values
Errors raised by the database layer SHALL NOT include the values bound to the failing statement, so a logged database error cannot carry customer names, phones or addresses. The statement text MAY still appear.

#### Scenario: Constraint violation on a customer insert
- **WHEN** inserting a customer with phone `+5581999991234` and name `Maria Teste` fails with a database error, and the error is logged with its traceback
- **THEN** neither the error message nor the logged traceback contains `5581999991234` or `Maria Teste`
