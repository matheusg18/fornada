"""Integration tests run against the dev container's Postgres, in throwaway `eval_*`
schemas. They are skipped when `DATABASE_URI` is not set (outside the dev container)."""

import os

import pytest

DATABASE_URI = os.environ.get("DATABASE_URI")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(os.path.dirname(__file__)):
            item.add_marker(pytest.mark.integration)
            if not DATABASE_URI:
                item.add_marker(pytest.mark.skip(reason="DATABASE_URI is not set"))


@pytest.fixture
def database_url() -> str:
    assert DATABASE_URI
    return DATABASE_URI
