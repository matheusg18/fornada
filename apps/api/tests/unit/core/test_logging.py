import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace import TracerProvider

from fornada_api.core.config import LogLevel, LogSettings, TelemetrySettings
from fornada_api.core.logging import configure_logging
from fornada_api.core.telemetry import build_logger_provider


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


def setup(level: LogLevel = "INFO") -> None:
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


# --- OTLP export ------------------------------------------------------------------


def setup_export(
    level: LogLevel = "INFO",
) -> tuple[InMemoryLogRecordExporter, LoggerProvider]:
    exporter = InMemoryLogRecordExporter()
    provider = build_logger_provider(TelemetrySettings(enabled=True), exporter)
    configure_logging(LogSettings(level=level), provider)
    return exporter, provider


def exported(exporter: InMemoryLogRecordExporter, provider: LoggerProvider) -> list:
    provider.force_flush()
    return list(exporter.get_finished_logs())


def test_exported_record_keeps_level_logger_context_and_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exporter, provider = setup_export()
    try:
        raise ZeroDivisionError("division by zero")
    except ZeroDivisionError:
        logging.getLogger("fornada_api.conversations").error(
            "turn failed", extra={"conversation_id": "c0ffee"}, exc_info=True
        )

    (record,) = exported(exporter, provider)
    assert record.log_record.body == "turn failed"
    assert record.log_record.severity_text == "ERROR"
    assert record.instrumentation_scope is not None
    assert record.instrumentation_scope.name == "fornada_api.conversations"
    attributes = record.log_record.attributes or {}
    assert attributes["conversation_id"] == "c0ffee"
    assert attributes["exception.type"] == "ZeroDivisionError"
    assert "ZeroDivisionError" in str(attributes["exception.stacktrace"])
    assert one_record(capsys)["message"] == "turn failed"


def test_exported_record_inside_a_span_carries_its_trace_context() -> None:
    exporter, provider = setup_export()
    tracer = TracerProvider().get_tracer(__name__)
    with tracer.start_as_current_span("turn") as span:
        logging.getLogger("t").error("inside")
        context = span.get_span_context()
    logging.getLogger("t").error("outside")

    inside, outside = exported(exporter, provider)
    assert inside.log_record.trace_id == context.trace_id
    assert inside.log_record.span_id == context.span_id
    assert not outside.log_record.trace_id


def test_records_below_level_are_neither_exported_nor_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exporter, provider = setup_export("WARNING")
    logging.getLogger("t").info("quiet")
    assert exported(exporter, provider) == []
    assert lines(capsys) == []


def test_sdk_records_stay_local(capsys: pytest.CaptureFixture[str]) -> None:
    exporter, provider = setup_export()
    logging.getLogger("opentelemetry.exporter.otlp").warning("export failed")
    logging.getLogger("fornada_api.t").warning("kept")

    assert [r.log_record.body for r in exported(exporter, provider)] == ["kept"]
    assert [json.loads(line)["message"] for line in lines(capsys)] == ["export failed", "kept"]


def test_setup_with_export_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    exporter, provider = setup_export()
    configure_logging(LogSettings(), provider)
    logging.getLogger("t").info("once")

    assert len(exported(exporter, provider)) == 1
    assert len(lines(capsys)) == 1


def test_setup_without_a_provider_adds_no_export_handler() -> None:
    setup()
    assert [type(h).__name__ for h in logging.getLogger().handlers] == ["StreamHandler"]
