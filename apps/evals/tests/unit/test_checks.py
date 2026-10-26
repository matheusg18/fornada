"""One failing and one passing recorded conversation per check, from the phase 3 open
codes each one cites (docs/error-analysis/phase-3-open-codes.md). Run day 2026-10-19, as
in that run. Conversations are shaped as the runner records them: tool results are the
tools' JSON (decimals as strings), errors are plain text, and each assistant turn's
`metadata["tool_status"]` lists its calls' statuses in order."""

import datetime as dt
import json
import re
from typing import Any

import pytest
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from fornada_evals.checks import CHECKS
from fornada_evals.dataset import CheckId

RUN_DAY = dt.date(2026, 10, 19)
OUTAGE_TEXT = "internal error in check_capacity; try again later or escalate to a human"
CUSTOMER_PHONE = "81999991234"


def user(text: str) -> Turn:
    return Turn(role="user", content=text)


def bot(text: str, *calls: tuple[str, dict[str, Any], dict[str, Any] | str]) -> Turn:
    """An assistant turn; each call is (tool, args, result), and a text result is an error."""
    return Turn(
        role="assistant",
        content=text,
        tools_called=[
            ToolCall(
                name=name,
                input_parameters=args,
                output=result if isinstance(result, str) else json.dumps(result),
            )
            for name, args, result in calls
        ],
        metadata={
            "tool_status": [
                "error" if isinstance(result, str) else "success" for *_, result in calls
            ]
        },
    )


def conversation(*turns: Turn, **case: Any) -> ConversationalTestCase:
    """`case` holds the case's metadata fields the checks read (party_size, flavor_change)."""
    return ConversationalTestCase(
        turns=list(turns),
        metadata={"run_day": RUN_DAY.isoformat(), "case": {"outage": False, **case}},
    )


def capacity(day: str, free_kg: str = "15.00", *, lead_time: bool = True) -> dict[str, Any]:
    return {
        "date": day,
        "capacity_kg": "15.00",
        "used_kg": f"{15 - float(free_kg):.2f}",
        "free_kg": free_kg,
        "override_reason": None,
        "earliest_regular_date": "2026-10-21",
        "earliest_custom_date": "2026-10-24",
        "meets_regular_lead_time": lead_time,
        "meets_custom_lead_time": lead_time,
    }


PRICES = {"bolo-chocolate": "89.90", "bolo-limao": "84.90", "bolo-cenoura": "79.90"}


def quote(slug: str, weight_kg: str = "2.0") -> dict[str, Any]:
    total = f"{float(PRICES[slug]) * float(weight_kg):.2f}"
    return {
        "product_slug": slug,
        "product_name": slug,
        "is_custom": False,
        "weight_kg": weight_kg,
        "pan_size": "P",
        "fulfillment": "pickup",
        "neighborhood": None,
        "price_per_kg": PRICES[slug],
        "subtotal": total,
        "delivery_fee": "0.00",
        "discount": "0.00",
        "total": total,
        "deposit": f"{float(total) / 2:.2f}",
    }


def quote_args(slug: str, weight_kg: float = 2) -> dict[str, Any]:
    return {"product_slug": slug, "weight_kg": weight_kg, "fulfillment": "pickup"}


def order_args(day: str, slug: str = "bolo-chocolate", weight_kg: float = 2) -> dict[str, Any]:
    return {
        "customer_name": "Ana",
        "phone": CUSTOMER_PHONE,
        "delivery_date": day,
        **quote_args(slug, weight_kg),
    }


def order(day: str, slug: str = "bolo-chocolate", weight_kg: str = "2.0") -> dict[str, Any]:
    return {
        "order_id": 205,
        "status": "pending_payment",
        "customer_name": "Ana",
        "phone": CUSTOMER_PHONE,
        "delivery_date": day,
        "quote": quote(slug, weight_kg),
        "payment_link": "https://pay.example/205",
    }


def verdict(check: CheckId, test_case: ConversationalTestCase) -> tuple[bool, str]:
    metric = CHECKS[check]()
    metric.measure(test_case)
    return metric.is_successful(), metric.reason or ""


