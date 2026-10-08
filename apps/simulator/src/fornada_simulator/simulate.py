"""Run simulated conversations: a persona plays the customer against the API.

The persona's model sees the chat from the customer's side: its own messages are
`AIMessage`, the attendant's replies arrive as `HumanMessage` (the usual role
inversion for simulated users). Message text is never logged.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from fornada_simulator.client import ApiError, send_message
from fornada_simulator.personas import PERSONAS, Persona
from fornada_simulator.settings import SimulatorSettings
from fornada_simulator.transcript import Message, Outcome, Transcript, append_jsonl

logger = logging.getLogger(__name__)

END_MARKER = "[FIM]"
START_PROMPT = "A conversa com a confeitaria começa agora. Escreva a primeira mensagem do cliente."


class ChatModel(Protocol):
    """What the simulator needs from a chat model; `BaseChatModel` satisfies it."""

    async def ainvoke(self, input: list[BaseMessage], /) -> BaseMessage: ...


def build_system_prompt(persona: Persona, goal: str) -> str:
    return (
        f"{persona.description}\n\n"
        f"O que você quer agora: {goal}\n\n"
        "Você está conversando por mensagem com a atendente de uma confeitaria que "
        "vende bolos por encomenda. Regras:\n"
        "- Escreva só a próxima mensagem do cliente, em português do Brasil, curta, "
        "como num chat. Sem aspas, sem explicações, sem descrever ações.\n"
        "- Aja como uma pessoa real. Nunca diga que é uma IA ou um personagem.\n"
        "- Só fale o que o cliente sabe; não invente informações da loja.\n"
        f"- Quando a conversa terminar (você fechou, desistiu ou se despediu), "
        f"termine a sua mensagem com {END_MARKER}."
    )


def _text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else str(block.get("text", "")) for block in content
    )


async def run_conversation(
    persona: Persona,
    goal: str,
    http: httpx.AsyncClient,
    model: ChatModel,
    *,
    max_turns: int,
    run_id: str,
) -> Transcript:
    """Play one conversation; always returns a transcript with its outcome."""
    conversation_id = uuid.uuid4()
    started = time.monotonic()
    history: list[BaseMessage] = [
        SystemMessage(build_system_prompt(persona, goal)),
        HumanMessage(START_PROMPT),
    ]
    messages: list[Message] = []
    turns = 0
    outcome: Outcome = "max_turns"

    for _ in range(max_turns):
        try:
            raw = _text_of(await model.ainvoke(history)).strip()
        except Exception as exc:
            # The error text can carry request details: log only its type.
            logger.warning(
                "simulator call failed",
                extra={"conversation_id": str(conversation_id), "error": type(exc).__name__},
            )
            outcome = "simulator_error"
            break

        ended = END_MARKER in raw
        text = raw.replace(END_MARKER, "").strip()
        if not text and not ended:
            outcome = "simulator_error"
            break
        if text:
            history.append(AIMessage(text))
            messages.append(Message(role="customer", text=text))
            turns += 1
            try:
                replies = await send_message(http, conversation_id, text)
            except ApiError:
                outcome = "api_error"
                break
            messages.extend(
                Message(role="attendant", text=reply, reply_index=index)
                for index, reply in enumerate(replies)
            )
            history.append(HumanMessage("\n\n".join(replies)))
        if ended:
            outcome = "completed"
            break

    transcript = Transcript(
        run_id=run_id,
        persona_id=persona.id,
        goal=goal,
        conversation_id=conversation_id,
        outcome=outcome,
        messages=messages,
        turns=turns,
        elapsed_seconds=round(time.monotonic() - started, 2),
    )
    logger.info(
        "conversation finished",
        extra={
            "run_id": run_id,
            "persona_id": persona.id,
            "conversation_id": str(conversation_id),
            "outcome": outcome,
            "turns": turns,
        },
    )
    return transcript


def plan_jobs(runs_per_persona: int) -> list[tuple[Persona, str]]:
    """Same number of runs for every persona; each persona's goals in order.

    Rounds are interleaved (every persona once, then again) so a batch cut short
    is still balanced.
    """
    return [
        (persona, persona.goals[run % len(persona.goals)])
        for run in range(runs_per_persona)
        for persona in PERSONAS
    ]


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:4]}"


async def run_batch(
    settings: SimulatorSettings,
    model: ChatModel,
    *,
    runs_dir: Path,
    run_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[Transcript]:
    """Run the planned conversations; each transcript is appended as it finishes."""
    run_id = run_id or new_run_id()
    path = runs_dir / f"{run_id}.jsonl"
    semaphore = asyncio.Semaphore(settings.concurrency)

    async with httpx.AsyncClient(
        base_url=settings.api_url, timeout=120, transport=transport
    ) as http:

        async def one(persona: Persona, goal: str) -> Transcript:
            async with semaphore:
                transcript = await run_conversation(
                    persona, goal, http, model, max_turns=settings.max_turns, run_id=run_id
                )
            append_jsonl(path, transcript)
            return transcript

        jobs = plan_jobs(settings.runs_per_persona)
        return list(await asyncio.gather(*(one(persona, goal) for persona, goal in jobs)))
