"""`uv run task evals`: run the golden suite with DeepEval, then the reporter on its results.

    uv run task evals [--run-id ID] [--workers N] [pytest args, e.g. -k size-40-people]

Runs from the repo root, so the agent reads the root `.env` as the API does.
"""

import argparse
import datetime as dt
import os
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from fornada_evals import report

APP_DIR = Path(__file__).parents[2]
REPO_ROOT = APP_DIR.parents[1]
WORKERS_ENV = "EVALS__WORKERS"
DEFAULT_WORKERS = 4  # about 4 conversations in flight, within the provider's rate limits


def new_run_id() -> str:
    return f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:4]}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals", description="Run the golden suite.")
    parser.add_argument("--run-id", default=new_run_id())
    parser.add_argument(
        "--workers", type=int, default=int(os.environ.get(WORKERS_ENV, DEFAULT_WORKERS))
    )
    args, pytest_args = parser.parse_known_args(argv)

    deepeval = Path(sys.executable).parent / "deepeval"
    command = [
        str(deepeval), "test", "run", str(APP_DIR / "evals"),
        "-n", str(args.workers), "-id", args.run_id, "-d", "failing",
        *pytest_args,
    ]  # fmt: skip
    env = os.environ | {"DEEPEVAL_TELEMETRY_OPT_OUT": "1", "EVALS_RUN_ID": args.run_id}
    status = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False).returncode

    # pytest exits 1 when a critical run failed; the gate decides then. Anything else
    # (an interruption, a usage error such as a missing TEST_DATABASE_URI) wins.
    if status not in (0, 1):
        return status
    return report.main([args.run_id])


if __name__ == "__main__":
    raise SystemExit(main())