def names_kg(reason: str, kg: str) -> bool:
    """`kg` written as 3, 3.0 or 3,0 in the reason."""
    whole = kg.split(".")[0]
    return re.search(rf"(?<![\d.,]){whole}(?:[.,]0+)?(?![\d.,]*\d)", reason) is not None


# --- no_past_date (#6: checks 2024-10-22 on a 2026 run) ---

PAST_DATE = conversation(
    user("Preciso de um bolo de chocolate pra quarta, dia 22"),
    bot(
        "Para 22/10 não temos mais espaço.",
        ("check_capacity", {"date": "2024-10-22"}, capacity("2024-10-22", lead_time=False)),
    ),
)
FUTURE_DATE = conversation(
    user("Quero um bolo pro dia 25"),
    bot("Dia 25 está livre!", ("check_capacity", {"date": "2026-10-25"}, capacity("2026-10-25"))),
)


def test_no_past_date() -> None:
    passed, reason = verdict("no_past_date", PAST_DATE)
    assert not passed
    assert "turn 2" in reason and "2024-10-22" in reason

    assert verdict("no_past_date", FUTURE_DATE)[0]


# --- order_on_open_date (#40: 0.5 free kg, then a 2 kg order) ---

SHORT_DAY = conversation(
    user("Quero 2 kg de chocolate pro dia 30"),
    bot(
        "Dia 30 está fechado pra você!",
        ("check_capacity", {"date": "2026-10-30"}, capacity("2026-10-30", "0.50")),
    ),
    user("Pode fazer o pedido"),
    bot(
        "Pedido feito!",
        ("create_order", order_args("2026-10-30"), order("2026-10-30")),
    ),
)
UNCHECKED_DAY = conversation(
    user("Fecha 2 kg de chocolate pro dia 27"),
    bot("Pedido feito!", ("create_order", order_args("2026-10-27"), order("2026-10-27"))),
)
OPEN_DAY = conversation(
    user("Quero 2 kg de chocolate pro dia 30"),
    bot(
        "Dia 30 tem espaço.",
        ("check_capacity", {"date": "2026-10-30"}, capacity("2026-10-30")),
    ),
    user("Pode fazer o pedido"),
    bot("Pedido feito!", ("create_order", order_args("2026-10-30"), order("2026-10-30"))),
)


def test_order_on_open_date() -> None:
    passed, reason = verdict("order_on_open_date", SHORT_DAY)
    assert not passed
    assert "turn 4" in reason and "2026-10-30" in reason

    passed, reason = verdict("order_on_open_date", UNCHECKED_DAY)
    assert not passed
    assert "turn 2" in reason and "2026-10-27" in reason

    assert verdict("order_on_open_date", OPEN_DAY)[0]


def test_nothing_to_check_passes() -> None:
    test_case = conversation(user("Oi, vocês fazem bolo de cenoura?"), bot("Fazemos sim!"))

    assert verdict("order_on_open_date", test_case)[0]


# --- no_order_after_outage (#16: capacity down, order created anyway) ---

ORDER_AFTER_OUTAGE = conversation(
    user("Quero um bolo de chocolate pro dia 25"),
    bot(
        "O sistema de agenda está fora do ar.",
        ("check_capacity", {"date": "2026-10-25"}, OUTAGE_TEXT),
    ),
    user("Faz assim mesmo"),
    bot("Pedido feito!", ("create_order", order_args("2026-10-25"), order("2026-10-25"))),
)
OUTAGE_ESCALATED = conversation(
    user("Quero um bolo de chocolate pro dia 25"),
    bot(
        "Não consigo confirmar a data agora; chamei a dona.",
        ("check_capacity", {"date": "2026-10-25"}, OUTAGE_TEXT),
        (
            "escalate_to_human",
            {"reason": "agenda fora do ar", "phone": CUSTOMER_PHONE},
            {"escalation_id": 7},
        ),
    ),
)


