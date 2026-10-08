# Spec Delta

## MODIFIED Requirements

### Requirement: Models never change the schema
The schema script SHALL remain the only source of app table definitions. Starting the API or importing the models SHALL NOT create, alter or drop any app table. The LangGraph checkpointer's tables are the one exception: the checkpointer library creates and migrates them in the same database, and SHALL NOT touch any app table.

#### Scenario: Startup against the seeded database
- **WHEN** the API starts and stops against the seeded database
- **THEN** the set of app tables and their columns is unchanged

#### Scenario: Checkpointer tables
- **WHEN** the first conversation turn runs against a database without checkpointer tables
- **THEN** the checkpointer's tables exist afterwards, and the app tables and their columns are unchanged
