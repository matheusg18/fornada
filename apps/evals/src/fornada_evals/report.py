"""The suite's reporter: reads the result lines of one or more runs, applies the gate and
writes `report.md` and `summary.json` into the first run's folder.

    uv run task evals:report <run-id> [<run-id>...]

Critical cases gate on pass^3, non-critical cases on a minimum pass rate, and the mean cost
per run and the p95 turn latency on their ceilings in `gate.toml` (an empty ceiling reports
without gating). With two or more run ids it also lists the cases whose verdict flipped.
"""

import argparse
import json
import math
import tomllib
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepeval.test_case import ConversationalTestCase
from pydantic import BaseModel

APP_DIR = Path(__file__).parents[2]
REPORTS_DIR = APP_DIR / "reports"
GATE_FILE = APP_DIR / "gate.toml"
K = 3  # critical cases run 3 times and pass only when all 3 pass


class CheckResult(BaseModel):
    passed: bool
    reason: str | None = None


class RunResult(BaseModel):
    """One result line: one run of one case, as the suite appends it."""

    run_id: str
    case: str
    category: str
    critical: bool
    run_index: int
    checks: dict[str, CheckResult]
    failed: bool  # the run itself raised (model provider, graph), with `error`
    error: str | None
    latencies_ms: list[float]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    prompt_version: str
    model: str
    # Each turn: role, content and, for the assistant, its tool calls (name, input, status).
    transcript: list[dict[str, Any]]

    @property
    def passed(self) -> bool:
        return not self.failed and all(check.passed for check in self.checks.values())


def run_result(
    test_case: ConversationalTestCase, run_id: str, checks: dict[str, CheckResult]
) -> RunResult:
    """The result line for a case run by `run_case` and measured by its checks."""
    metadata = test_case.metadata or {}
    case = metadata["case"]
    transcript = [
        {
            "role": turn.role,
            "content": turn.content,
            "tools": [
                {"name": call.name, "input": call.input_parameters, "status": status}
                for call, status in zip(
                    turn.tools_called or [],
                    (turn.metadata or {}).get("tool_status", []),
                    strict=False,
                )
            ],
        }
        for turn in test_case.turns
    ]
    return RunResult(
        run_id=run_id,
        case=test_case.name or "",
        category=case["category"],
        critical=case["critical"],
        run_index=metadata["run_index"],
        checks=checks,
        failed=metadata["failed"],
        error=metadata["error"],
        latencies_ms=metadata["latencies_ms"],
        input_tokens=metadata["input_tokens"],
        output_tokens=metadata["output_tokens"],
        cost_usd=metadata["cost_usd"],
        prompt_version=metadata["prompt_version"],
        model=metadata["model"],
        transcript=transcript,
    )


@dataclass(frozen=True)
class Gate:
    min_noncritical_rate: float | None
    max_cost_per_run_usd: float | None
    max_p95_turn_latency_s: float | None


def load_gate(path: Path) -> Gate:
    settings = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return Gate(
        min_noncritical_rate=settings.get("min_noncritical_rate"),
        max_cost_per_run_usd=settings.get("max_cost_per_run_usd"),
        max_p95_turn_latency_s=settings.get("max_p95_turn_latency_s"),
    )


def load_runs(reports_dir: Path, run_ids: Sequence[str]) -> list[RunResult]:
    """Every result line of the given runs, from all their per-worker files."""
    results: list[RunResult] = []
    for run_id in run_ids:
        files = sorted((reports_dir / run_id).glob("results-*.jsonl"))
        if not files:
            raise FileNotFoundError(f"no result lines in {reports_dir / run_id}")
        for file in files:
            lines = file.read_text(encoding="utf-8").splitlines()
            results += [RunResult.model_validate_json(line) for line in lines if line.strip()]
    return results


def pass_hat_k(n: int, c: int, k: int = K) -> float | None:
    """pass^k, τ-bench's unbiased estimator: the chance that k runs drawn from the n made
    (c of them passing) all pass, C(c, k) / C(n, k). With n = k it is 1 only when every
    run passed; more runs estimate the same quantity with less noise. None when n < k."""
    if n < k:
        return None
    return math.comb(c, k) / math.comb(n, k)


def pass_at_1(n: int, c: int) -> float:
    return c / n


