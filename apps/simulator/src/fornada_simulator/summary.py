"""Aggregate transcripts per persona, for the notebook and the batch printout."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import groupby
from typing import get_args

from fornada_simulator.transcript import Outcome, Transcript


@dataclass(frozen=True)
class PersonaSummary:
    persona_id: str
    conversations: int
    outcomes: dict[Outcome, int] = field(default_factory=dict)
    avg_turns: float = 0.0
    avg_seconds: float = 0.0


def summarize(transcripts: Sequence[Transcript]) -> list[PersonaSummary]:
    """One row per persona, in order of first appearance; every outcome has a count."""
    by_persona = sorted(transcripts, key=lambda t: t.persona_id)
    first_seen = {}
    for transcript in transcripts:
        first_seen.setdefault(transcript.persona_id, len(first_seen))
    rows = []
    for persona_id, group in groupby(by_persona, key=lambda t: t.persona_id):
        items = list(group)
        rows.append(
            PersonaSummary(
                persona_id=persona_id,
                conversations=len(items),
                outcomes={o: sum(t.outcome == o for t in items) for o in get_args(Outcome)},
                avg_turns=round(sum(t.turns for t in items) / len(items), 1),
                avg_seconds=round(sum(t.elapsed_seconds for t in items) / len(items), 1),
            )
        )
    return sorted(rows, key=lambda row: first_seen[row.persona_id])


def format_transcript(transcript: Transcript) -> str:
    """The conversation as readable text, one block per message."""
    lines = [
        f"[{transcript.persona_id}] {transcript.goal}",
        f"outcome={transcript.outcome} turns={transcript.turns} "
        f"seconds={transcript.elapsed_seconds}",
        "",
    ]
    for message in transcript.messages:
        speaker = "CLIENTE " if message.role == "customer" else "ATENDENTE"
        lines.append(f"{speaker}: {message.text}")
    return "\n".join(lines)
