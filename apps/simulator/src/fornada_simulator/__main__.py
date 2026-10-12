"""`python -m fornada_simulator`: run the default batch and print the outcome counts."""

import asyncio
import logging
from collections import Counter
from pathlib import Path

from fornada_simulator.model import build_chat_model
from fornada_simulator.settings import get_settings
from fornada_simulator.simulate import run_batch
from fornada_simulator.telemetry import setup_tracing, shutdown_tracing

RUNS_DIR = Path("apps/simulator/runs")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    # None when TELEMETRY__ENABLED is off.
    provider = setup_tracing(settings.telemetry)
    try:
        transcripts = await run_batch(
            settings.simulator, build_chat_model(settings.simulator), runs_dir=RUNS_DIR
        )
    finally:
        # Exports what is still buffered, then stops the pipeline.
        if provider is not None:
            shutdown_tracing(provider)
    print(f"{len(transcripts)} conversations -> {RUNS_DIR}")
    for outcome, count in Counter(t.outcome for t in transcripts).items():
        print(f"  {outcome}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
