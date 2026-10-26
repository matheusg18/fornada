"""The deterministic checks: one DeepEval conversational metric per check id.

Each metric scores a recorded conversation 1 (no violation) or 0, with a reason that
lists every violation with its turn. The metric classes and the helpers are plumbing; the
predicate each check runs is the maintainer's rule. See the `add-eval-harness` design,
decision 7.
"""

import datetime as dt
import json
import math
import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from typing import Any, ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case import ConversationalTestCase, ToolCall

from fornada_evals.dataset import CheckId

# What a predicate returns: one line per violation, naming its turn and the value.
type Violations = list[str]
# Binary score: only a conversation with no violation passes.
THRESHOLD = 1.0

# The money fields in the tools' results.
MONEY_FIELDS = ("price_per_kg", "subtotal", "delivery_fee", "discount", "total", "deposit")
OWNER_WORDS = ("dono", "dona", "proprietario", "proprietaria")

KG_PER_PERSON = Decimal("0.15")
WEIGHT_STEP_KG = Decimal("0.5")
MIN_WEIGHT_KG = Decimal("1.0")

# `R$ 1.234,56`, `R$194,80`, `R$ 80`: thousands with dots, cents after a comma.
_REAIS = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?")
# An owner word as the one addressed: at the start, after "olá"/"oi", or after "para o/a".
_OWNER = re.compile(
    r"(?:^\s*|\b(?:ola|oi)\b[\s,!]*|\bpara\s+[oa]\s+)(?:" + "|".join(OWNER_WORDS) + r")\b"
)


def tool_calls(test_case: ConversationalTestCase) -> list[tuple[int, ToolCall]]:
    """Every tool call in the conversation, in order, with its turn's 1-based position in
    `test_case.turns` (customer turns count too), the number a reason names."""
    return [
        (position, call)
        for position, turn in enumerate(test_case.turns, start=1)
        for call in turn.tools_called or []
    ]


def result(call: ToolCall) -> dict[str, Any] | None:
    """The tool's result as JSON, or None when the call failed (its output is the error text)."""
    try:
        parsed = json.loads(call.output) if isinstance(call.output, str) else None
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def replies(test_case: ConversationalTestCase) -> list[tuple[int, str]]:
    """Every assistant reply with its turn's 1-based position, as in `tool_calls`."""
    return [
        (position, turn.content)
        for position, turn in enumerate(test_case.turns, start=1)
        if turn.role == "assistant"
    ]


def run_day(test_case: ConversationalTestCase) -> dt.date:
    """The day the case ran on, which the runner records."""
    return dt.date.fromisoformat((test_case.metadata or {})["run_day"])


def case_setup(test_case: ConversationalTestCase) -> dict[str, Any]:
    """The case's metadata from the dataset (party_size, flavor_change, outage...)."""
    return (test_case.metadata or {}).get("case", {})


def reais(text: str) -> list[Decimal]:
    """Every amount in reais written in `text`, in order."""
    return [
        Decimal(f"{whole.replace('.', '')}.{cents or '00'}")
        for whole, cents in _REAIS.findall(text)
    ]


def addresses_owner(text: str) -> bool:
    """Whether `text` speaks to the shop's owner ("Olá, dono!", "para a dona"), case- and
    accent-insensitive. A name that only starts like one ("Donato") does not count."""
    return _OWNER.search(_fold(text)) is not None


def expected_weight_kg(people: int) -> Decimal:
    """The serving rule: 150 g a person, rounded up to the next half kilo, 1 kg minimum.
    In `Decimal`: in floats, 0.15 * N can land just above a half kilo and round up a step."""
    steps = math.ceil(KG_PER_PERSON * people / WEIGHT_STEP_KG)
    return max(MIN_WEIGHT_KG, steps * WEIGHT_STEP_KG)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


# --- The predicates: the maintainer's rules (task 5.4) ---


def no_past_date(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("no_past_date")


def order_on_open_date(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("order_on_open_date")


def no_order_after_outage(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("no_order_after_outage")


def price_from_tool(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("price_from_tool")


def escalation_has_phone(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("escalation_has_phone")


def serving_rule(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("serving_rule")


def confirmation_before_order(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("confirmation_before_order")


def requote_after_change(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("requote_after_change")


def no_message_to_owner(test_case: ConversationalTestCase) -> Violations:
    raise NotImplementedError("no_message_to_owner")


# --- The metrics ---


class Check(BaseConversationalMetric):
    """A deterministic check as a DeepEval metric: binary score, strict, no LLM."""

    check_id: ClassVar[CheckId]
    predicate: ClassVar[Callable[[ConversationalTestCase], Violations]]

    def __init__(self) -> None:
        self.threshold = THRESHOLD
        self.strict_mode = True
        self.include_reason = True

    def measure(self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any) -> float:
        try:
            violations = type(self).predicate(test_case)
        except Exception as error:
            # As DeepEval's custom metric guide does: record it, then let the runner see it.
            self.error = str(error)
            raise
        self.score = 0.0 if violations else 1.0
        self.reason = "; ".join(violations) if violations else "no violation"
        self.success = self.score >= THRESHOLD
        return self.score

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        # No I/O: the async path is the sync one.
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        # DeepEval's custom metric guide: a metric that errored never succeeds.
        if self.error is not None or self.score is None:
            self.success = False
        else:
            self.success = self.score >= THRESHOLD
        return self.success

    @property
    # The base types it as its own literal name, so no subclass name can match.
    def __name__(self) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self.check_id


def _check(
    check_id: CheckId, predicate: Callable[[ConversationalTestCase], Violations]
) -> type[Check]:
    return type(
        f"Check_{check_id}",
        (Check,),
        {"check_id": check_id, "predicate": staticmethod(predicate)},
    )


CHECKS: dict[CheckId, type[Check]] = {
    "no_past_date": _check("no_past_date", no_past_date),
    "order_on_open_date": _check("order_on_open_date", order_on_open_date),
    "no_order_after_outage": _check("no_order_after_outage", no_order_after_outage),
    "price_from_tool": _check("price_from_tool", price_from_tool),
    "escalation_has_phone": _check("escalation_has_phone", escalation_has_phone),
    "serving_rule": _check("serving_rule", serving_rule),
    "confirmation_before_order": _check("confirmation_before_order", confirmation_before_order),
    "requote_after_change": _check("requote_after_change", requote_after_change),
    "no_message_to_owner": _check("no_message_to_owner", no_message_to_owner),
}
