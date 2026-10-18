"""Chaos mode: fault injection for simulator runs. See the `chaos-mode` spec.

One `Chaos` per process, built from `ChaosSettings` when `CHAOS__ENABLED` is on
and handed to the tools; `None` means off. It draws the delay of each tool
call, decides whether a `check_capacity` call fails, and remembers which
conversations already had a quote, so their later prices rise.

Draws come from one `random.Random(seed)`: with a seed, the same sequence of
calls gets the same delays and failures. The marks live in process memory, so
a restart forgets them and each worker process has its own.
"""

import random
from decimal import Decimal

from fornada_api.core.config import ChaosSettings

NO_CHANGE = Decimal(1)


class Chaos:
    def __init__(self, settings: ChaosSettings) -> None:
        self._latency_min_ms = settings.latency_min_ms
        self._latency_max_ms = settings.latency_max_ms
        self._capacity_failure_rate = settings.capacity_failure_rate
        self._raised = 1 + settings.price_increase_pct / 100
        self._random = random.Random(settings.seed)
        self._quoted: set[str] = set()

    def delay_ms(self) -> int:
        """Delay for one tool call, uniform in the configured range."""
        return self._random.randint(self._latency_min_ms, self._latency_max_ms)

    def capacity_fails(self) -> bool:
        """Whether this `check_capacity` call fails."""
        return self._random.random() < self._capacity_failure_rate

    def price_factor(self, conversation_id: str) -> Decimal:
        """Multiplier on the price per kg: 1 until the conversation's first quote."""
        return self._raised if conversation_id in self._quoted else NO_CHANGE

    def mark_quoted(self, conversation_id: str) -> None:
        """Record a successful quote; later prices in the conversation rise once."""
        self._quoted.add(conversation_id)
