"""`python -m fornada_simulator`: run the default batch and print the outcome counts."""

import asyncio
import logging
from collections import Counter
from pathlib import Path

from fornada_simulator.model import build_chat_model
from fornada_simulator.settings import get_settings
from fornada_simulator.simulate import run_batch

RUNS_DIR = Path("apps/simulator/runs")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings().simulator
    transcripts = await run_batch(settings, build_chat_model(settings), runs_dir=RUNS_DIR)
    print(f"{len(transcripts)} conversations -> {RUNS_DIR}")
    for outcome, count in Counter(t.outcome for t in transcripts).items():
        print(f"  {outcome}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
