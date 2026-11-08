from decimal import Decimal

import pytest
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from fornada_evals.checks import addresses_owner, expected_weight_kg, reais, tool_calls


def test_tool_calls_keep_order_and_turn() -> None:
    capacity = ToolCall(name="check_capacity", input_parameters={"date": "2026-03-12"})
    quote = ToolCall(name="calculate_quote", input_parameters={"weight_kg": 2})
    order = ToolCall(name="create_order", input_parameters={})
    test_case = ConversationalTestCase(
        turns=[
            Turn(role="user", content="Oi"),
            Turn(role="assistant", content="Olá", tools_called=[capacity, quote]),
            Turn(role="user", content="Pode fechar"),
            Turn(role="assistant", content="Fechado", tools_called=[order]),
        ]
    )

    assert tool_calls(test_case) == [(2, capacity), (2, quote), (4, order)]


@pytest.mark.parametrize(
    ("text", "amounts"),
    [
        ("Total: R$ 1.234,56", [Decimal("1234.56")]),
        ("Sinal de R$194,80.", [Decimal("194.80")]),
        ("Fica R$ 80 o kg", [Decimal("80.00")]),
        ("Bolo R$ 389,60, entrega R$ 15,00", [Decimal("389.60"), Decimal("15.00")]),
        ("Sem preço aqui, só 2 kg.", []),
    ],
)
def test_reais(text: str, amounts: list[Decimal]) -> None:
    assert reais(text) == amounts


@pytest.mark.parametrize(
    "text",
    ["Olá, dono! Pedido novo.", "Mensagem para a dona da confeitaria", "Oi proprietária"],
)
def test_owner_is_addressed(text: str) -> None:
    assert addresses_owner(text)


@pytest.mark.parametrize(
    "text", ["Seu pedido do Donato está pronto", "O dono do pedido é você", "Olá, Maria!"]
)
def test_owner_is_not_addressed(text: str) -> None:
    assert not addresses_owner(text)


@pytest.mark.parametrize(
    ("people", "kg"), [(40, Decimal("6.0")), (3, Decimal("1.0")), (11, Decimal("2.0"))]
)
def test_expected_weight(people: int, kg: Decimal) -> None:
    assert expected_weight_kg(people) == kg
