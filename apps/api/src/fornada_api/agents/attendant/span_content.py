"""Conversation content as GenAI semconv JSON, for the content attributes in
`tracing`. Only built with content capture on.

Shapes follow the input and output message schemas in
`open-telemetry/semantic-conventions-genai` (same commit as `tracing`): a
message is `{"role", "parts"}`, and a part is `text`, `tool_call` or
`tool_call_response`. Output messages also carry `finish_reason`.
"""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

Part = dict[str, Any]
Message = dict[str, Any]

# LangChain message type -> semconv role.
_ROLES = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}


def to_json(value: Any) -> str:
    # Customer text is Portuguese: keep accents readable in Langfuse.
    return json.dumps(value, ensure_ascii=False)


def _parts(message: BaseMessage) -> list[Part]:
    if isinstance(message, ToolMessage):
        return [
            {"type": "tool_call_response", "id": message.tool_call_id, "response": message.text}
        ]
    parts: list[Part] = []
    if text := message.text:
        parts.append({"type": "text", "content": text})
    if isinstance(message, AIMessage):
        parts.extend(
            {"type": "tool_call", "id": call["id"], "name": call["name"], "arguments": call["args"]}
            for call in message.tool_calls
        )
    return parts


def _message(message: BaseMessage) -> Message:
    return {"role": _ROLES.get(message.type, message.type), "parts": _parts(message)}


def input_messages(messages: Sequence[BaseMessage]) -> str:
    """`gen_ai.input.messages`: what was sent, in order. The system prompt
    goes to `system_instructions`, so leave it out of `messages`."""
    return to_json([_message(m) for m in messages])


def output_messages(answer: AIMessage) -> str:
    """`gen_ai.output.messages` of a model call: one assistant message. The
    finish reason is the provider's own value, as in
    `gen_ai.response.finish_reasons`, and is left out when missing."""
    message = _message(answer)
    metadata = answer.response_metadata
    if reason := metadata.get("stop_reason") or metadata.get("finish_reason"):
        message["finish_reason"] = reason
    return to_json([message])


def system_instructions(text: str) -> str:
    """`gen_ai.system_instructions`: the system prompt as one text part."""
    return to_json([{"type": "text", "content": text}])


def text_messages(role: str, texts: Sequence[str]) -> str:
    """Plain text messages, for the turn span: the customer message in, the
    replies out."""
    return to_json([{"role": role, "parts": [{"type": "text", "content": t}]} for t in texts])
