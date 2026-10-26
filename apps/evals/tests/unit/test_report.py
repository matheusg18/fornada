import json
from pathlib import Path
from typing import Any

import pytest

from fornada_evals.report import (
    CheckResult,
    Gate,
    RunResult,
    load_runs,
    main,
    nearest_rank_p95,
    pass_at_1,
    pass_hat_k,
    render_markdown,
    summarize,
)

NO_GATE = Gate(min_noncritical_rate=None, max_cost_per_run_usd=None, max_p95_turn_latency_s=None)
REASON = "turn 2: check_capacity.date=2025-10-27 < run day 2026-10-21"


def run(
    case: str = "date-wrong-year-27-10",
    *,
    critical: bool = True,
    run_index: int = 0,
    passed: bool = True,
    run_id: str = "run-a",
    cost: float = 0.01,
    latencies_ms: list[float] | None = None,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        case=case,
        category="DATE",
        critical=critical,
        run_index=run_index,
        checks={"no_past_date": CheckResult(passed=passed, reason=None if passed else REASON)},
        failed=False,
        error=None,
        latencies_ms=latencies_ms if latencies_ms is not None else [1000.0],
        input_tokens=1000,
        output_tokens=100,
        cost_usd=cost,
        prompt_version="v0-abc123",
        model="claude-haiku",
        transcript=[
            {"role": "user", "content": "Quero um bolo para 27/10.", "tools": []},
            {
                "role": "assistant",
                "content": "Vou verificar.",
                "tools": [{"name": "check_capacity", "input": {"date": "2025-10-27"}}],
            },
        ],
    )


def critical_runs(*verdicts: bool, run_id: str = "run-a") -> list[RunResult]:
    return [run(run_index=i, passed=v, run_id=run_id) for i, v in enumerate(verdicts)]


def noncritical(passing: int, failing: int) -> list[RunResult]:
    return [run(f"case-{i}", critical=False, passed=i < passing) for i in range(passing + failing)]


class TestPassHatK:
    def test_all_runs_pass(self) -> None:
        assert pass_hat_k(n=3, c=3, k=3) == 1.0

    def test_one_failed_run_of_three(self) -> None:
        assert pass_hat_k(n=3, c=2, k=3) == 0.0

    def test_two_suite_runs_estimate_with_less_noise(self) -> None:
        # C(5, 3) / C(6, 3) = 10 / 20
        assert pass_hat_k(n=6, c=5, k=3) == 0.5

    def test_fewer_runs_than_k_has_no_estimate(self) -> None:
        assert pass_hat_k(n=2, c=2, k=3) is None

    def test_pass_at_1(self) -> None:
        assert pass_at_1(n=3, c=2) == pytest.approx(2 / 3)


class TestGate:
    def test_critical_case_with_one_failed_run_fails_the_gate(self) -> None:
        summary = summarize(critical_runs(True, True, False), NO_GATE)

        [case] = summary["cases"]
        assert case["runs"] == 3 and case["passed_runs"] == 2
        assert case["passed"] is False
        assert summary["gate"]["passed"] is False
        assert "critical cases" in summary["gate"]["failures"]

    def test_critical_case_passing_three_of_three_passes(self) -> None:
        summary = summarize(critical_runs(True, True, True), NO_GATE)

        [case] = summary["cases"]
        assert case["pass_hat_k"] == 1.0
        assert case["passed"] is True
        assert summary["gate"]["passed"] is True

    def test_noncritical_rate_below_minimum_fails(self) -> None:
        gate = Gate(
            min_noncritical_rate=0.8, max_cost_per_run_usd=None, max_p95_turn_latency_s=None
        )

        summary = summarize(noncritical(passing=7, failing=3), gate)

        assert summary["noncritical"]["rate"] == pytest.approx(0.7)
        assert summary["gate"]["failures"] == ["non-critical rate"]
        markdown = render_markdown(summary)
        assert "70%" in markdown and "80%" in markdown

    def test_mean_cost_above_ceiling_fails_naming_the_cost_check(self) -> None:
        gate = Gate(
            min_noncritical_rate=None, max_cost_per_run_usd=0.05, max_p95_turn_latency_s=None
        )

        summary = summarize(
            [run(critical=False, cost=0.06), run("other", critical=False, cost=0.06)], gate
        )

        assert summary["cost"]["mean_per_run_usd"] == pytest.approx(0.06)
        assert summary["gate"]["failures"] == ["cost"]

    def test_p95_above_ceiling_fails(self) -> None:
        gate = Gate(min_noncritical_rate=None, max_cost_per_run_usd=None, max_p95_turn_latency_s=5)

        summary = summarize([run(critical=False, latencies_ms=[1000.0, 6000.0])], gate)

        assert summary["gate"]["failures"] == ["p95 latency"]

    def test_empty_ceilings_report_without_gating(self) -> None:
        summary = summarize([run(critical=False, cost=9.0, latencies_ms=[60_000.0])], NO_GATE)

        assert summary["gate"]["passed"] is True
        assert summary["cost"]["max_usd"] is None
        assert "not gated" in render_markdown(summary)


