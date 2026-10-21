"""Integration tests run against the test database (`postgres-test`), in throwaway
`eval_*` schemas. They are skipped when `TEST_DATABASE_URI` is not set; there is no
fallback to the dev database."""

import os

import pytest

TEST_DATABASE_URI = os.environ.get("TEST_DATABASE_URI")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(os.path.dirname(__file__)):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URI:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URI is not set"))


@pytest.fixture
def database_url() -> str:
    assert TEST_DATABASE_URI
    return TEST_DATABASE_URI
