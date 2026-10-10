"""What a simulated conversation records, and how it is written to disk.

The transcripts are simulated, fictional data. They are the one place message
text is stored; the logging system never sees it.
"""

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


def read_jsonl(path: Path) -> list[Transcript]:
    with path.open(encoding="utf-8") as file:
        return [Transcript.model_validate_json(line) for line in file if line.strip()]
