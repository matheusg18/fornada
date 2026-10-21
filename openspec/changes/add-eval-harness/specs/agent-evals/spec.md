# Spec Delta

## Purpose

Defines the offline evaluation suite for the attendant: the golden dataset, how each case runs against the real agent in isolation, the deterministic and trajectory checks derived from the phase 3 failure taxonomy, and the gate (pass^3, minimum rate, cost and latency) with its report.

## ADDED Requirements

### Requirement: Every golden case traces back to an observed failure
Each golden case SHALL name its taxonomy category, the phase 3 conversation it reproduces (by its number in the open codes file), the checks that apply to it and whether it is critical. A case without a category, a source or at least one check SHALL make the dataset fail to load.

#### Scenario: Complete case
- **WHEN** the dataset is loaded and a case has category `DATE`, source `#3`, checks `no_past_date` and critical `true`
- **THEN** the case loads with those four values

#### Scenario: Case without a source
- **WHEN** a case in the dataset has no source conversation
- **THEN** loading fails with an error naming the case

#### Scenario: Unknown check
- **WHEN** a case lists a check the suite does not define
- **THEN** loading fails with an error naming the case and the check

### Requirement: Case dates are relative to the run day
A case's customer turns SHALL write dates as offsets from the run day, and the suite SHALL render them in Brazilian Portuguese form (`DD/MM`, or a weekday name) when the case runs. The run day SHALL be the day the case's seed was loaded.

#### Scenario: Day plus three
- **WHEN** a case says "quero um bolo para {d+3:dd/mm}" and the run day is 2026-10-21
- **THEN** the customer turn sent to the agent reads "quero um bolo para 24/10"

#### Scenario: Full day matches the seed
- **WHEN** a case asks for the run day plus 3
- **THEN** `check_capacity` for that date reports no free kg, as the seed fills it

### Requirement: Each case runs in isolation
Each run of a case SHALL see the dev schema and seed as freshly loaded, and nothing else: no order, message or escalation written by another case or by the dev environment. When the run ends, whatever it wrote SHALL be gone. The suite SHALL NOT read or write the app's own tables.

#### Scenario: Orders do not leak
- **WHEN** one case creates an order for the run day plus 8 and another case then checks capacity for that date
- **THEN** the second case sees the seed's free kg for that date

#### Scenario: Dev data untouched
- **WHEN** the suite finishes
- **THEN** the dev database's orders, messages and escalations are the same as before the run

### Requirement: The agent runs as it ships
A case SHALL run the attendant's graph with its system prompt, the configured model and provider, and the nine tools with their business rules, unchanged. The tools' clock SHALL be fixed to the run day. Each run SHALL record the prompt version and the model.

#### Scenario: Prompt version recorded
- **WHEN** a case runs
- **THEN** its result records the same prompt version the API reports for the current prompt file

#### Scenario: No change to the agent
- **WHEN** the suite is added
- **THEN** the system prompt, the tools and the graph are unchanged

### Requirement: Outage cases make `check_capacity` fail
A case marked as an outage SHALL make every `check_capacity` call fail with the same error a real failure returns. Other tools SHALL work. Cases not marked as an outage SHALL have no injected fault.

#### Scenario: Outage case
- **WHEN** an outage case runs and the agent calls `check_capacity` twice
- **THEN** both calls return the tool's generic error

#### Scenario: Normal case
- **WHEN** a case without the outage mark runs
- **THEN** no tool call is delayed or failed by fault injection

### Requirement: A run records the conversation with its tool calls
A run SHALL record every customer turn and every assistant turn. Each assistant turn SHALL list its tool calls in order, with the tool's name, its arguments, and its result or error. It SHALL also record the turn's latency, its token counts and its cost at the configured prices. A turn that raises SHALL end the run as failed, with the error recorded.

#### Scenario: Turn with two tools
- **WHEN** the agent answers a turn after calling `check_capacity` and then `calculate_quote`
- **THEN** that assistant turn lists both calls in that order, each with its arguments and result

#### Scenario: Failing turn
- **WHEN** the model provider fails during a case's second turn
- **THEN** the run is recorded as failed, with the error, and the suite goes on to the next case

