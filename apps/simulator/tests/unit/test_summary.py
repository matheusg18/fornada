from uuid import uuid4

from fornada_simulator.summary import format_axis, format_transcript, summarize, summarize_by
from fornada_simulator.transcript import Message, Outcome, Transcript


def make(persona_id: str, outcome: Outcome, turns: int, seconds: float) -> Transcript:
    return Transcript(
        run_id="r",
        persona_id=persona_id,
        goal="g",
        conversation_id=uuid4(),
        outcome=outcome,
        messages=[],
        turns=turns,
        elapsed_seconds=seconds,
    )


def test_one_row_per_persona_with_counts_and_averages() -> None:
    rows = summarize(
        [
            make("malandro", "completed", 4, 10.0),
            make("apressada", "completed", 2, 4.0),
            make("malandro", "max_turns", 12, 30.0),
            make("apressada", "api_error", 1, 2.0),
        ]
    )
    assert [row.persona_id for row in rows] == ["malandro", "apressada"]
    malandro, apressada = rows
    assert malandro.conversations == 2
    assert malandro.outcomes == {
        "completed": 1,
        "max_turns": 1,
        "api_error": 0,
        "simulator_error": 0,
    }
    assert (malandro.avg_turns, malandro.avg_seconds) == (8.0, 20.0)
    assert apressada.outcomes["api_error"] == 1
    assert apressada.avg_turns == 1.5


def test_empty_input_gives_no_rows() -> None:
    assert summarize([]) == []


def test_format_transcript_shows_outcome_and_speakers() -> None:
    transcript = make("apressada", "completed", 1, 2.0).model_copy(
        update={
            "messages": [
                Message(role="customer", text="oi"),
                Message(role="attendant", text="olá!", reply_index=0),
            ]
        }
    )
    text = format_transcript(transcript)
    assert "outcome=completed" in text
    assert "CLIENTE : oi" in text
    assert "ATENDENTE: olá!" in text


def cell(
    intent: str, complication: str, outcome: Outcome, persona: str = "apressada"
) -> Transcript:
    return make(persona, outcome, 1, 1.0).model_copy(
        update={"intent_id": intent, "complication_id": complication}
    )


def test_rows_per_complication_and_per_intent() -> None:
    transcripts = [
        cell("retirada", "nenhuma", "completed"),
        cell("retirada", "data_lotada", "max_turns"),
        cell("entrega", "nenhuma", "completed"),
        cell("entrega", "data_lotada", "completed", persona="indecisa"),
    ]
    by_complication = summarize_by(transcripts, lambda t: t.complication_id)
    assert [(r.value, r.conversations) for r in by_complication] == [
        ("nenhuma", 2),
        ("data_lotada", 2),
    ]
    assert by_complication[1].outcomes["max_turns"] == 1
    by_intent = summarize_by(transcripts, lambda t: t.intent_id)
    assert [(r.value, r.outcomes["completed"]) for r in by_intent] == [
        ("retirada", 1),
        ("entrega", 2),
    ]


def test_a_retried_cell_counts_by_its_last_line() -> None:
    rows = summarize_by(
        [cell("retirada", "nenhuma", "api_error"), cell("retirada", "nenhuma", "completed")],
        lambda t: t.complication_id,
    )
    (row,) = rows
    assert row.conversations == 1
    assert row.outcomes["completed"] == 1
    assert row.outcomes["api_error"] == 0


def test_format_axis_has_a_row_per_value() -> None:
    text = format_axis(
        "intent", summarize_by([cell("retirada", "nenhuma", "completed")], lambda t: t.intent_id)
    )
    header, row = text.splitlines()
    assert header.split()[:2] == ["intent", "total"]
    assert row.split()[:3] == ["retirada", "1", "1"]
