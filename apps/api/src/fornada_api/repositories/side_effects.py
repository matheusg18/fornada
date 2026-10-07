from sqlalchemy.ext.asyncio import AsyncSession

from fornada_api.models import Escalation, SentMessage


class SideEffectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_message(self, message: SentMessage) -> SentMessage:
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_escalation(self, escalation: Escalation) -> Escalation:
        self.session.add(escalation)
        await self.session.flush()
        return escalation
