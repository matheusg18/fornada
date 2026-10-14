"""JSON logging on stdout, built on the standard `logging` module, plus an
optional OTLP copy of every record for the Collector."""

import logging.config
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from pythonjsonlogger.json import JsonFormatter

from fornada_api.core.config import LogSettings


class FornadaJsonFormatter(JsonFormatter):
    """`JsonFormatter` where extra keys can never replace the standard fields.

    The library merges `extra` after the standard fields, so an extra named
    `level` would win. Put the standard values back after the merge.
    """

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_data, record, message_dict)
        log_data["level"] = record.levelname
        log_data["logger"] = record.name
        log_data["message"] = record.message
        log_data["timestamp"] = datetime.fromtimestamp(record.created, tz=UTC)
        if "exc_info" in message_dict:
            log_data["exception"] = message_dict["exc_info"]


class _NotTelemetrySdk(logging.Filter):
    """Reject the telemetry SDK's own records. A failing export logs a warning;
    exported, it would feed the next export and never stop."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name == "opentelemetry" or record.name.startswith("opentelemetry."))


def _otlp_handler(logger_provider: LoggerProvider) -> logging.Handler:
    # No formatter: the body is the plain message; the JSON shape is for stdout.
    handler = LoggingHandler(logger_provider=logger_provider)
    handler.addFilter(_NotTelemetrySdk())
    return handler


def configure_logging(settings: LogSettings, logger_provider: LoggerProvider | None = None) -> None:
    """Send every log record to stdout as one JSON object per line, and to the
    Collector over OTLP when a `logger_provider` is given.

    Safe to call more than once: `dictConfig` replaces the root handlers, the
    OTLP one included, so output is never duplicated.
    """
    handlers: dict[str, Any] = {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "json",
        }
    }
    if logger_provider is not None:
        handlers["otlp"] = {"()": _otlp_handler, "logger_provider": logger_provider}
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": FornadaJsonFormatter,
                    "fmt": "{levelname} {name} {message}",
                    "style": "{",
                    "timestamp": True,
                    "rename_fields": {
                        "levelname": "level",
                        "name": "logger",
                        "exc_info": "exception",
                    },
                    "json_ensure_ascii": False,
                }
            },
            "handlers": handlers,
            "root": {"level": settings.level, "handlers": list(handlers)},
        }
    )
