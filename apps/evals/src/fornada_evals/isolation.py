"""One PostgreSQL schema per case run, loaded from the dev schema and seed.

Each run gets `eval_<hex>` in the `fornada` database, with its own copy of the seed, so
runs cannot see each other's orders (parallel tool calls and xdist workers included) and
`public` is never touched. The role owns the database, so it can create schemas without
`CREATEDB`. See the `add-eval-harness` design, decision 3.
"""

import datetime as dt
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg
from fornada_api.infrastructure.engine import drop_server_detail, to_async_url
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQL_DIR = Path(__file__).resolve().parents[4] / ".devcontainer" / "db"
SCHEMA_PREFIX = "eval_"
APPLICATION_NAME = "fornada-evals"


@dataclass(frozen=True)
class CaseDatabase:
    schema: str
    run_day: dt.date  # the seed's "today"; every relative date in it counts from here
    sessionmaker: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def isolated_database(database_url: str) -> AsyncGenerator[CaseDatabase]:
    """A freshly seeded schema for one run, dropped on exit even when the run raises."""
    schema = f"{SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    engine = None
    try:
        run_day = await _create_and_seed(database_url, schema)
        engine = create_async_engine(
            to_async_url(database_url),
            connect_args={
                "application_name": APPLICATION_NAME,
                "options": f"-c search_path={schema}",
            },
            # As in the API: errors keep the SQL text but not the bound values.
            hide_parameters=True,
        )
        event.listen(engine.sync_engine, "handle_error", drop_server_detail)
        yield CaseDatabase(
            schema=schema,
            run_day=run_day,
            sessionmaker=async_sessionmaker(engine, expire_on_commit=False, autoflush=False),
        )
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop(database_url, [schema])


async def sweep(database_url: str) -> list[str]:
    """Drop every `eval_*` schema, left behind by a killed run. Call it only when no
    run is in flight (once per suite, before the workers start): it drops live ones too."""
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        cursor = await conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE %s",
            (SCHEMA_PREFIX.replace("_", "\\_") + "%",),
        )
        names = [row[0] for row in await cursor.fetchall()]
    await _drop(database_url, names)
    return names


async def _create_and_seed(database_url: str, schema: str) -> dt.date:
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        await conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        # Multi-statement scripts with their own BEGIN/COMMIT; no parameters, so psycopg
        # sends each file as one simple query.
        await conn.execute((SQL_DIR / "schema.sql").read_bytes())
        await conn.execute((SQL_DIR / "seed.sql").read_bytes())
        # The seed sets the session's time zone to America/Sao_Paulo and dates everything
        # from CURRENT_DATE there; read it in the same session so the run day matches.
        cursor = await conn.execute("SELECT CURRENT_DATE")
        row = await cursor.fetchone()
    assert row is not None
    return row[0]


async def _drop(database_url: str, schemas: list[str]) -> None:
    if not schemas:
        return
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        for schema in schemas:
            await conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )
