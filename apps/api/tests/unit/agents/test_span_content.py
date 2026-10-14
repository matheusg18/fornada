"""Conversation content as GenAI semconv JSON (`agent-tracing` spec, content
capture)."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fornada_api.agents.attendant import span_content


def test_user_message() -> None:
    sent = span_content.input_messages([HumanMessage("Quero um bolo de chocolate")])
    assert json.loads(sent) == [
        {"role": "user", "parts": [{"type": "text", "content": "Quero um bolo de chocolate"}]}
    ]


def test_accents_stay_readable() -> None:
    assert "produção" in span_content.input_messages([HumanMessage("Está em produção?")])


def test_answer_with_text() -> None:
    answer = AIMessage("Temos bolo de chocolate.", response_metadata={"stop_reason": "end_turn"})
    assert json.loads(span_content.output_messages(answer)) == [
        {
            "role": "assistant",
            "parts": [{"type": "text", "content": "Temos bolo de chocolate."}],
            "finish_reason": "end_turn",
        }
    ]


def test_answer_with_two_tool_calls() -> None:
    answer = AIMessage(
        "",
        tool_calls=[
            {"name": "check_capacity", "args": {"date": "2026-10-20"}, "id": "toolu_01"},
            {"name": "calculate_quote", "args": {"weight_kg": 2.0}, "id": "toolu_02"},
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    [message] = json.loads(span_content.output_messages(answer))
    assert message["finish_reason"] == "tool_calls"
    assert message["parts"] == [
        {
            "type": "tool_call",
            "id": "toolu_01",
            "name": "check_capacity",
            "arguments": {"date": "2026-10-20"},
        },
        {
            "type": "tool_call",
            "id": "toolu_02",
            "name": "calculate_quote",
            "arguments": {"weight_kg": 2.0},
        },
    ]


def test_answer_without_finish_reason() -> None:
    [message] = json.loads(span_content.output_messages(AIMessage("Oi")))
    assert "finish_reason" not in message


def test_tool_message() -> None:
    result = ToolMessage('{"free_kg": 5.0}', tool_call_id="toolu_01")
    assert json.loads(span_content.input_messages([result])) == [
        {
            "role": "tool",
            "parts": [
                {"type": "tool_call_response", "id": "toolu_01", "response": '{"free_kg": 5.0}'}
            ],
        }
    ]


def test_history_keeps_order() -> None:
    history = [
        HumanMessage("Tem vaga dia 20?"),
        AIMessage("", tool_calls=[{"name": "check_capacity", "args": {}, "id": "toolu_01"}]),
        ToolMessage("5 kg", tool_call_id="toolu_01"),
    ]
    roles = [m["role"] for m in json.loads(span_content.input_messages(history))]
    assert roles == ["user", "assistant", "tool"]


def test_system_instructions() -> None:
    assert json.loads(span_content.system_instructions("Você é a atendente.")) == [
        {"type": "text", "content": "Você é a atendente."}
    ]


def test_text_messages() -> None:
    assert json.loads(span_content.text_messages("assistant", ["Oi!", "Posso ajudar?"])) == [
        {"role": "assistant", "parts": [{"type": "text", "content": "Oi!"}]},
        {"role": "assistant", "parts": [{"type": "text", "content": "Posso ajudar?"}]},
    ]