def nearest_rank_p95(values: Sequence[float]) -> float | None:
    """The 95th percentile by nearest rank: the ceil(0.95 * N)-th smallest value."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(results: Sequence[RunResult], gate: Gate) -> dict[str, Any]:
    by_case: dict[str, list[RunResult]] = defaultdict(list)
    for result in results:
        by_case[result.case].append(result)

    cases = [_case_summary(name, runs) for name, runs in sorted(by_case.items())]
    critical = [case for case in cases if case["critical"]]
    noncritical_runs = [result for result in results if not result.critical]
    rate = (
        sum(result.passed for result in noncritical_runs) / len(noncritical_runs)
        if noncritical_runs
        else None
    )
    mean_cost = sum(result.cost_usd for result in results) / len(results) if results else 0.0
    p95_ms = nearest_rank_p95([ms for result in results for ms in result.latencies_ms])
    p95_s = None if p95_ms is None else p95_ms / 1000

    # Each ceiling or minimum gates only when it is set and there is a value to compare.
    checks = {
        "critical cases": not all(case["passed"] for case in critical),
        "non-critical rate": _beyond(gate.min_noncritical_rate, rate, lambda v, m: v < m),
        "cost": _beyond(gate.max_cost_per_run_usd, mean_cost, lambda v, m: v > m),
        "p95 latency": _beyond(gate.max_p95_turn_latency_s, p95_s, lambda v, m: v > m),
    }
    failures = [name for name, failed in checks.items() if failed]

    return {
        "run_ids": sorted({result.run_id for result in results}),
        "prompt_versions": sorted({result.prompt_version for result in results}),
        "models": sorted({result.model for result in results}),
        "gate": {"passed": not failures, "failures": failures},
        "critical": {
            "cases": len(critical),
            "passed": sum(case["passed"] for case in critical),
            "k": K,
        },
        "noncritical": {
            "cases": len(cases) - len(critical),
            "runs": len(noncritical_runs),
            "rate": rate,
            "min_rate": gate.min_noncritical_rate,
        },
        "cost": {
            "mean_per_run_usd": mean_cost,
            "total_usd": sum(result.cost_usd for result in results),
            "max_usd": gate.max_cost_per_run_usd,
        },
        "latency": {"p95_turn_s": p95_s, "max_s": gate.max_p95_turn_latency_s},
        "variance": _variance(by_case),
        "cases": cases,
    }


def _beyond(
    limit: float | None, value: float | None, fails: Callable[[float, float], bool]
) -> bool:
    return limit is not None and value is not None and fails(value, limit)


def _case_summary(name: str, runs: list[RunResult]) -> dict[str, Any]:
    runs = sorted(runs, key=lambda result: (result.run_id, result.run_index))
    n, c = len(runs), sum(result.passed for result in runs)
    critical = runs[0].critical
    estimate = pass_hat_k(n, c)
    return {
        "name": name,
        "category": runs[0].category,
        "critical": critical,
        "runs": n,
        "passed_runs": c,
        "pass_hat_k": estimate,
        "pass_at_1": pass_at_1(n, c),
        # A critical case with fewer than k runs has no pass^k, so it cannot pass.
        "passed": estimate == 1.0 if critical else c == n,
        "failed_runs": [
            {
                "run_id": result.run_id,
                "run_index": result.run_index,
                "error": result.error,
                "checks": {
                    check_id: check.reason
                    for check_id, check in result.checks.items()
                    if not check.passed
                },
                "transcript": result.transcript,
            }
            for result in runs
            if not result.passed
        ],
    }


def _variance(by_case: dict[str, list[RunResult]]) -> dict[str, Any] | None:
    """Cases whose verdict (every run passed) differs between the suite runs given."""
    if len({result.run_id for runs in by_case.values() for result in runs}) < 2:
        return None
    compared: list[str] = []
    flipped: list[str] = []
    for name, runs in sorted(by_case.items()):
        verdicts: dict[str, bool] = {}
        for result in runs:
            verdicts[result.run_id] = verdicts.get(result.run_id, True) and result.passed
        if len(verdicts) < 2:
            continue
        compared.append(name)
        if len(set(verdicts.values())) > 1:
            flipped.append(name)
    return {
        "compared": len(compared),
        "flipped": flipped,
        "share": len(flipped) / len(compared) if compared else None,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    gate = summary["gate"]
    critical = summary["critical"]
    noncritical = summary["noncritical"]
    cost = summary["cost"]
    latency = summary["latency"]
    verdict = "PASSED" if gate["passed"] else f"FAILED ({', '.join(gate['failures'])})"
    lines = [
        f"# Eval report: {', '.join(summary['run_ids'])}",
        "",
        f"**Gate: {verdict}**",
        "",
        f"- Prompt version: {', '.join(summary['prompt_versions'])}",
        f"- Model: {', '.join(summary['models'])}",
        "",
        "| Check | Value | Ceiling or minimum | Result |",
        "|---|---|---|---|",
        f"| Critical cases (pass^{critical['k']}) | {critical['passed']}/{critical['cases']} "
        f"| all | {_result(critical['passed'] == critical['cases'])} |",
        _gate_row(
            "Non-critical pass rate",
            noncritical["rate"],
            noncritical["min_rate"],
            _percent,
            lambda value, limit: value >= limit,
        ),
        _gate_row(
            "Mean cost per run",
            cost["mean_per_run_usd"],
            cost["max_usd"],
            lambda value: f"US$ {value:.4f}",
            lambda value, limit: value <= limit,
        ),
        _gate_row(
            "p95 turn latency",
            latency["p95_turn_s"],
            latency["max_s"],
            lambda value: f"{value:.1f} s",
            lambda value, limit: value <= limit,
        ),
        "",
        f"Total cost: US$ {cost['total_usd']:.4f}.",
        "",
        "## Cases",
        "",
        f"| Case | Category | Critical | Runs passed | pass^{critical['k']} | pass@1 |",
        "|---|---|---|---|---|---|",
    ]
    for case in summary["cases"]:
        estimate = "—" if case["pass_hat_k"] is None else f"{case['pass_hat_k']:.2f}"
        lines.append(
            f"| {'' if case['passed'] else '❌ '}`{case['name']}` | {case['category']} "
            f"| {'yes' if case['critical'] else 'no'} | {case['passed_runs']}/{case['runs']} "
            f"| {estimate} | {case['pass_at_1']:.2f} |"
        )

    failed = [(case, run) for case in summary["cases"] for run in case["failed_runs"]]
    if failed:
        lines += ["", "## Failed runs"]
        for case, run in failed:
            lines += ["", f"### `{case['name']}`, {run['run_id']} run {run['run_index'] + 1}", ""]
            if run["error"]:
                lines.append(f"- run failed: {run['error']}")
            lines += [f"- `{check_id}`: {reason}" for check_id, reason in run["checks"].items()]
            lines += ["", "<details><summary>Conversation</summary>", ""]
            lines += [_turn(turn) for turn in run["transcript"]]
            lines += ["", "</details>"]

    variance = summary["variance"]
    if variance is not None:
        share = "—" if variance["share"] is None else _percent(variance["share"])
        lines += [
            "",
            "## Variance",
            "",
            f"{len(variance['flipped'])} of {variance['compared']} cases changed verdict "
            f"between runs ({share}).",
        ]
        lines += [f"- `{name}`" for name in variance["flipped"]]
    return "\n".join(lines) + "\n"


def _gate_row(label: str, value: Any, limit: Any, fmt: Any, ok: Any) -> str:
    shown = "—" if value is None else fmt(value)
    if limit is None:
        return f"| {label} | {shown} | — | not gated |"
    result = "—" if value is None else _result(ok(value, limit))
    return f"| {label} | {shown} | {fmt(limit)} | {result} |"


def _result(ok: bool) -> str:
    return "pass" if ok else "**fail**"


def _percent(value: float) -> str:
    return f"{value:.0%}"


def _turn(turn: dict[str, Any]) -> str:
    speaker = "Cliente" if turn["role"] == "user" else "Bot"
    tools = "".join(
        f"\n  - `{tool['name']}({json.dumps(tool['input'], ensure_ascii=False)})`"
        f"{' → ' + tool['status'] if tool.get('status') else ''}"
        for tool in turn.get("tools", [])
    )
    content = " ".join(str(turn["content"]).split())
    return f"- **{speaker}:** {content}{tools}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals:report", description="Gate and report eval runs.")
    parser.add_argument("run_ids", nargs="+", metavar="run-id")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--gate", type=Path, default=GATE_FILE)
    args = parser.parse_args(argv)

    summary = summarize(load_runs(args.reports_dir, args.run_ids), load_gate(args.gate))
    folder = args.reports_dir / args.run_ids[0]
    (folder / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = render_markdown(summary)
    (folder / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown.split("\n## Cases")[0])
    print(f"Full report: {folder / 'report.md'}")
    return 0 if summary["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
