# Spec Delta

## ADDED Requirements

### Requirement: Intent and complication catalogs
The simulator SHALL provide five intents (`retirada`, `entrega`, `orcamento`, `duvida_cardapio`, `pos_pedido`) and five complications (`nenhuma`, `data_lotada`, `troca_sabor`, `ferramenta_fora`, `tamanho_ambiguo`), each with a stable identifier and a Brazilian Portuguese text for the customer. Like persona prompts, these texts SHALL NOT mention the attendant's tools, its prompt or the project's evaluation.

#### Scenario: Catalog contents
- **WHEN** the intent and complication catalogs are listed
- **THEN** each has five entries with distinct identifiers

#### Scenario: Texts read as a customer
- **WHEN** any intent or complication text is checked
- **THEN** it contains no word that reveals tools, prompts, tests or simulation

### Requirement: A matrix cell defines the customer's goal
A matrix cell SHALL be one persona, one intent and one complication. Its goal SHALL combine the intent's text with the complication's text, and SHALL be deterministic for the cell. The persona's description SHALL stay unchanged, and the cheater's legacy goals SHALL NOT be used in matrix cells. The control complication `nenhuma` SHALL add nothing to the intent's text.

#### Scenario: Same cell, same goal
- **WHEN** the goal of cell (`indecisa`, `entrega`, `troca_sabor`) is built twice
- **THEN** both goals are the same text, containing the delivery intent and the flavor change

#### Scenario: Control cell
- **WHEN** the goal of a cell with complication `nenhuma` is built
- **THEN** it equals the intent's text

#### Scenario: Cheater in the matrix
- **WHEN** the goal of any cell with persona `malandro` is built
- **THEN** it is built from the cell's intent and complication and contains none of the cheater's legacy goals

### Requirement: Complications that depend on the seed or the API
The `data_lotada` complication SHALL ask for the date 3 days from today, which the dev seed fills, and SHALL tell the customer to accept another date if it is refused. The `ferramenta_fora` complication SHALL NOT mention any outage to the customer: its goal SHALL ask for a specific date, and the outage SHALL come only from the API running in chaos mode.

#### Scenario: Full date
- **WHEN** the goal of a `data_lotada` cell is built
- **THEN** it asks for a cake for 3 days from today

#### Scenario: Tool down is not scripted
- **WHEN** the goal of a `ferramenta_fora` cell is built
- **THEN** it names a delivery date and says nothing about a failure or an unavailable system

### Requirement: The matrix batch plans each cell once
A matrix batch SHALL plan every persona × intent × complication cell exactly once (125 cells in total). Cells SHALL be ordered so that every persona appears once before any persona appears again, so a batch cut short stays balanced across personas.

#### Scenario: Full matrix
- **WHEN** the full matrix is planned
- **THEN** 125 distinct cells are planned and each persona appears in 25 of them

#### Scenario: Interleaved order
- **WHEN** the first five planned cells are listed
- **THEN** they cover the five personas

### Requirement: The matrix batch keeps the outage cells apart
By default, a matrix batch SHALL run the 100 cells whose complication is not `ferramenta_fora`. The batch SHALL accept a list of complications and then run only the cells with those complications. The `ferramenta_fora` cells SHALL run only when that complication is named, so they never share an API process with cells that need a working `check_capacity`.

#### Scenario: Default matrix batch
- **WHEN** a matrix batch is launched without a complication list
- **THEN** 100 cells are planned and none has complication `ferramenta_fora`

#### Scenario: Outage cells only
- **WHEN** a matrix batch is launched with the complication list `ferramenta_fora`
- **THEN** 25 cells are planned, all with complication `ferramenta_fora`

#### Scenario: Unknown complication
- **WHEN** a matrix batch is launched with a complication that is not in the catalog
- **THEN** the batch fails before any conversation starts, naming the unknown identifier

### Requirement: A matrix batch can resume a run
When a matrix batch is launched with the id of an existing run, it SHALL append to that run's file and SHALL skip every planned cell that the file already records with outcome `completed` or `max_turns`. A cell recorded only with `api_error` or `simulator_error` SHALL be run again. When a cell appears more than once in a run file, its last line SHALL be the one that counts.

#### Scenario: Resume after an interruption
- **WHEN** a 100-cell batch stops after 40 finished cells and is launched again with the same run id
- **THEN** only the remaining 60 cells run, and the run file ends with 100 cells that each count once

#### Scenario: Failed cell is retried
- **WHEN** a run file records a cell with outcome `api_error` and the batch resumes that run
- **THEN** that cell runs again and its new line is the one that counts

#### Scenario: Outage cells join the same run
- **WHEN** the 100 default cells finished in a run and the batch resumes it with the complication list `ferramenta_fora`
- **THEN** the 25 outage cells are appended to the same run file

### Requirement: Matrix transcripts record their cell
A matrix transcript SHALL record its `intent_id` and `complication_id` with the other transcript fields. Transcripts of the persona batch SHALL record both as null, and transcripts written before this change SHALL still be readable.

#### Scenario: Matrix line
- **WHEN** a matrix conversation for cell (`apressada`, `retirada`, `data_lotada`) finishes
- **THEN** its JSON line has `persona_id` `apressada`, `intent_id` `retirada` and `complication_id` `data_lotada`

#### Scenario: Old run file
- **WHEN** a run file written before this change is read
- **THEN** every transcript loads with `intent_id` and `complication_id` null

### Requirement: Matrix batches are summarized per axis
When a matrix batch finishes, the simulator SHALL print its outcome counts per complication and per intent. The notebook SHALL be able to show the same summary for a matrix run file.

#### Scenario: Batch printout
- **WHEN** a matrix batch of 100 cells finishes
- **THEN** the printout shows one row per complication and one row per intent, each with its outcome counts
