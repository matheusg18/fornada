"""Session setup for the golden suite: the test database, the run id and the sweep."""

import asyncio
import os
from pathlib import Path

import pytest

from fornada_evals.isolation import require_test_database_url, sweep
from fornada_evals.report import REPORTS_DIR

RUN_ID_ENV = "EVALS_RUN_ID"

# DeepEval checks this when it sends an event, so setting it here covers a plain pytest run
# too; `uv run task evals` also sets it for the whole process.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")


def pytest_configure(config: pytest.Config) -> None:
    # Fail before any case, and sweep once: on the controller, not on each xdist worker,
    # where a worker's sweep would drop the schemas its siblings are using.
    if hasattr(config, "workerinput"):
        return
    try:
        database_url = require_test_database_url()
    except RuntimeError as error:
        raise pytest.UsageError(str(error)) from None
    if not os.environ.get(RUN_ID_ENV):
        raise pytest.UsageError(f"{RUN_ID_ENV} is not set; run the suite with `uv run task evals`")
    if dropped := asyncio.run(sweep(database_url)):
        print(f"swept {len(dropped)} leftover eval schemas")


@pytest.fixture(scope="session")
def database_url() -> str:
    return require_test_database_url()


@pytest.fixture(scope="session")
def results_file() -> Path:
    """This worker's result lines: one file per xdist worker, so appends never interleave."""
    folder = REPORTS_DIR / os.environ[RUN_ID_ENV]
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"results-{os.environ.get('PYTEST_XDIST_WORKER', 'main')}.jsonl"
