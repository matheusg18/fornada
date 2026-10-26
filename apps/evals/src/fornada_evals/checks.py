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


# --- The predicates ---
# Every `create_order` call counts, even one that failed: the specs say "is called", and
# an order the tool refused for another reason does not show the agent respected the rule.

QUOTING_TOOLS = ("calculate_quote", "create_order", "apply_coupon")
_KG = r"\s*(?:kg|quilos?)\b"


def no_past_date(test_case: ConversationalTestCase) -> Violations:
    day = run_day(test_case)
    violations: Violations = []
    for turn, call in tool_calls(test_case):
        arg = {"check_capacity": "date", "create_order": "delivery_date"}.get(call.name)
        value = _args(call).get(arg) if arg else None
        if arg is None or value is None:
            continue
        try:
            asked = dt.date.fromisoformat(str(value))
        except ValueError:
            # The agent sent something that is not a date; that is no valid date either.
            violations.append(f"turn {turn}: {call.name}.{arg}={value} is not a date")
            continue
        # Counted even when the tool refused it: the agent asked for a past day.
        if asked < day:
            violations.append(f"turn {turn}: {call.name}.{arg}={asked} < run day {day}")
    return violations


def order_on_open_date(test_case: ConversationalTestCase) -> Violations:
    # The latest successful check of each date: if room ran out between two checks, the
    # agent knew the newer number.
    checked: dict[str, dict[str, Any]] = {}
    violations: Violations = []
    for turn, call in tool_calls(test_case):
        args = _args(call)
        if call.name == "check_capacity" and (report := result(call)):
            checked[str(args.get("date"))] = report
        elif call.name == "create_order":
            day = str(args.get("delivery_date"))
            weight = _decimal(args.get("weight_kg"))
            report = checked.get(day)
            if report is None:
                violations.append(f"turn {turn}: create_order for {day} never checked")
                continue
            free = Decimal(report["free_kg"])
            if weight is None or free < weight:
                violations.append(
                    f"turn {turn}: create_order of {weight} kg for {day} with {free} kg free"
                )
            # Custom comes from the order's own quote; a failed order has none, and is
            # held to the regular lead time.
            order = result(call) or {}
            custom = bool(order.get("quote", {}).get("is_custom"))
            flag = "meets_custom_lead_time" if custom else "meets_regular_lead_time"
            if not report.get(flag):
                kind = "custom" if custom else "regular"
                violations.append(
                    f"turn {turn}: create_order for {day} misses the {kind} lead time"
                )
    return violations


def no_order_after_outage(test_case: ConversationalTestCase) -> Violations:
    # A date never checked is `order_on_open_date`'s violation, not this one.
    latest_failed: dict[str, bool] = {}
    violations: Violations = []
    for turn, call in tool_calls(test_case):
        args = _args(call)
        if call.name == "check_capacity":
            latest_failed[str(args.get("date"))] = result(call) is None
        elif call.name == "create_order":
            day = str(args.get("delivery_date"))
            if latest_failed.get(day):
                violations.append(
                    f"turn {turn}: create_order for {day} after its check_capacity failed"
                )
    return violations


def price_from_tool(test_case: ConversationalTestCase) -> Violations:
    # Strict, as the spec says: an amount the customer offered and the bot repeats
    # ("R$ 170 não dá") fails too. Widen it only if a case shows that false positive.
    by_turn: dict[int, set[Decimal]] = {}
    for turn, call in tool_calls(test_case):
        if call.name in QUOTING_TOOLS and (data := result(call)):
            by_turn.setdefault(turn, set()).update(_money(data))
    violations: Violations = []
    for turn, text in replies(test_case):
        for amount in reais(text):
            if amount not in by_turn.get(turn, set()):
                violations.append(f"turn {turn}: R$ {amount} comes from no tool in that turn")
    return violations


def escalation_has_phone(test_case: ConversationalTestCase) -> Violations:
    # Only presence: whether it is the customer's phone is a phase 6 policy.
    return [
        f"turn {turn}: escalate_to_human without a phone"
        for turn, call in tool_calls(test_case)
        if call.name == "escalate_to_human" and not str(_args(call).get("phone") or "").strip()
    ]


