"""`python -m fornada_simulator.matrix`: run the persona x intent x complication matrix.

Without `--complications`, the 100 cells that need a working API; the 25
`ferramenta_fora` cells run in a second launch against an API in chaos mode,
resuming the same run (`--run-id`). See the README for the two launches.
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from fornada_simulator.model import build_chat_model
from fornada_simulator.scenarios import COMPLICATIONS, Cell, UnknownComplicationError, plan_matrix
from fornada_simulator.settings import get_settings
from fornada_simulator.simulate import run_matrix
from fornada_simulator.summary import format_axis, summarize_by
from fornada_simulator.telemetry import setup_tracing, shutdown_tracing
from fornada_simulator.transcript import read_jsonl

RUNS_DIR = Path("apps/simulator/runs")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fornada_simulator.matrix",
        description="Run the persona x intent x complication matrix against the API.",
    )
    parser.add_argument(
        "--complications",
        type=lambda value: [part.strip() for part in value.split(",") if part.strip()],
        help=(
            "comma-separated complication ids to run; default: every one but "
            f"ferramenta_fora. Known: {', '.join(c.id for c in COMPLICATIONS)}"
        ),
    )
    parser.add_argument("--run-id", help="resume this run: skip the cells it already finished")
    parser.add_argument(
        "--limit", type=int, help="run at most this many pending cells (the cost pilot)"
    )
    return parser.parse_args(argv)


def plan(args: argparse.Namespace) -> list[Cell]:
    """The cells to run; an unknown complication stops the launch here."""
    try:
        return plan_matrix(args.complications)
    except UnknownComplicationError as exc:
        raise SystemExit(f"error: {exc}") from None


async def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    # Validated before the settings, the model or any connection.
    cells = plan(args)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    provider = setup_tracing(settings.telemetry)
    try:
        run_id, transcripts = await run_matrix(
            settings.simulator,
            build_chat_model(settings.simulator),
            cells,
            runs_dir=RUNS_DIR,
            run_id=args.run_id,
            limit=args.limit,
        )
    finally:
        if provider is not None:
            shutdown_tracing(provider)
    path = RUNS_DIR / f"{run_id}.jsonl"
    print(f"{len(transcripts)} conversations this launch -> {path}")
    # The whole run, retried cells counted once.
    recorded = read_jsonl(path) if path.exists() else []
    print(format_axis("complication", summarize_by(recorded, lambda t: t.complication_id)))
    print(format_axis("intent", summarize_by(recorded, lambda t: t.intent_id)))


if __name__ == "__main__":
    asyncio.run(main())
