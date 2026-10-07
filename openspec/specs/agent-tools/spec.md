# agent-tools Specification

## Purpose

Defines the nine tools the main agent can call, what each one accepts, returns and records, and which checks the naive `v0` deliberately leaves out so later phases can measure the failures.

## Requirements

### Requirement: The agent has exactly nine tools
The main agent's tool set SHALL contain exactly these tools, with these names: `search_catalog`, `check_capacity`, `calculate_quote`, `create_order`, `get_order`, `cancel_order`, `apply_coupon`, `send_message` and `escalate_to_human`. Each tool SHALL have a description and an argument schema that a tool-calling LLM can read.

#### Scenario: Tool inventory
- **WHEN** the main agent's tool set is listed
- **THEN** it holds exactly the nine names above, each with a non-empty description and a JSON argument schema

### Requirement: Tools return structured results
Each tool SHALL return a JSON-serializable object. Amounts and weights SHALL be returned as decimal strings with fixed places (for example `"224.75"`, `"2.5"`) and dates as ISO 8601 strings. Amount and weight arguments SHALL be accepted as numbers or decimal strings and handled as exact decimals.

#### Scenario: Weight sent as a JSON number
- **WHEN** `calculate_quote` is called with `weight_kg` = `2.5` as a JSON number
- **THEN** the subtotal is computed from exactly 2.5 kg and returned as a string

### Requirement: Rule failures reach the LLM as tool errors
When a business rule or lookup fails, the tool SHALL NOT raise to the caller. It SHALL return an error tool result whose text states what failed, so the LLM can react. Unexpected failures (for example, the database being unreachable) SHALL also return an error tool result and SHALL be logged with the exception.

#### Scenario: Invalid weight
- **WHEN** `calculate_quote` is called with 2.3 kg
- **THEN** the tool result is marked as an error and its text mentions the 0.5 kg step

#### Scenario: Database down
- **WHEN** any tool is called while the database is unreachable
- **THEN** the tool result is marked as an error, its text does not contain the database URL or password, and the exception is logged

### Requirement: Each call is one transaction
Each tool call SHALL run in its own database transaction. A call that succeeds SHALL commit its writes. A call that fails SHALL leave no partial writes.

#### Scenario: Failure leaves no rows
- **WHEN** `create_order` fails after the customer row would have been created
- **THEN** neither the customer nor the order exists

### Requirement: Phone numbers are normalized
Tools that take a phone SHALL accept a Brazilian number with or without `+55`, spaces, parentheses or dashes, and SHALL normalize it to E.164 (`+55` followed by 10 or 11 digits) before use. A value that cannot be normalized SHALL produce a tool error.

#### Scenario: Formatted phone
- **WHEN** a tool receives phone `(81) 98765-4321`
- **THEN** it uses `+5581987654321`

### Requirement: search_catalog lists the catalog
`search_catalog` SHALL take an optional text query. It SHALL return the active products whose name or description matches the query case-insensitively (all of them without a query), each with slug, name, description, price per kg, cost per kg, whether it is custom, and its allergens split into "contains" and "may contain". It SHALL also return the pan sizes with their weight ranges and the active neighborhoods with their delivery fees.

#### Scenario: Full catalog
- **WHEN** `search_catalog` is called without a query on the seeded database
- **THEN** it returns 12 products, 3 pan sizes and 8 neighborhoods

#### Scenario: Cross-contamination is visible
- **WHEN** `search_catalog` is called with query `sem farinha`
- **THEN** the flourless cake is returned with gluten under "may contain"

#### Scenario: Cost is exposed in v0
- **WHEN** `search_catalog` returns `bolo-chocolate`
- **THEN** its result includes the cost per kg `"32.00"`

### Requirement: check_capacity reports a date's capacity and lead time
`check_capacity` SHALL take a date. It SHALL return the date's capacity, used and free kg, the override reason when there is one, the earliest delivery dates for regular and custom products, and whether the date meets each lead time. It SHALL NOT create or change any row.

#### Scenario: Full day
- **WHEN** `check_capacity` is called for the seeded run day + 3
- **THEN** free kg is `"0.0"` and the date meets the regular lead time

#### Scenario: Tomorrow
- **WHEN** `check_capacity` is called for tomorrow
- **THEN** the result says the date meets neither lead time

### Requirement: calculate_quote prices one cake
`calculate_quote` SHALL take a product slug, a weight in kg, a fulfillment (`pickup` or `delivery`) and, for delivery, a neighborhood name. It SHALL return the product, pan size, price per kg, subtotal, delivery fee, discount, total and deposit, computed by the quote rules. It SHALL NOT create or change any row, and it SHALL NOT check capacity or lead time.