### Requirement: Checks are deterministic and apply only where listed
Every check in this capability SHALL be computed from the recorded conversation alone, with no LLM call. A check SHALL run only on the cases that list it. A check whose condition never occurs in the conversation SHALL pass.

#### Scenario: Same conversation, same verdict
- **WHEN** a check is computed twice on the same recorded conversation
- **THEN** both verdicts are equal

#### Scenario: Nothing to check
- **WHEN** a case lists the order capacity check and the agent never calls `create_order`
- **THEN** that check passes

### Requirement: No date before the run day
The `no_past_date` check SHALL fail when any `check_capacity` `date` or `create_order` `delivery_date` argument is earlier than the run day. (DATE)

#### Scenario: Wrong year
- **WHEN** the run day is 2026-10-21 and the agent calls `check_capacity` with 2025-10-27
- **THEN** the check fails, naming the argument and the date

#### Scenario: Future date
- **WHEN** every date argument is the run day plus 6
- **THEN** the check passes

### Requirement: Orders only on an open date
The `order_on_open_date` check SHALL fail when `create_order` is called for a date unless an earlier successful `check_capacity` for that date in the same run showed free kg at least the order's weight and the lead time met for the product (custom or regular). (CAPACITY)

#### Scenario: Short day
- **WHEN** `check_capacity` for a date shows 0.5 free kg and the agent then creates a 2 kg order for it
- **THEN** the check fails

#### Scenario: Order without a check
- **WHEN** the agent creates an order for a date it never checked
- **THEN** the check fails

#### Scenario: Valid order
- **WHEN** `check_capacity` showed 15 free kg with the regular lead time met, and the agent creates a 2 kg regular order for that date
- **THEN** the check passes

### Requirement: No order after an outage
The `no_order_after_outage` check SHALL fail when `create_order` is called for a date whose latest `check_capacity` call in the run returned an error. (OUTAGE)

#### Scenario: Order despite the outage
- **WHEN** `check_capacity` for a date failed and the agent then creates an order for that date
- **THEN** the check fails

#### Scenario: Outage handled
- **WHEN** `check_capacity` failed and the agent escalates without creating an order
- **THEN** the check passes

### Requirement: Prices come from the tools in the same turn
The `price_from_tool` check SHALL fail when an assistant reply states an amount in reais that no `calculate_quote`, `create_order` or `apply_coupon` result of the same turn contains as one of its money fields. (PRICE)

#### Scenario: Price by hand
- **WHEN** a reply says "fica R$ 159,60" and no tool in that turn returned 159.60
- **THEN** the check fails, naming the amount

#### Scenario: Price from the quote
- **WHEN** a reply says the total is R$ 194,80 and that turn's `calculate_quote` returned total 194.80
- **THEN** the check passes

### Requirement: Escalations carry a phone
The `escalation_has_phone` check SHALL fail when `escalate_to_human` is called without a phone or with an empty one. (ESCALATION)

#### Scenario: Null phone
- **WHEN** the agent calls `escalate_to_human` with no phone
- **THEN** the check fails

#### Scenario: Phone given
- **WHEN** the agent calls `escalate_to_human` with the phone the customer gave
- **THEN** the check passes

### Requirement: Suggested weight follows the serving rule
For a case with a party size, the `serving_rule` check SHALL expect 150 g per person, rounded up to the next 0.5 kg. It SHALL fail when a `calculate_quote` or `create_order` uses another weight, or when the run has no quote and no reply states the expected weight. (SIZE)

#### Scenario: Forty people
- **WHEN** the case's party size is 40 and the agent quotes 6 kg
- **THEN** the check passes

#### Scenario: Guessed weight
- **WHEN** the case's party size is 40 and the agent quotes 3 kg
- **THEN** the check fails, naming 3 kg and the expected 6 kg

### Requirement: Order only after the quote was shown
The `confirmation_before_order` check SHALL fail when `create_order` is called in a turn unless an earlier turn called `calculate_quote` with the same product and weight and its reply stated that quote's total.

