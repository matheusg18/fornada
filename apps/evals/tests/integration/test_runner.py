import datetime as dt
from decimal import Decimal

import pytest
from deepeval.test_case import ConversationalTestCase, Turn
from fornada_api.agents.attendant.metrics import TokenPrices
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_evals.runner import Agent, run_case

from fornada_evals.dataset import CaseMetadata, GoldenCase
from tests.fakes import ScriptedChatModel, reply, tool_call

pytestmark = pytest.mark.anyio

SEED_DAY = dt.date(2026, 3, 9)
FULL_DAY = SEED_DAY + dt.timedelta(3)
OUTAGE_TEXT = "internal error in check_capacity; try again later or escalate to a human"
MODEL_NAME = "scripted-model"
# 100 input and 20 output tokens per model call (tests/fakes.py): US$ 0.0002 a call.
PRICES = TokenPrices(Decimal(1), Decimal(5))
CALL_COST = 0.0002


def case(*turns: str, outage: bool = False) -> GoldenCase:
    return GoldenCase(
        name="runner-test",
        scenario="Cliente pede um bolo.",
        expected_outcome=None,
        turns=list(turns),
        metadata=CaseMetadata(
            category="OUTAGE" if outage else "CAPACITY",
            source="#1",
            critical=False,
            checks=["no_order_after_outage" if outage else "order_on_open_date"],
            outage=outage,
        ),
    )


def agent(*answers: object) -> Agent:
    return Agent(
        model=ScriptedChatModel(answers=list(answers)),  # pyright: ignore[reportArgumentType]
        model_name=MODEL_NAME,
        prices=PRICES,
        daily_capacity_kg=Decimal(15),
    )


def assistant_turns(test_case: ConversationalTestCase) -> list[Turn]:
    return [turn for turn in test_case.turns if turn.role == "assistant"]


def capacity_then_quote() -> list[object]:
    return [
        tool_call("check_capacity", {"date": FULL_DAY.isoformat()}, "call-1"),
        tool_call(
            "calculate_quote",
            {"product_slug": "bolo-chocolate", "weight_kg": 2, "fulfillment": "pickup"},
            "call-2",
        ),
        reply("Esse dia está cheio, mas o orçamento fica assim."),
    ]


async def test_two_turns_record_both_sides(database_url: str) -> None:
    test_case = await run_case(
        case("Oi, quero um bolo para {d+3:dd/mm}", "Obrigado"),
        0,
        database_url=database_url,
        agent=agent(reply("Olá!"), reply("De nada!")),
    )

    assert [(turn.role, turn.content) for turn in test_case.turns] == [
        ("user", "Oi, quero um bolo para 12/03"),
        ("assistant", "Olá!"),
        ("user", "Obrigado"),
        ("assistant", "De nada!"),
    ]


async def test_turn_lists_its_tool_calls_in_order(database_url: str) -> None:
    test_case = await run_case(
        case("Quero 2 kg de chocolate para {d+3:dd/mm}"),
        0,
        database_url=database_url,
        agent=agent(*capacity_then_quote()),
    )

    (turn,) = assistant_turns(test_case)
    calls = turn.tools_called or []
    assert [call.name for call in calls] == ["check_capacity", "calculate_quote"]
    assert calls[0].input_parameters == {"date": FULL_DAY.isoformat()}
    assert '"free_kg"' in str(calls[0].output)
    assert calls[1].input_parameters == {
        "product_slug": "bolo-chocolate",
        "weight_kg": 2,
        "fulfillment": "pickup",
    }
    assert '"deposit"' in str(calls[1].output)
    assert turn.metadata == {"tool_status": ["success", "success"]}


async def test_error_result_is_marked(database_url: str) -> None:
    test_case = await run_case(
        case("Quero o bolo de unicórnio"),
        0,
        database_url=database_url,
        agent=agent(
            tool_call(
                "calculate_quote",
                {"product_slug": "bolo-unicornio", "weight_kg": 2, "fulfillment": "pickup"},
                "call-1",
            ),
            reply("Não temos esse sabor."),
        ),
    )

    (turn,) = assistant_turns(test_case)
    assert turn.metadata == {"tool_status": ["error"]}


async def test_outage_case_fails_every_capacity_check(database_url: str) -> None:
    test_case = await run_case(
        case("Quero 2 kg de chocolate para {d+3:dd/mm}", outage=True),
        0,
        database_url=database_url,
        agent=agent(*capacity_then_quote()),
    )

    (turn,) = assistant_turns(test_case)
    calls = turn.tools_called or []
    assert calls[0].output == OUTAGE_TEXT
    # Chaos with no latency: the quote runs normally, and nothing waits.
    assert '"deposit"' in str(calls[1].output)
    assert turn.metadata == {"tool_status": ["error", "success"]}
    assert turn.latency_ms is not None and turn.latency_ms < 1000


async def test_regular_case_injects_nothing(database_url: str) -> None:
    test_case = await run_case(
        case("Quero 2 kg de chocolate para {d+3:dd/mm}"),
        0,
        database_url=database_url,
        agent=agent(*capacity_then_quote()),
    )

    (turn,) = assistant_turns(test_case)
    calls = turn.tools_called or []
    assert '"free_kg"' in str(calls[0].output)
    assert turn.metadata == {"tool_status": ["success", "success"]}


async def test_model_error_fails_the_run(database_url: str) -> None:
    test_case = await run_case(
        case("Oi", "Quero um bolo", "Obrigado"),
        0,
        database_url=database_url,
        agent=agent(reply("Olá!"), RuntimeError("provider down")),
    )

    assert [turn.role for turn in test_case.turns] == ["user", "assistant", "user"]
    metadata = test_case.metadata or {}
    assert metadata["failed"] is True
    assert "provider down" in metadata["error"]


async def test_metadata_describes_the_run(database_url: str) -> None:
    test_case = await run_case(
        case("Quero 2 kg de chocolate para {d+3:dd/mm}", "Obrigado"),
        2,
        database_url=database_url,
        agent=agent(*capacity_then_quote(), reply("De nada!")),
    )

    metadata = test_case.metadata or {}
    assert test_case.name == "runner-test"
    assert metadata["run_index"] == 2
    assert metadata["run_day"] == SEED_DAY.isoformat()
    assert metadata["prompt_version"] == load_system_prompt().version
    assert metadata["model"] == MODEL_NAME
    assert metadata["case"]["category"] == "CAPACITY"
    assert metadata["failed"] is False
    assert metadata["error"] is None
    latencies = metadata["latencies_ms"]
    assert len(latencies) == 2 and all(latency > 0 for latency in latencies)
    # Four model calls: two tool rounds and the reply in turn 1, the reply in turn 2.
    assert metadata["input_tokens"] == 400
    assert metadata["output_tokens"] == 80
    assert metadata["cost_usd"] == pytest.approx(4 * CALL_COST)
