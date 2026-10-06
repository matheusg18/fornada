import logging

from fornada_api.core.config import get_settings
from fornada_api.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log)
    logger.info(
        "fornada-api starting",
        extra={
            "llm_provider": settings.llm.provider,
            "llm_model": settings.llm.active.model,
        },
    )
