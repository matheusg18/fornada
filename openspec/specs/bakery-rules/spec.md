# bakery-rules Specification

## Purpose

Defines the bakery's business rules as the API enforces them in code: pan size, quotes and deposits, lead time, daily capacity, coupons and cancellation refunds. Tools and later guardrails rely on these rules instead of on the LLM's arithmetic.

## Requirements

### Requirement: Amounts are exact and rounded half up
Every amount the rules compute SHALL be an exact decimal in BRL. Any result with more than two decimal places SHALL be rounded half up to two places. Amounts SHALL NOT pass through floating point.

#### Scenario: Subtotal rounding
- **WHEN** a price per kg of `89.90` is multiplied by a weight of `2.5` kg
- **THEN** the subtotal is exactly `224.75`

### Requirement: Order weight is valid
An order's weight SHALL be a multiple of 0.5 kg between the smallest pan's minimum and the largest pan's maximum, inclusive (1.0 to 6.0 kg with the seeded pans). Any other weight SHALL be rejected with an error that states the valid range and step.

#### Scenario: Off-step weight
- **WHEN** a quote is requested for 2.3 kg
- **THEN** it fails with an error that mentions the 0.5 kg step

#### Scenario: Weight above the largest pan
- **WHEN** a quote is requested for 8 kg
- **THEN** it fails with an error that states the 1.0 to 6.0 kg range

### Requirement: Pan size follows from the weight
The pan size SHALL be the smallest pan whose weight range contains the order's weight. A weight on the boundary between two pans SHALL use the smaller pan.

#### Scenario: Boundary weight
- **WHEN** the weight is 2.0 kg
- **THEN** the pan size is `P`

#### Scenario: Middle of a range
- **WHEN** the weight is 4.5 kg
- **THEN** the pan size is `G`

### Requirement: Quote uses catalog price and delivery fee
A quote SHALL use the product's current price per kg. Subtotal SHALL be price per kg × weight. The delivery fee SHALL be the neighborhood's fee for delivery and `0.00` for pickup. Total SHALL be subtotal + delivery fee − discount, with a discount of `0.00` before any coupon.

#### Scenario: Delivery quote
- **WHEN** a quote is requested for `bolo-chocolate`, 2.5 kg, delivery to a neighborhood with a fee of `10.00`
- **THEN** the subtotal is `224.75`, the delivery fee `10.00` and the total `234.75`

#### Scenario: Pickup quote
- **WHEN** the same quote is requested for pickup
- **THEN** the delivery fee is `0.00` and the total equals the subtotal

### Requirement: Deposit is half the total
The deposit SHALL be half of the total, rounded half up to two decimal places.

#### Scenario: Odd cent total
- **WHEN** the total is `234.75`
- **THEN** the deposit is `117.38`

### Requirement: Quotes need an active product and neighborhood
A quote SHALL fail when the product does not exist or is inactive. A delivery quote SHALL fail when no neighborhood is given, or when it does not exist or is inactive. A pickup quote SHALL ignore the neighborhood.

#### Scenario: Unknown product
- **WHEN** a quote is requested for product `bolo-de-pistache`
- **THEN** it fails with a product-not-found error

#### Scenario: Delivery outside the area
- **WHEN** a delivery quote is requested for neighborhood `Olinda`
- **THEN** it fails with an error that names the neighborhoods served

### Requirement: Lead time depends on the product
Today SHALL be the current calendar date in the application time zone. The earliest delivery date SHALL be today + 2 days for regular products and today + 5 days for custom products.

#### Scenario: Regular product
- **WHEN** today is 2026-10-07
- **THEN** the earliest delivery date for a regular product is 2026-10-09

#### Scenario: Custom product
- **WHEN** today is 2026-10-07
- **THEN** the earliest delivery date for a custom product is 2026-10-12

#### Scenario: Late evening in UTC
- **WHEN** it is 22:00 on 2026-10-07 in `America/Sao_Paulo` (01:00 UTC on 2026-10-08)
- **THEN** today is 2026-10-07

### Requirement: Daily capacity
A date's capacity SHALL be its capacity override when one exists, and the configured default daily capacity otherwise. Used capacity SHALL be the sum of the weights of the date's orders that are not cancelled. Free capacity SHALL be capacity minus used, and never below zero.

#### Scenario: Full day
- **WHEN** capacity is checked for the seeded full day (run day + 3)
- **THEN** capacity is 15.0 kg, used is 15.0 kg and free is 0.0 kg

#### Scenario: Holiday
- **WHEN** capacity is checked for December 25
- **THEN** capacity is 0.0 kg and the override reason is returned

#### Scenario: Cancelled orders free capacity
- **WHEN** a 2.0 kg order on a date is cancelled
- **THEN** that date's free capacity grows by 2.0 kg

### Requirement: Coupon validity
A coupon SHALL be valid only when its code exists (compared case-insensitively), it is active, today is within its validity window (inclusive), its usage is below its usage limit when it has one, and its percentage is between 1 and 10. Usage SHALL be the number of non-cancelled orders that reference it. Each failure SHALL have its own error.

#### Scenario: Valid coupon in lowercase
- **WHEN** coupon `amigo5` is checked
- **THEN** it is valid with 5% off

#### Scenario: Expired coupon
- **WHEN** coupon `PASCOA10` is checked
- **THEN** it fails with an expired-coupon error

#### Scenario: Used-up coupon
- **WHEN** coupon `PRIMEIRA10` is checked after its usage limit was reached
- **THEN** it fails with a used-up-coupon error

#### Scenario: Percentage above the cap
- **WHEN** a coupon with 30% off exists, is active and is in its window
- **THEN** it fails with an error, and no discount is granted

### Requirement: Coupon discount applies to the subtotal
A coupon SHALL apply only to an order with status `pending_payment` that has no coupon yet. The discount SHALL be the subtotal × percentage / 100, rounded half up to two places. Applying it SHALL store the coupon code and discount on the order and recompute the total and deposit by the quote rule. The delivery fee SHALL NOT be discounted.

#### Scenario: Five percent off
- **WHEN** coupon `AMIGO5` is applied to a pending order with subtotal `224.75` and delivery fee `10.00`
- **THEN** the discount is `11.24`, the total `223.51` and the deposit `111.76`

#### Scenario: Second coupon refused
- **WHEN** a coupon is applied to an order that already has one
- **THEN** it fails and the order is unchanged

#### Scenario: Confirmed order
- **WHEN** a coupon is applied to an order with status `confirmed`
- **THEN** it fails and the order is unchanged

### Requirement: Cancellation refund policy
Only orders with status `pending_payment` or `confirmed` SHALL be cancellable. A `pending_payment` order SHALL be refunded `0.00`, because nothing was paid. A `confirmed` order SHALL be refunded its deposit when the delivery date is at least 2 days after today, and `0.00` otherwise. Cancelling SHALL set the status, cancellation time, refund amount and reason.

#### Scenario: Confirmed order with notice
- **WHEN** a confirmed order with a deposit of `117.38` and delivery in 5 days is cancelled
- **THEN** its status is `cancelled` and the refund is `117.38`

#### Scenario: Confirmed order without notice
- **WHEN** a confirmed order with delivery tomorrow is cancelled
- **THEN** its status is `cancelled` and the refund is `0.00`

#### Scenario: Pending order
- **WHEN** a pending-payment order is cancelled
- **THEN** its status is `cancelled` and the refund is `0.00`

#### Scenario: Delivered order
- **WHEN** a delivered order is cancelled
- **THEN** it fails and the order is unchanged