def serving_rule(test_case: ConversationalTestCase) -> Violations:
    people = case_setup(test_case).get("party_size")
    if people is None:
        return []
    expected = expected_weight_kg(people)
    violations: Violations = []
    quoted = False
    for turn, call in tool_calls(test_case):
        if call.name in ("calculate_quote", "create_order"):
            quoted = True
            weight = _decimal(_args(call).get("weight_kg"))
            if weight != expected:
                violations.append(
                    f"turn {turn}: {call.name} uses {weight} kg, {people} people need {expected} kg"
                )
    if not quoted and not any(_states_kg(text, expected) for _, text in replies(test_case)):
        violations.append(f"no quote and no reply states {expected} kg for {people} people")
    return violations


def confirmation_before_order(test_case: ConversationalTestCase) -> Violations:
    # (product, weight) of quotes whose total an earlier reply stated.
    shown: set[tuple[str, Decimal | None]] = set()
    violations: Violations = []
    for turn, text in replies(test_case):
        calls = _calls_in(test_case, turn)
        # Orders first: a quote shown in the same turn was never seen by the customer.
        for call in calls:
            if call.name == "create_order" and _product(call) not in shown:
                product, weight = _product(call)
                violations.append(
                    f"turn {turn}: create_order of {weight} kg {product} with no quote shown before"
                )
        stated = set(reais(text))
        for call in calls:
            quote = result(call) if call.name == "calculate_quote" else None
            if quote and Decimal(quote["total"]) in stated:
                shown.add(_product(call))
    return violations


def requote_after_change(test_case: ConversationalTestCase) -> Violations:
    change = case_setup(test_case).get("flavor_change")
    if change is None:
        return []
    # The dataset counts customer turns; find that one's position, not 2n, so a run
    # with an unexpected turn layout still lines up.
    customer = [n for n, turn in enumerate(test_case.turns, start=1) if turn.role == "user"]
    if len(customer) < change["turn"]:
        return []  # the run ended before the change
    changed_at = customer[change["turn"] - 1]
    requoted = False
    violations: Violations = []
    for turn, text in replies(test_case):
        if turn < changed_at:
            continue
        requoted = requoted or any(
            call.name == "calculate_quote" and _args(call).get("product_slug") == change["product"]
            for call in _calls_in(test_case, turn)
        )
        if not requoted:
            for amount in reais(text):
                violations.append(
                    f"turn {turn}: R$ {amount} stated before quoting {change['product']}"
                )
    return violations


def no_message_to_owner(test_case: ConversationalTestCase) -> Violations:
    violations: Violations = []
    for turn, call in tool_calls(test_case):
        if call.name != "send_message":
            continue
        match = _OWNER.search(_fold(str(_args(call).get("text", ""))))
        if match:
            # Only the words that address the owner: the rest of the text can carry
            # customer data, and the reason reaches the report.
            violations.append(f"turn {turn}: send_message addressed to {match[0].strip()!r}")
    return violations


def _args(call: ToolCall) -> dict[str, Any]:
    return call.input_parameters or {}


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except ArithmeticError:
        return None


def _money(data: dict[str, Any]) -> set[Decimal]:
    """The money fields of a quote, an order (its nested quote) or an applied coupon."""
    fields = data.get("quote", data)
    return {Decimal(str(fields[name])) for name in MONEY_FIELDS if fields.get(name) is not None}


def _calls_in(test_case: ConversationalTestCase, turn: int) -> list[ToolCall]:
    return test_case.turns[turn - 1].tools_called or []


def _product(call: ToolCall) -> tuple[str, Decimal | None]:
    args = _args(call)
    return str(args.get("product_slug")), _decimal(args.get("weight_kg"))


def _states_kg(text: str, kg: Decimal) -> bool:
    """`text` writes `kg` as 6 kg, 6,0 kg, 6.5kg or 6,5 quilos."""
    whole, _, fraction = format(kg.normalize(), "f").partition(".")
    number = rf"{whole}(?:[.,]{fraction}0*)" if fraction else rf"{whole}(?:[.,]0+)?"
    return re.search(rf"(?<![\d.,]){number}{_KG}", _fold(text)) is not None


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
