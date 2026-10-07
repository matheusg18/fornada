"""The attendant's entry point: one customer message in, the bot's replies out.

The HTTP layer depends only on `Attendant`. Until the LangGraph graph is wired,
`FixedAttendant` answers every message with the same text.
"""

from typing import Protocol
from uuid import UUID

FIXED_REPLY = (
    "Olá! Aqui é a Fornada. Ainda estou aprendendo a anotar pedidos, "
    "mas logo vou poder te ajudar com o seu bolo."
)


class Attendant(Protocol):
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        """Answer one customer message with one or more bot messages."""
        ...


class FixedAttendant:
    """Same reply for every message. Calls no LLM and stores nothing."""

    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        return [FIXED_REPLY]
