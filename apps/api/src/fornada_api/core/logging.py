"""JSON logging on stdout, built on the standard `logging` module."""

import logging.config
import sys
from datetime import UTC, datetime
from typing import Any

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


def configure_logging(settings: LogSettings) -> None:
    """Send every log record to stdout as one JSON object per line.

    Safe to call more than once: `dictConfig` replaces the root handlers.
    """
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
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "json",
                }
            },
            "root": {"level": settings.level, "handlers": ["stdout"]},
        }
    )