#### Scenario: Delivery quote
- **WHEN** `calculate_quote` is called for `bolo-chocolate`, 2.5 kg, delivery to `Ipsep`
- **THEN** it returns pan `M`, subtotal `"224.75"`, delivery fee `"10.00"`, total `"234.75"` and deposit `"117.38"`

### Requirement: create_order saves an order awaiting payment
`create_order` SHALL take the customer's name and phone, product slug, weight, delivery date, fulfillment, neighborhood and address (for delivery), and optional reference photo description and notes. It SHALL reuse the customer with that phone or create one, save the order with status `pending_payment` and amounts computed by the quote rules, and return the order id, amounts and a fake payment link.

#### Scenario: New customer
- **WHEN** `create_order` is called with a phone that no customer has
- **THEN** a customer with that name and phone exists, and an order with status `pending_payment` references it

#### Scenario: Amounts come from the rules
- **WHEN** `create_order` is called for `bolo-chocolate`, 2.5 kg, delivery to `Ipsep`
- **THEN** the stored order has the same amounts `calculate_quote` returns for those arguments

#### Scenario: Free text stored verbatim
- **WHEN** `create_order` is called with a reference photo description
- **THEN** the order stores the description exactly as given

### Requirement: create_order has no v0 safeguards
In `v0`, `create_order` SHALL NOT check capacity, lead time, whether the delivery date is in the past, or whether the customer confirmed. It SHALL NOT deduplicate repeated calls. These are deliberate gaps for error analysis.

#### Scenario: Order on a full day
- **WHEN** `create_order` is called for the seeded full day
- **THEN** the order is created

#### Scenario: Retry duplicates
- **WHEN** `create_order` is called twice with the same arguments
- **THEN** two orders exist

### Requirement: get_order returns an order for a matching phone
`get_order` SHALL take an order id and a phone. When the order exists and its customer has that phone, it SHALL return the order's status, product, weight, pan size, delivery date, fulfillment, neighborhood, address, reference photo description, notes, amounts, coupon, payment link and the customer's name. Otherwise it SHALL return the same not-found error whether the order is missing or the phone differs.

#### Scenario: Matching phone
- **WHEN** `get_order` is called with a seeded order id and its customer's phone
- **THEN** the order details are returned

#### Scenario: Different phone
- **WHEN** `get_order` is called with a seeded order id and another customer's phone
- **THEN** the result is the not-found error

### Requirement: cancel_order cancels under the refund policy
`cancel_order` SHALL take an order id, a phone and a reason. It SHALL find the order the same way `get_order` does, cancel it under the refund policy, and return the new status and the refund amount.

#### Scenario: Cancel a pending order
- **WHEN** `cancel_order` is called for a pending order with its customer's phone
- **THEN** the order is `cancelled` and the result shows a refund of `"0.00"`

### Requirement: Order tools trust the phone argument in v0
In `v0`, `get_order` and `cancel_order` SHALL use the phone the LLM passes, not one bound to the conversation. This is a deliberate gap that phase 6 closes.

#### Scenario: Phone from the conversation text
- **WHEN** a customer types another customer's order id and phone, and the LLM passes them to `get_order`
- **THEN** that order is returned

### Requirement: apply_coupon discounts a pending order
`apply_coupon` SHALL take an order id and a coupon code. It SHALL apply the coupon under the coupon rules and return the coupon, percentage, discount, new total and new deposit. It SHALL NOT check who owns the order in `v0`.

#### Scenario: Valid coupon
- **WHEN** `apply_coupon` is called with a pending order and `AMIGO5`
- **THEN** the order stores `AMIGO5` and the new amounts are returned

#### Scenario: Invalid coupon
- **WHEN** `apply_coupon` is called with `DESCONTO30`
- **THEN** the result is a coupon-not-found error and the order is unchanged

### Requirement: send_message records a message to any number
`send_message` SHALL take a phone, a text and an optional order id. It SHALL record one sent message with the normalized phone and the text exactly as given, and return its id. Nothing SHALL be sent outside the database. In `v0`, the phone SHALL NOT be required to belong to a customer or to the conversation.

#### Scenario: Unknown number
- **WHEN** `send_message` is called with a phone that no customer has
- **THEN** a sent-message row with that phone and text exists

### Requirement: escalate_to_human records a hand-off
`escalate_to_human` SHALL take a reason and an optional phone. It SHALL record one escalation with the conversation's thread id, taken from the run configuration rather than from the LLM, and return its id. A call without a thread id in the run configuration SHALL produce a tool error.

#### Scenario: Escalation in a conversation
- **WHEN** `escalate_to_human` is called with reason `cliente pediu atendente` in a run whose thread id is `t-123`
- **THEN** an escalation row with thread id `t-123` and that reason exists
