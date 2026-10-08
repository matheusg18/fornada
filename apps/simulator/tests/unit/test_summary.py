from uuid import uuid4

from fornada_simulator.summary import format_transcript, summarize
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
