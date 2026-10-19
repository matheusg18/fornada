"""What a simulated conversation records, and how it is written to disk.

The transcripts are simulated, fictional data. They are the one place message
text is stored; the logging system never sees it.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Outcome = Literal["completed", "max_turns", "api_error", "simulator_error"]
Role = Literal["customer", "attendant"]


class Message(BaseModel):
    role: Role
    text: str
    # Position of an attendant reply within its turn (0, 1, ...); None for the customer.
    reply_index: int | None = None


class Transcript(BaseModel):
    run_id: str
    persona_id: str
    # The matrix cell; None for the persona batch and for files written before it.
    intent_id: str | None = None
    complication_id: str | None = None
    goal: str
    conversation_id: UUID
    outcome: Outcome
    messages: list[Message]
    turns: int
    elapsed_seconds: float


def append_jsonl(path: Path, transcript: Transcript) -> None:
    """Append one transcript as one JSON line, creating the folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(transcript.model_dump_json() + "\n")


CellKey = tuple[str, str | None, str | None]


def cell_key(transcript: Transcript) -> CellKey:
    return (transcript.persona_id, transcript.intent_id, transcript.complication_id)


def latest_per_cell(transcripts: Sequence[Transcript]) -> list[Transcript]:
    """A matrix run file appends a retried cell again: its last line counts.

    Order is the cells' first appearance. Persona batch lines share their key
    (no cell), so call this on matrix runs only.
    """
    latest: dict[CellKey, Transcript] = {}
    for transcript in transcripts:
        latest[cell_key(transcript)] = transcript
    return list(latest.values())


def read_jsonl(path: Path) -> list[Transcript]:
    with path.open(encoding="utf-8") as file:
        return [Transcript.model_validate_json(line) for line in file if line.strip()]
