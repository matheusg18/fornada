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
    # TODO(human): no_past_date (DATE). Suggested sketch:
    # violations: Violations = []
    # day = run_day(test_case)
    # for turn, call in tool_calls(test_case):
    #     arg = {"check_capacity": "date", "create_order": "delivery_date"}.get(call.name)
    #     if arg and (value := (call.input_parameters or {}).get(arg)):
    #         if dt.date.fromisoformat(str(value)) < day:
    #             violations.append(f"turn {turn}: {call.name}.{arg}={value} < {day}")
    # return violations
    # Points to weigh: a malformed date string (count it as a violation, or skip?); a
    # past date whose call failed (the tool refused it: still the agent's error?).
    raise NotImplementedError("no_past_date")


def order_on_open_date(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): order_on_open_date (CAPACITY). Suggested sketch:
    # checked: dict[str, dict[str, Any]] = {}  # date -> its capacity report
    # for turn, call in tool_calls(test_case):
    #     args = call.input_parameters or {}
    #     if call.name == "check_capacity" and (report := result(call)):
    #         checked[str(args.get("date"))] = report
    #     elif call.name == "create_order":
    #         day, report = str(args.get("delivery_date")), checked.get(...)
    #         if report is None: violation "never checked"
    #         elif Decimal(report["free_kg"]) < Decimal(str(args["weight_kg"])): violation
    #         elif not report[lead-time flag for custom or regular]: violation
    # Points to weigh: two checks of the same date (keep the latest, or any that
    # showed room?); where "custom" comes from (the order's quote.is_custom in its
    # result, or the catalog); a create_order that itself failed.
    raise NotImplementedError("order_on_open_date")


def no_order_after_outage(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): no_order_after_outage (OUTAGE). Suggested sketch:
    # latest_failed: dict[str, bool] = {}  # date -> did its latest check fail?
    # for turn, call in tool_calls(test_case):
    #     args = call.input_parameters or {}
    #     if call.name == "check_capacity":
    #         latest_failed[str(args.get("date"))] = result(call) is None
    #     elif call.name == "create_order" and latest_failed.get(str(args.get("delivery_date"))):
    #         violations.append(f"turn {turn}: create_order for {...} after check_capacity failed")
    # Points to weigh: an order for a date never checked in an outage case (this check,
    # or leave it to order_on_open_date?); a failed create_order (does it count?).
    raise NotImplementedError("no_order_after_outage")


def price_from_tool(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): price_from_tool (PRICE). Suggested sketch:
    # by_turn: dict[int, set[Decimal]] = {}
    # for turn, call in tool_calls(test_case):
    #     if call.name in {"calculate_quote", "create_order", "apply_coupon"}:
    #         data = result(call) or {}
    #         money = data.get("quote", data)  # create_order nests its quote
    #         by_turn.setdefault(turn, set()).update(
    #             Decimal(money[f]) for f in MONEY_FIELDS if f in money)
    # for turn, text in replies(test_case):
    #     for amount in reais(text):
    #         if amount not in by_turn.get(turn, set()): violation naming turn and amount
    # Points to weigh: amounts the customer said and the bot repeats ("faz por R$ 170?");
    # apply_coupon's result shape; search_catalog's price_per_kg (the spec leaves it out).
    raise NotImplementedError("price_from_tool")


def escalation_has_phone(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): escalation_has_phone (ESCALATION). Suggested sketch:
    # for turn, call in tool_calls(test_case):
    #     if call.name == "escalate_to_human":
    #         phone = (call.input_parameters or {}).get("phone")
    #         if not phone or not str(phone).strip():
    #             violations.append(f"turn {turn}: escalate_to_human without a phone")
    # Points to weigh: a phone that is not the customer's (out of scope here, or a
    # second rule?); a phone with no area code.
    raise NotImplementedError("escalation_has_phone")


def serving_rule(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): serving_rule (SIZE). Suggested sketch:
    # people = case_setup(test_case).get("party_size")
    # if people is None: return []
    # expected = expected_weight_kg(people)
    # weights = [(turn, Decimal(str(args["weight_kg"]))) for turn, call in tool_calls(...)
    #            if call.name in {"calculate_quote", "create_order"} ...]
    # for turn, kg in weights: if kg != expected: violation naming kg and expected
    # if not weights and no reply states the expected weight: violation naming expected
    # Points to weigh: how "a reply states 6 kg" is read ("6 kg", "6,0 kg", "seis quilos");
    # the customer later asking for a different weight on purpose.
    raise NotImplementedError("serving_rule")


def confirmation_before_order(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): confirmation_before_order. Suggested sketch:
    # shown: set[tuple[str, Decimal]] = set()  # (product, weight) whose total a reply stated
    # for each assistant turn, in order:
    #     for create_order calls in this turn:
    #         if (product, weight) not in shown: violation (shown holds earlier turns only)
    #     for calculate_quote calls in this turn whose total is in reais(this turn's reply):
    #         shown.add((product, weight))
    # Points to weigh: order of the two loops (a quote shown in the same turn must not
    # count); weights as 2 vs 2.0 (compare as Decimal); a delivery fee changing the total.
    raise NotImplementedError("confirmation_before_order")


def requote_after_change(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): requote_after_change. Suggested sketch:
    # change = case_setup(test_case).get("flavor_change")
    # if change is None: return []
    # first_reply = 2 * change["turn"]  # customer turn n -> its reply's position in turns
    # requoted = False
    # for each assistant turn at or after first_reply, in order:
    #     requoted |= any calculate_quote with product_slug == change["product"] in this turn
    #     if not requoted and reais(reply): violation naming the turn and the amount
    # Points to weigh: the position mapping (it assumes turns alternate user/assistant,
    # which a failed run can break); an amount that is not a price (a delivery fee alone).
    raise NotImplementedError("requote_after_change")


def no_message_to_owner(test_case: ConversationalTestCase) -> Violations:
    # TODO(human): no_message_to_owner (MESSAGE). Suggested sketch:
    # for turn, call in tool_calls(test_case):
    #     if call.name == "send_message":
    #         text = str((call.input_parameters or {}).get("text", ""))
    #         if addresses_owner(text): violation naming the turn and the text's start
    # Points to weigh: how much of the text goes in the reason (it reaches the report);
    # a message that mentions the owner but is addressed to the customer.
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
