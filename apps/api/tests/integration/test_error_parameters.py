import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.anyio

PHONE = "+5581999991234"
NAME = "Maria Teste"


async def test_database_errors_carry_no_parameter_values(
    app_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    # The phone breaks the CHECK on `customers.phone`, so the insert fails
    # with its bound values in hand.
    with pytest.raises(DBAPIError) as raised:
        async with app_engine.connect() as connection:
            await connection.execute(
                text("INSERT INTO customers (name, phone) VALUES (:name, :phone)"),
                {"name": NAME, "phone": PHONE + "x"},
            )

    with caplog.at_level(logging.ERROR):
        try:
            raise raised.value
        except DBAPIError:
            logging.getLogger("t").exception("tool failed")

    logged = str(raised.value) + caplog.text
    assert "INSERT INTO customers" in logged  # the statement stays
    assert "5581999991234" not in logged
    assert NAME not in logged
