"""Aggregate transcripts per persona or per matrix axis, for the notebook and
the batch printouts."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import groupby
from typing import get_args

from fornada_simulator.transcript import Outcome, Transcript, latest_per_cell


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


@dataclass(frozen=True)
class AxisSummary:
    value: str
    conversations: int
    outcomes: dict[Outcome, int] = field(default_factory=dict)


def summarize_by(
    transcripts: Sequence[Transcript], key: Callable[[Transcript], str | None]
) -> list[AxisSummary]:
    """One row per value of `key` (an intent or a complication), in order of
    first appearance. A cell recorded more than once counts by its last line."""
    groups: dict[str, list[Transcript]] = {}
    for transcript in latest_per_cell(transcripts):
        groups.setdefault(str(key(transcript)), []).append(transcript)
    return [
        AxisSummary(
            value=value,
            conversations=len(items),
            outcomes={o: sum(t.outcome == o for t in items) for o in get_args(Outcome)},
        )
        for value, items in groups.items()
    ]


def format_axis(title: str, rows: Sequence[AxisSummary]) -> str:
    """A plain-text table: one row per value, one column per outcome."""
    outcomes = get_args(Outcome)
    width = max([len(title), *(len(row.value) for row in rows)])
    lines = [f"{title:<{width}}  total  " + "  ".join(outcomes)]
    for row in rows:
        counts = "  ".join(f"{row.outcomes[o]:>{len(o)}}" for o in outcomes)
        lines.append(f"{row.value:<{width}}  {row.conversations:>5}  {counts}")
    return "\n".join(lines)


def cell_parts(transcript: Transcript) -> tuple[str | None, ...]:
    return (transcript.persona_id, transcript.intent_id, transcript.complication_id)


def format_transcript(transcript: Transcript) -> str:
    """The conversation as readable text, one block per message."""
    lines = [
        f"[{' / '.join(filter(None, cell_parts(transcript)))}] {transcript.goal}",
        f"outcome={transcript.outcome} turns={transcript.turns} "
        f"seconds={transcript.elapsed_seconds}",
        "",
    ]
    for message in transcript.messages:
        speaker = "CLIENTE " if message.role == "customer" else "ATENDENTE"
        lines.append(f"{speaker}: {message.text}")
    return "\n".join(lines)