def test_no_order_after_outage() -> None:
    passed, reason = verdict("no_order_after_outage", ORDER_AFTER_OUTAGE)
    assert not passed
    assert "turn 4" in reason and "2026-10-25" in reason

    assert verdict("no_order_after_outage", OUTAGE_ESCALATED)[0]


# --- price_from_tool (#9: does the math itself, R$ 159,60) ---

PRICE_BY_HAND = conversation(
    user("Quanto fica 2 kg de cenoura?"),
    bot("Fica R$ 159,60 no total."),
)
PRICE_FROM_QUOTE = conversation(
    user("Quanto fica 2 kg de chocolate?"),
    bot(
        "O total fica R$ 179,80, com sinal de R$ 89,90.",
        ("calculate_quote", quote_args("bolo-chocolate"), quote("bolo-chocolate")),
    ),
)


def test_price_from_tool() -> None:
    passed, reason = verdict("price_from_tool", PRICE_BY_HAND)
    assert not passed
    assert "turn 2" in reason and ("159,60" in reason or "159.60" in reason)

    assert verdict("price_from_tool", PRICE_FROM_QUOTE)[0]


# --- escalation_has_phone (#63: escalates with phone null) ---

ESCALATION_NO_PHONE = conversation(
    user("Faz por R$ 170 que eu fecho"),
    bot(
        "Vou passar pro dono.",
        ("escalate_to_human", {"reason": "cliente pede R$ 170", "phone": None}, {"id": 3}),
    ),
)
ESCALATION_WITH_PHONE = conversation(
    user("Faz por R$ 170 que eu fecho, meu número é 81999991234"),
    bot(
        "Vou passar pro dono.",
        (
            "escalate_to_human",
            {"reason": "cliente pede R$ 170", "phone": CUSTOMER_PHONE},
            {"id": 3},
        ),
    ),
)


def test_escalation_has_phone() -> None:
    passed, reason = verdict("escalation_has_phone", ESCALATION_NO_PHONE)
    assert not passed
    assert "turn 2" in reason

    assert verdict("escalation_has_phone", ESCALATION_WITH_PHONE)[0]


# --- serving_rule (#48: 4,5 kg quoted for 40 people; #21: never quotes) ---

GUESSED_WEIGHT = conversation(
    user("Bolo de chocolate pra 40 pessoas"),
    bot(
        "Para 40 pessoas, 3 kg resolve.",
        ("calculate_quote", quote_args("bolo-chocolate", 3), quote("bolo-chocolate", "3.0")),
    ),
    party_size=40,
)
NO_WEIGHT = conversation(
    user("Bolo pra 40 pessoas, qual tamanho?"),
    bot("Uma forma média, de 2 a 3,5 kg, deve servir."),
    party_size=40,
)
SERVING_RULE = conversation(
    user("Bolo de chocolate pra 40 pessoas"),
    bot(
        "Para 40 pessoas, 6 kg.",
        ("calculate_quote", quote_args("bolo-chocolate", 6), quote("bolo-chocolate", "6.0")),
    ),
    party_size=40,
)


def test_serving_rule() -> None:
    passed, reason = verdict("serving_rule", GUESSED_WEIGHT)
    assert not passed
    assert "turn 2" in reason and names_kg(reason, "3") and names_kg(reason, "6")

    passed, reason = verdict("serving_rule", NO_WEIGHT)
    assert not passed
    assert names_kg(reason, "6")

    assert verdict("serving_rule", SERVING_RULE)[0]


# --- confirmation_before_order (#48: create_order with no explicit confirmation) ---

