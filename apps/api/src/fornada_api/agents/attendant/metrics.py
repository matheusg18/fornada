"""The attendant's metrics. See the `app-metrics` spec.

Instruments are created once, at import, from the global meter: a proxy until
`setup_metrics` registers the SDK provider, and a no-op when telemetry is off.
Names follow the GenAI semantic conventions in
`open-telemetry/semantic-conventions-genai`, read at commit 547934a
(2026-10-18); like `tracing.py`, they live here as plain strings, so a
convention bump is one diff in this module. Where semconv has nothing (tool
outcome counts, spend, conversations), names are under `fornada.`.

Measurements carry only low-cardinality attributes: the semconv ones the spans
already have, minus ids and content, plus the persona. Never a conversation id,
a phone or a message.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal

from opentelemetry import baggage, metrics

meter = metrics.get_meter(__name__)

# Persona of the simulated customer, from the request's W3C Baggage (the
# `client-tracing` spec). Only ever a metric dimension, never on a span.
FORNADA_SIMULATOR_PERSONA_ID = "fornada.simulator.persona.id"

# The simulator's persona ids (`apps/simulator/.../personas.py`). Any other value
# would let a client create one series per request, so it is recorded as `other`.
PERSONAS = frozenset({"apressada", "indecisa", "pechincheira", "mae_alergica", "malandro"})
PERSONA_OTHER = "other"
# No baggage entry: the chat, or any client that is not the simulator.
PERSONA_NONE = "none"

# The turn's persona, set by `GraphAttendant.reply` before the graph runs.
# Asyncio tasks copy it, so the nodes LangGraph runs see the same value.
current_persona: ContextVar[str] = ContextVar("current_persona", default=PERSONA_NONE)


def persona_from_baggage() -> str:
    """The persona in the current context's baggage, mapped through `PERSONAS`."""
    value = baggage.get_baggage(FORNADA_SIMULATOR_PERSONA_ID)
    if value is None:
        return PERSONA_NONE
    # Baggage values are typed `object`; the propagator only ever puts strings.
    return value if isinstance(value, str) and value in PERSONAS else PERSONA_OTHER


@dataclass(frozen=True)
class TokenPrices:
    """The active provider's prices, in US dollars per million tokens."""

    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        usd = (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1_000_000
        # Exact in Decimal; float only at the instrument, which takes floats.
        return float(usd)


# Semconv bucket boundaries. Durations double from 10 ms to 82 s; tokens grow
# by powers of 4 from 1 to 67M. The SDK default ([0, 5, 10, 25, ..., 10000]) is
# made for milliseconds: every turn would land in the first bucket or two.
DURATION_BUCKETS = [
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
]  # fmt: skip
TOKEN_BUCKETS = [
    1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864,
]  # fmt: skip

# Model calls: one measurement each per `chat` span.
inference_duration = meter.create_histogram(
    "gen_ai.client.inference.duration",
    unit="s",
    description="GenAI client inference operation duration.",
    explicit_bucket_boundaries_advisory=DURATION_BUCKETS,
)
inference_input_tokens = meter.create_histogram(
    "gen_ai.client.inference.operation.input_tokens",
    unit="{token}",
    description="Input tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)
inference_output_tokens = meter.create_histogram(
    "gen_ai.client.inference.operation.output_tokens",
    unit="{token}",
    description="Output tokens used per inference operation.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)

# Turns and tools: one measurement per `invoke_agent` and `execute_tool` span.
invoke_agent_duration = meter.create_histogram(
    "gen_ai.invoke_agent.duration",
    unit="s",
    description="End-to-end duration of one attendant turn.",
    explicit_bucket_boundaries_advisory=DURATION_BUCKETS,
)
execute_tool_duration = meter.create_histogram(
    "gen_ai.execute_tool.duration",
    unit="s",
    description="Duration of one tool execution.",
    explicit_bucket_boundaries_advisory=DURATION_BUCKETS,
)

# Fornada's own. Counters, because Kibana sums them over a time range: calls
# with and without `error.type` give the error rate; spend over conversations
# gives the mean cost per conversation. Semconv says the token histograms are
# not for totals or cost.
tool_calls = meter.create_counter(
    "fornada.tool.calls",
    unit="{call}",
    description="Tool calls; failed ones carry error.type.",
)
cost = meter.create_counter(
    "fornada.gen_ai.cost",
    unit="USD",
    description="Model spend, priced from the provider's token prices.",
)
conversations = meter.create_counter(
    "fornada.conversations",
    unit="{conversation}",
    description="Conversations whose first turn completed.",
)
