import json
from pathlib import Path
from uuid import uuid4

from fornada_simulator.transcript import Message, Transcript, append_jsonl, read_jsonl


def make_transcript() -> Transcript:
    return Transcript(
        run_id="20261008T120000-ab12",
        persona_id="apressada",
        goal="um bolo para amanhã",
        conversation_id=uuid4(),
        outcome="completed",
        messages=[
            Message(role="customer", text="bolo amanhã"),
            Message(role="attendant", text="Claro!", reply_index=0),
            Message(role="attendant", text="Qual sabor?", reply_index=1),
        ],
        turns=1,
        elapsed_seconds=2.5,
    )


def test_one_parseable_line_with_every_field(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "batch.jsonl"
    append_jsonl(path, make_transcript())
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {
        "run_id",
        "persona_id",
        "goal",
        "conversation_id",
        "outcome",
        "messages",
        "turns",
        "elapsed_seconds",
    }
    assert [m["reply_index"] for m in record["messages"]] == [None, 0, 1]


def test_appending_twice_gives_two_lines_that_read_back(tmp_path: Path) -> None:
    path = tmp_path / "batch.jsonl"
    first, second = make_transcript(), make_transcript()
    append_jsonl(path, first)
    append_jsonl(path, second)
    assert len(path.read_text().splitlines()) == 2
    assert read_jsonl(path) == [first, second]
