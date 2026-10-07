"""Operational endpoints. They return counts, never row contents."""

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from fornada_api.dependencies import DbSessionDep
from fornada_api.models import Base

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class DbHealth(BaseModel):
    status: Literal["ok", "unavailable"]
    tables: dict[str, int]


@router.get(
    "/db",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": DbHealth}},
)
async def db_health(session: DbSessionDep, response: Response) -> DbHealth:
    """Load through every model and count the rows of each app table."""
    tables: dict[str, int] = {}
    try:
        for mapper in sorted(Base.registry.mappers, key=lambda m: m.class_.__tablename__):
            model = mapper.class_
            count = await session.execute(select(func.count()).select_from(model))
            tables[model.__tablename__] = count.scalar_one()
            # Selects every mapped column, so a model that drifted from the
            # schema fails here.
            (await session.scalars(select(model).limit(1))).first()
    except (SQLAlchemyError, OSError):
        # The driver's message names the host; keep it in the logs only.
        logger.exception("database health check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DbHealth(status="unavailable", tables={})
    return DbHealth(status="ok", tables=tables)
