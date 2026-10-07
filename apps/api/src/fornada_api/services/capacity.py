"""Lead time and daily oven capacity."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from fornada_api.services.clock import Clock
from fornada_api.services.money import round_weight
from fornada_api.services.ports import CapacityRepository

# "48 hours" and "5 days", counted in calendar days: delivery dates have no time.
REGULAR_LEAD_DAYS = 2
CUSTOM_LEAD_DAYS = 5


def earliest_delivery_date(today: dt.date, *, is_custom: bool) -> dt.date:
    days = CUSTOM_LEAD_DAYS if is_custom else REGULAR_LEAD_DAYS
    return today + dt.timedelta(days=days)


@dataclass(frozen=True)
class CapacityReport:
    date: dt.date
    capacity_kg: Decimal
    used_kg: Decimal
    free_kg: Decimal
    override_reason: str | None
    earliest_regular_date: dt.date
    earliest_custom_date: dt.date
    meets_regular_lead_time: bool
    meets_custom_lead_time: bool


class CapacityService:
    def __init__(
        self, capacity: CapacityRepository, clock: Clock, default_capacity_kg: Decimal
    ) -> None:
        self.capacity = capacity
        self.clock = clock
        self.default_capacity_kg = default_capacity_kg

    async def check(self, day: dt.date) -> CapacityReport:
        override = await self.capacity.get_override(day)
        capacity = override.capacity_kg if override else self.default_capacity_kg
        used = await self.capacity.used_kg(day)
        today = self.clock.today()
        regular = earliest_delivery_date(today, is_custom=False)
        custom = earliest_delivery_date(today, is_custom=True)
        return CapacityReport(
            date=day,
            capacity_kg=round_weight(capacity),
            used_kg=round_weight(used),
            free_kg=round_weight(max(capacity - used, Decimal(0))),
            override_reason=override.reason if override else None,
            earliest_regular_date=regular,
            earliest_custom_date=custom,
            meets_regular_lead_time=day >= regular,
            meets_custom_lead_time=day >= custom,
        )
