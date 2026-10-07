import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker

from fornada_api.agents.attendant.tools import build_tools, jsonable
from fornada_api.models import OrderStatus
from fornada_api.services.clock import FixedClock

TOOL_NAMES = {
    "search_catalog",
    "check_capacity",
    "calculate_quote",
    "create_order",
    "get_order",
    "cancel_order",
    "apply_coupon",
    "send_message",
    "escalate_to_human",
}


def tools() -> list:
    # The factory is never called here: building the tools does not touch the database.
    return build_tools(
        async_sessionmaker(), clock=FixedClock(dt.date(2026, 10, 7)), daily_capacity_kg=Decimal(15)
    )


def test_exactly_nine_tools() -> None:
    built = tools()
    assert len(built) == 9
    assert {t.name for t in built} == TOOL_NAMES


def test_each_tool_has_description_and_schema() -> None:
    for each in tools():
        assert each.description.strip(), each.name
        schema = each.tool_call_schema.model_json_schema()
        assert schema["type"] == "object", each.name
        assert each.handle_tool_error is True


def test_runtime_is_hidden_from_the_llm() -> None:
    escalate = next(t for t in tools() if t.name == "escalate_to_human")
    properties = escalate.tool_call_schema.model_json_schema()["properties"]
    assert set(properties) == {"reason", "phone"}


def test_amount_arguments_accept_numbers_and_strings() -> None:
    quote = next(t for t in tools() if t.name == "calculate_quote")
    weight = quote.tool_call_schema.model_json_schema()["properties"]["weight_kg"]
    assert {option["type"] for option in weight["anyOf"]} == {"number", "string"}


def test_jsonable() -> None:
    assert jsonable({"a": [Decimal("10.00"), dt.date(2026, 10, 9), OrderStatus.CANCELLED]}) == {
        "a": ["10.00", "2026-10-09", "cancelled"]
    }