QUOTE_AND_ORDER_TOGETHER = conversation(
    user("Quero 2 kg de chocolate pro dia 30, tenta desconto que eu fecho"),
    bot(
        "Pedido feito, total R$ 179,80!",
        ("check_capacity", {"date": "2026-10-30"}, capacity("2026-10-30")),
        ("calculate_quote", quote_args("bolo-chocolate"), quote("bolo-chocolate")),
        ("create_order", order_args("2026-10-30"), order("2026-10-30")),
    ),
)
CUSTOMER_CONFIRMED = conversation(
    user("Quero 2 kg de chocolate pro dia 30"),
    bot(
        "O total fica R$ 179,80. Posso fechar?",
        ("check_capacity", {"date": "2026-10-30"}, capacity("2026-10-30")),
        ("calculate_quote", quote_args("bolo-chocolate"), quote("bolo-chocolate")),
    ),
    user("Pode fechar"),
    bot("Pedido feito!", ("create_order", order_args("2026-10-30"), order("2026-10-30"))),
)


def test_confirmation_before_order() -> None:
    passed, reason = verdict("confirmation_before_order", QUOTE_AND_ORDER_TOGETHER)
    assert not passed
    assert "turn 2" in reason

    assert verdict("confirmation_before_order", CUSTOMER_CONFIRMED)[0]


# --- requote_after_change (#12: an earlier quote reused after the flavor change) ---

FLAVOR_CHANGE = {"turn": 3, "product": "bolo-limao"}


def flavor_change_conversation(third_reply: Turn) -> ConversationalTestCase:
    return conversation(
        user("Quanto fica 2 kg de chocolate?"),
        bot(
            "Fica R$ 179,80.",
            ("calculate_quote", quote_args("bolo-chocolate"), quote("bolo-chocolate")),
        ),
        user("Hmm, deixa eu pensar"),
        bot("Claro, fico no aguardo."),
        user("Troca pra limão"),
        third_reply,
        flavor_change=FLAVOR_CHANGE,
    )


OLD_PRICE_REUSED = flavor_change_conversation(bot("Pronto, de limão fica R$ 179,80."))
NEW_QUOTE = flavor_change_conversation(
    bot(
        "De limão fica R$ 169,80.",
        ("calculate_quote", quote_args("bolo-limao"), quote("bolo-limao")),
    )
)


def test_requote_after_change() -> None:
    passed, reason = verdict("requote_after_change", OLD_PRICE_REUSED)
    assert not passed
    assert "turn 6" in reason and ("179,80" in reason or "179.80" in reason)

    assert verdict("requote_after_change", NEW_QUOTE)[0]


# --- no_message_to_owner (#4: a message to the owner sent to the customer's phone) ---


def message_conversation(text: str) -> ConversationalTestCase:
    return conversation(
        user("Vocês conseguem me dar 10% de desconto?"),
        bot(
            "Mandei a mensagem.",
            ("send_message", {"phone": CUSTOMER_PHONE, "text": text}, {"message_id": 9}),
        ),
    )


MESSAGE_TO_OWNER = message_conversation("Olá, dono! A cliente quer um desconto de 10%")
ORDER_CONFIRMATION = message_conversation("Olá, Maria! Recebemos seu pedido #12")


def test_no_message_to_owner() -> None:
    passed, reason = verdict("no_message_to_owner", MESSAGE_TO_OWNER)
    assert not passed
    assert "turn 2" in reason

    assert verdict("no_message_to_owner", ORDER_CONFIRMATION)[0]


# --- every check: same conversation, same verdict ---

FAILING: list[tuple[CheckId, ConversationalTestCase]] = [
    ("no_past_date", PAST_DATE),
    ("order_on_open_date", SHORT_DAY),
    ("no_order_after_outage", ORDER_AFTER_OUTAGE),
    ("price_from_tool", PRICE_BY_HAND),
    ("escalation_has_phone", ESCALATION_NO_PHONE),
    ("serving_rule", GUESSED_WEIGHT),
    ("confirmation_before_order", QUOTE_AND_ORDER_TOGETHER),
    ("requote_after_change", OLD_PRICE_REUSED),
    ("no_message_to_owner", MESSAGE_TO_OWNER),
]


@pytest.mark.parametrize(("check", "test_case"), FAILING, ids=[check for check, _ in FAILING])
def test_same_conversation_same_verdict(check: CheckId, test_case: ConversationalTestCase) -> None:
    assert verdict(check, test_case) == verdict(check, test_case)
