"""The deterministic checks: one DeepEval conversational metric per check id.

This module holds the helpers the predicates share. The rule each check enforces is
the maintainer's; see the `add-eval-harness` design, decision 7.
"""

import math
import re
import unicodedata
from decimal import Decimal

from deepeval.test_case import ConversationalTestCase, ToolCall

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