def test_p95_uses_nearest_rank() -> None:
    # Nearest rank: the ceil(0.95 * 20) = 19th value. Interpolation would give 19.05.
    assert nearest_rank_p95([float(v) for v in range(1, 21)]) == 19.0


def test_flipping_case_counts_in_the_variance_share() -> None:
    first = [run("stable", run_id="run-a"), run("flips", run_id="run-a")]
    second = [run("stable", run_id="run-b"), run("flips", run_id="run-b", passed=False)]

    summary = summarize(first + second, NO_GATE)

    assert summary["variance"]["flipped"] == ["flips"]
    assert summary["variance"]["share"] == pytest.approx(1 / 2)


def test_single_run_id_has_no_variance() -> None:
    assert summarize(critical_runs(True, True, True), NO_GATE)["variance"] is None


def test_markdown_lists_failed_checks_with_reasons() -> None:
    markdown = render_markdown(summarize(critical_runs(True, True, False), NO_GATE))

    assert "date-wrong-year-27-10" in markdown
    assert "2/3" in markdown
    assert "no_past_date" in markdown
    assert REASON in markdown


def test_failed_run_counts_as_a_failure() -> None:
    crashed = run().model_copy(update={"failed": True, "error": "RuntimeError: provider down"})

    summary = summarize([crashed], NO_GATE)

    assert summary["cases"][0]["passed_runs"] == 0
    assert "provider down" in render_markdown(summary)


def write_run(reports: Path, run_id: str, results: list[RunResult]) -> None:
    folder = reports / run_id
    folder.mkdir(parents=True)
    lines = (result.model_dump_json() for result in results)
    (folder / "results-gw0.jsonl").write_text("\n".join(lines) + "\n")


def test_load_runs_reads_every_worker_file(tmp_path: Path) -> None:
    write_run(tmp_path, "run-a", critical_runs(True, True))
    (tmp_path / "run-a" / "results-gw1.jsonl").write_text(run(run_index=2).model_dump_json() + "\n")

    assert len(load_runs(tmp_path, ["run-a"])) == 3


@pytest.mark.parametrize(
    ("verdicts", "status"), [((True, True, True), 0), ((True, True, False), 1)]
)
def test_main_writes_the_report_and_exits_with_the_gate(
    tmp_path: Path, verdicts: tuple[bool, ...], status: int
) -> None:
    write_run(tmp_path, "run-a", critical_runs(*verdicts))
    gate = tmp_path / "gate.toml"
    gate.write_text("")

    assert main(["run-a", "--reports-dir", str(tmp_path), "--gate", str(gate)]) == status

    summary: dict[str, Any] = json.loads((tmp_path / "run-a" / "summary.json").read_text())
    assert summary["gate"]["passed"] is (status == 0)
    assert (tmp_path / "run-a" / "report.md").exists()
