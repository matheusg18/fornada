# Spec Delta

## ADDED Requirements

### Requirement: Default daily capacity setting
`APP__DAILY_CAPACITY_KG` SHALL set the oven capacity in kg for dates without a capacity override. It SHALL accept a decimal number greater than zero and default to `15`. A value that is not a positive number SHALL make settings loading fail with an error that names `APP__DAILY_CAPACITY_KG`.

#### Scenario: Default capacity
- **WHEN** `APP__DAILY_CAPACITY_KG` is not set
- **THEN** the default daily capacity is exactly 15 kg

#### Scenario: Override
- **WHEN** `APP__DAILY_CAPACITY_KG=20.5`
- **THEN** the default daily capacity is exactly 20.5 kg

#### Scenario: Invalid capacity
- **WHEN** `APP__DAILY_CAPACITY_KG=0`
- **THEN** settings loading fails with an error that names `APP__DAILY_CAPACITY_KG`
