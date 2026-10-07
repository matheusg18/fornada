"""The current day and time for the business rules, injectable so tests can fix them."""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def today(self) -> dt.date:
        """The current calendar date in the bakery's time zone."""
        ...

    def now(self) -> dt.datetime:
        """The current time, time-zone aware."""
        ...


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass(frozen=True)
class SystemClock:
    timezone: ZoneInfo
    utcnow: Callable[[], dt.datetime] = field(default=_utcnow)

    def today(self) -> dt.date:
        return self.utcnow().astimezone(self.timezone).date()

    def now(self) -> dt.datetime:
        return self.utcnow().astimezone(self.timezone)


@dataclass(frozen=True)
class FixedClock:
    """Always the same day, at noon in the given time zone."""

    day: dt.date
    timezone: ZoneInfo = field(default=ZoneInfo("America/Sao_Paulo"))

    def today(self) -> dt.date:
        return self.day

    def now(self) -> dt.datetime:
        return dt.datetime.combine(self.day, dt.time(12), tzinfo=self.timezone)
