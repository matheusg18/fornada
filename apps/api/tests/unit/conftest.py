"""Shared unit-test fixtures. Span fixtures live in `tests/conftest.py`."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
