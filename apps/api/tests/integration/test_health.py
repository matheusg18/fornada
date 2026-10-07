import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from fornada_api.core.config import ConfigError
from fornada_api.infrastructure.engine import APPLICATION_NAME
from fornada_api.main import app

DATABASE_URI = os.environ.get("DATABASE_URI")


def test_seeded_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/db")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["tables"]) == 11
    assert body["tables"]["products"] == 12
    assert body["tables"]["neighborhoods"] == 8


def test_no_personal_data_in_response() -> None:
    assert DATABASE_URI
    with psycopg.connect(DATABASE_URI) as conn:
        customers = conn.execute("SELECT name, phone FROM customers").fetchall()
        addresses = conn.execute(
            "SELECT address FROM orders WHERE address IS NOT NULL"
        ).fetchall()
    with TestClient(app) as client:
        text = client.get("/health/db").text
    for value in [v for row in customers + addresses for v in row]:
        assert value not in text


def test_database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB__URL", "postgresql://x:pw-SEC@127.0.0.1:1/x")
    with TestClient(app) as client:
        response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "tables": {}}
    assert "pw-SEC" not in response.text
    assert "127.0.0.1" not in response.text


def count_app_connections() -> int:
    assert DATABASE_URI
    with psycopg.connect(DATABASE_URI) as conn:
        row = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s",
            (APPLICATION_NAME,),
        ).fetchone()
    assert row is not None
    return row[0]


def test_no_connection_left_after_shutdown() -> None:
    with TestClient(app) as client:
        assert client.get("/health/db").status_code == 200
        assert count_app_connections() >= 1  # pooled while the app runs
    assert count_app_connections() == 0


def test_startup_without_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DB__URL")
    monkeypatch.chdir(tmp_path)  # no root `.env` that could supply it
    with pytest.raises(ConfigError, match="DB__URL"):
        with TestClient(app):
            pass
