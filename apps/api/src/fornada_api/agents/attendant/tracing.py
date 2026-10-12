"""Span and attribute names for the attendant's spans. See the `agent-tracing` spec.

Spans are made by hand with the OpenTelemetry API: one `invoke_agent` per turn,
one `chat` per model call and one `execute_tool` per tool call. Names follow the
GenAI semantic conventions in `open-telemetry/semantic-conventions-genai`, read
at commit 6fd0d76 (2026-10-09). They are still in development status, so they
live here as plain strings; a convention bump is one diff in this module.

The tracer comes from the global provider: a proxy until `setup_tracing`
registers the SDK provider, and a no-op when tracing is disabled.
"""

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

AGENT_NAME = "fornada-attendant"

# gen_ai.operation.name values.
OP_INVOKE_AGENT = "invoke_agent"
OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"

# GenAI semconv attributes.
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
TOOL_TYPE_FUNCTION = "function"

# General semconv. Langfuse maps `session.id` to the trace's session;
# it does not read `gen_ai.conversation.id`.
SESSION_ID = "session.id"
ERROR_TYPE = "error.type"

# Fornada's own attributes.
FORNADA_PROMPT_VERSION = "fornada.prompt.version"
FORNADA_CAPACITY_FREE_KG = "fornada.capacity.free_kg"
