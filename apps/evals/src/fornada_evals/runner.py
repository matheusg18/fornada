"""Plays one golden case against the real graph and records it as a DeepEval test case.

The graph runs in-process with LangGraph's in-memory saver, the real tools on the case's
isolated schema and a clock fixed at the seed day. Tool calls come from the graph's own
messages, never from DeepEval tracing. See the `add-eval-harness` design, decisions 4-5.
"""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from deepeval.test_case import ConversationalTestCase, ToolCall, Turn
from fornada_api.agents.attendant.attendant import RECURSION_LIMIT, turn_replies
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.metrics import TokenPrices
from fornada_api.agents.attendant.model import build_chat_model
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.agents.attendant.tools import build_tools
from fornada_api.core.config import ChaosSettings, get_settings
from fornada_api.infrastructure.chaos import Chaos
from fornada_api.services.clock import FixedClock
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from fornada_evals.dataset import GoldenCase, render
from fornada_evals.isolation import isolated_database

# Every `check_capacity` fails with the tool's generic error, and nothing waits.
OUTAGE = ChaosSettings(
    enabled=True, latency_min_ms=0, latency_max_ms=0, capacity_failure_rate=1, seed=0
)
# How the simulator joins a turn's replies into one message.
REPLY_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class Agent:
    """What the runner takes from the API's settings; tests pass their own."""

    model: BaseChatModel
    model_name: str
    prices: TokenPrices
    daily_capacity_kg: Decimal


def agent_from_settings() -> Agent:
    settings = get_settings()
    llm = settings.llm.active
    return Agent(
        model=build_chat_model(settings.llm),
        model_name=llm.model,
        prices=TokenPrices(llm.input_usd_per_mtok, llm.output_usd_per_mtok),
        daily_capacity_kg=settings.app.daily_capacity_kg,
    )


async def run_case(
    case: GoldenCase, run_index: int, *, database_url: str, agent: Agent | None = None
) -> ConversationalTestCase:
    """Send the case's customer turns in order. A turn that raises ends the run, which
    is then marked failed with the error; the turns before it stay recorded."""
    agent = agent or agent_from_settings()
    prompt = load_system_prompt()
    turns: list[Turn] = []
    latencies_ms: list[float] = []
    input_tokens = output_tokens = 0
    error: str | None = None

    async with isolated_database(database_url) as db:
        tools = build_tools(
            db.sessionmaker,
            clock=FixedClock(db.run_day),
            daily_capacity_kg=agent.daily_capacity_kg,
            chaos=Chaos(OUTAGE) if case.metadata.outage else None,
        )
        graph = build_graph(agent.model, tools, prompt).compile(checkpointer=InMemorySaver())
        config: Any = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "recursion_limit": RECURSION_LIMIT,
        }
        for text in case.turns:
            content = render(text, db.run_day)
            turns.append(Turn(role="user", content=content))
            start = time.perf_counter()
            try:
                output = await graph.ainvoke({"messages": [HumanMessage(content)]}, config)
            except Exception as raised:
                error = f"{type(raised).__name__}: {raised}"
                break
            latency_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(latency_ms)
            new = _after_last_customer(output["messages"])
            for message in new:
                if isinstance(message, AIMessage) and message.usage_metadata:
                    input_tokens += message.usage_metadata["input_tokens"]
                    output_tokens += message.usage_metadata["output_tokens"]
            calls, statuses = _tool_calls(new)
            turns.append(
                Turn(
                    role="assistant",
                    content=REPLY_SEPARATOR.join(turn_replies(output["messages"])),
                    tools_called=calls,
                    latency_ms=latency_ms,
                    metadata={"tool_status": statuses},
                )
            )

    return ConversationalTestCase(
        name=case.name,
        scenario=case.scenario,
        expected_outcome=case.expected_outcome,
        turns=turns,
        metadata={
            "run_index": run_index,
            "run_day": db.run_day.isoformat(),
            "prompt_version": prompt.version,
            "model": agent.model_name,
            "case": case.metadata.model_dump(mode="json"),
            "failed": error is not None,
            "error": error,
            "latencies_ms": latencies_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": agent.prices.cost(input_tokens, output_tokens),
        },
    )


def _after_last_customer(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    start = 0
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            start = index + 1
    return list(messages[start:])


def _tool_calls(messages: Sequence[AnyMessage]) -> tuple[list[ToolCall], list[str]]:
    """Each requested call, in order, paired with its result by `tool_call_id`, and
    each result's status (`success` or `error`)."""
    results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    calls: list[ToolCall] = []
    statuses: list[str] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            result = results.get(call["id"] or "")
            calls.append(
                ToolCall(
                    name=call["name"],
                    input_parameters=call["args"],
                    output=result.content if result else None,
                )
            )
            # No result: the turn ended before the tool ran.
            statuses.append(result.status if result else "missing")
    return calls, statuses