#### Scenario: Quote and order in one turn
- **WHEN** the agent calls `calculate_quote` and `create_order` in the same turn, with no earlier quote
- **THEN** the check fails

#### Scenario: Customer confirmed
- **WHEN** turn 2's reply stated the quote's total and the agent creates the order in turn 3
- **THEN** the check passes

### Requirement: A flavor change is quoted again
For a case that names the turn where the customer changes flavor and the new product, the `requote_after_change` check SHALL fail when a reply from that turn on states an amount in reais before a `calculate_quote` for the new product was called.

#### Scenario: Old price reused
- **WHEN** the customer switches to `bolo-limao` in turn 3 and the turn 3 reply states a total with no `calculate_quote` for `bolo-limao`
- **THEN** the check fails

#### Scenario: New quote
- **WHEN** turn 3 calls `calculate_quote` for `bolo-limao` and its reply states that total
- **THEN** the check passes

### Requirement: `send_message` is not a channel to the owner
The `no_message_to_owner` check SHALL fail when a `send_message` text addresses the shop owner, that is, names the owner ("dono", "dona", "proprietário", "proprietária") as its recipient. (MESSAGE)

#### Scenario: Message for the owner
- **WHEN** the agent sends "Olá, dono! A cliente quer um desconto de 10%" to the customer's phone
- **THEN** the check fails

#### Scenario: Order confirmation
- **WHEN** the agent sends "Olá, Maria! Recebemos seu pedido #12" to the customer's phone
- **THEN** the check passes

### Requirement: Critical cases gate on pass^3
Each critical case SHALL run 3 times, each run in its own isolation. A critical case SHALL pass only when all 3 runs pass every check it lists. The gate SHALL fail when any critical case fails.

#### Scenario: One flaky run
- **WHEN** a critical case passes in 2 runs and fails one check in the third
- **THEN** the case fails and the gate fails

#### Scenario: All three pass
- **WHEN** a critical case passes every check in its 3 runs
- **THEN** the case passes

### Requirement: Non-critical cases gate on a minimum rate
Each non-critical case SHALL run once. The gate SHALL fail when the share of non-critical cases that pass every check they list is below the configured minimum rate.

#### Scenario: Below the minimum
- **WHEN** the minimum is 80% and 7 of 10 non-critical cases pass
- **THEN** the gate fails and the report shows 70% against 80%

### Requirement: Cost and latency are checks
The gate SHALL fail when the mean cost per conversation run exceeds its configured ceiling, or when the 95th percentile of turn latency across all runs exceeds its configured ceiling. The report SHALL show both values next to their ceilings.

#### Scenario: Too expensive
- **WHEN** the mean cost per run is US$ 0.06 and the ceiling is US$ 0.05
- **THEN** the gate fails and the report names the cost check

### Requirement: The run report names what failed
After a run, the suite SHALL write a Markdown report and a JSON summary. They SHALL list each case with its category, its critical mark, its runs passed out of runs made, and for each failed run the checks that failed with their reasons. They SHALL also give the critical and non-critical results, the cost, the p95 latency, the prompt version and the model.

#### Scenario: Failed check in the report
- **WHEN** case `date-wrong-year-27-10` fails `no_past_date` in one run
- **THEN** the report lists that case with 2/3 runs passed and the `no_past_date` reason for the failed run

### Requirement: Variance across repeated suite runs
Given the results of two or more suite runs on the same prompt version and model, the reporter SHALL list the cases whose verdict differed between runs and the share of cases that differed.

#### Scenario: A case flips
- **WHEN** a case passes in the first suite run and fails in the second, on the same prompt version
- **THEN** the variance section lists it and counts it in the share of cases that differed

### Requirement: The suite stays offline and opt-in
The suite SHALL send no result or usage telemetry to third parties: only the agent's own model provider receives calls. The suite SHALL NOT run as part of an app's `task check`, and app code SHALL NOT import the evaluation library.

#### Scenario: Telemetry off
- **WHEN** the suite runs
- **THEN** no request goes to the evaluation library's telemetry or results service

#### Scenario: API check unchanged
- **WHEN** `uv run task check` runs in `apps/api`
- **THEN** no golden case runs and no model is called
