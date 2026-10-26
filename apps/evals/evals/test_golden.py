"""The golden suite: every case against the real agent, critical cases 3 times.

Paid (it calls the configured model), so it never runs from `task check`. Run it with
`uv run task evals` from apps/evals, which runs `deepeval test run` and then the reporter.
"""

import asyncio
import os
import warnings
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.metrics import BaseConversationalMetric

from fornada_evals.checks import CHECKS, Check
from fornada_evals.dataset import GoldenCase, load_cases
from fornada_evals.report import CheckResult, run_result
from fornada_evals.runner import run_case

GOLDEN = Path(__file__).parents[1] / "datasets" / "golden.jsonl"
CRITICAL_RUNS = 3


def _runs() -> list[object]:
    return [
        pytest.param(case, run_index, id=f"{case.name}-run{run_index + 1}")
        for case in load_cases(GOLDEN)
        for run_index in range(CRITICAL_RUNS if case.metadata.critical else 1)
    ]


def _metrics(case: GoldenCase) -> list[Check]:
    return [CHECKS[check_id]() for check_id in case.metadata.checks]


@pytest.mark.parametrize(("case", "run_index"), _runs())
def test_golden(case: GoldenCase, run_index: int, database_url: str, results_file: Path) -> None:
    test_case = asyncio.run(run_case(case, run_index, database_url=database_url))
    # A non-critical case gates on the rate in the report; in pytest it only warns.
    test_case.flaky = not case.metadata.critical

    # The verdicts for the result line come from our own instances: `assert_test` scores
    # copies of the metrics it is given, and raises before we could read them.
    checks: dict[str, CheckResult] = {}
    for metric in _metrics(case):
        try:
            metric.measure(test_case)
            passed = metric.is_successful()
            checks[metric.check_id] = CheckResult(
                passed=passed, reason=None if passed else metric.reason
            )
        except Exception as error:
            checks[metric.check_id] = CheckResult(
                passed=False, reason=f"check raised {type(error).__name__}: {error}"
            )
    result = run_result(test_case, os.environ["EVALS_RUN_ID"], checks)
    with results_file.open("a", encoding="utf-8") as file:
        file.write(result.model_dump_json() + "\n")

    if result.failed:
        # The checks only saw the turns before the error, so they cannot clear the run.
        message = f"run failed: {result.error}"
        if case.metadata.critical:
            pytest.fail(message)
        warnings.warn(message, stacklevel=1)
    # `List` is invariant: hand DeepEval the list typed as its own base class.
    metrics: list[BaseConversationalMetric] = [*_metrics(case)]
    assert_test(test_case, metrics, run_async=False)
