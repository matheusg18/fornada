"""Side effects that leave the conversation: messages and hand-offs to a human.

Nothing is actually sent; each call is recorded as a row. In v0 a message can
go to any number (the exfiltration channel phase 6 closes).
"""

from dataclasses import dataclass

from fornada_api.models import Escalation, SentMessage
from fornada_api.services.errors import OrderNotFound
from fornada_api.services.phones import normalize_phone
from fornada_api.services.ports import OrderRepository, SideEffectRepository


@dataclass(frozen=True)
class MessageSent:
    message_id: int
    to_phone: str
    order_id: int | None


@dataclass(frozen=True)
class EscalationCreated:
    escalation_id: int
    thread_id: str


class MessagingService:
    def __init__(self, side_effects: SideEffectRepository, orders: OrderRepository) -> None:
        self.side_effects = side_effects
        self.orders = orders

    async def send_message(self, phone: str, text: str, order_id: int | None = None) -> MessageSent:
        to_phone = normalize_phone(phone)
        if order_id is not None and await self.orders.get(order_id) is None:
            raise OrderNotFound(f"order {order_id} not found")
        message = await self.side_effects.add_message(
            SentMessage(to_phone=to_phone, body=text, order_id=order_id)
        )
        return MessageSent(message_id=message.id, to_phone=to_phone, order_id=order_id)

    async def escalate(
        self, thread_id: str, reason: str, phone: str | None = None
    ) -> EscalationCreated:
        escalation = await self.side_effects.add_escalation(
            Escalation(
                thread_id=thread_id,
                phone=normalize_phone(phone) if phone else None,
                reason=reason,
            )
        )
        return EscalationCreated(escalation_id=escalation.id, thread_id=thread_id)
