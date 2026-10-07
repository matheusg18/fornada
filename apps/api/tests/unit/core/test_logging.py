import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fornada_api.core.config import LogSettings
from fornada_api.core.logging import configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:], root.level = handlers, level


def lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.splitlines()


def one_record(capsys: pytest.CaptureFixture[str]) -> dict:
    out = lines(capsys)
    assert len(out) == 1
    return json.loads(out[0])


def setup(level: str = "INFO") -> None:
    configure_logging(LogSettings(level=level))


def test_application_log_is_one_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    logging.getLogger("fornada_api.orders").info("pedido criado")
    assert one_record(capsys)["message"] == "pedido criado"


def test_library_log_is_json_too(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    logging.getLogger("httpx").warning("slow response")
    record = one_record(capsys)
    assert record["logger"] == "httpx"
    assert record["message"] == "slow response"


def test_standard_fields(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    logging.getLogger("fornada_api.tools").warning("bolo de maçã")
    out = capsys.readouterr().out
    assert "maçã" in out  # not escaped
    record = json.loads(out)
    assert record["level"] == "WARNING"
    assert record["logger"] == "fornada_api.tools"
    assert record["message"] == "bolo de maçã"
    timestamp = datetime.fromisoformat(record["timestamp"])
    assert timestamp.utcoffset() == UTC.utcoffset(None)


def test_extra_becomes_top_level_fields(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    logging.getLogger("t").info("quote", extra={"order_id": 482, "total": "120.00"})
    record = one_record(capsys)
    assert record["order_id"] == 482
    assert record["total"] == "120.00"


def test_extra_cannot_replace_standard_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup()
    logging.getLogger("real").warning(
        "msg", extra={"level": "HACK", "logger": "fake", "timestamp": "now"}
    )
    record = one_record(capsys)
    assert record["level"] == "WARNING"
    assert record["logger"] == "real"
    assert record["timestamp"] != "now"


def test_non_serializable_extras_become_strings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup()
    logging.getLogger("t").info(
        "x", extra={"total": Decimal("120.50"), "at": datetime(2026, 1, 1, tzinfo=UTC)}
    )
    record = one_record(capsys)
    assert isinstance(record["total"], str) and "120.5" in record["total"]
    assert isinstance(record["at"], str) and "2026-01-01" in record["at"]


def test_exception_is_serialized_on_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    try:
        raise ZeroDivisionError("division by zero")
    except ZeroDivisionError:
        logging.getLogger("t").exception("boom")
    record = one_record(capsys)
    assert "ZeroDivisionError" in record["exception"]


def test_records_below_level_are_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    setup("WARNING")
    logging.getLogger("t").info("quiet")
    assert lines(capsys) == []


def test_setup_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    setup()
    setup()
    logging.getLogger("t").info("once")
    assert len(lines(capsys)) == 1
