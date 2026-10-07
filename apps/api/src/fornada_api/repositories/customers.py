from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fornada_api.models import Customer


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_phone(self, phone: str) -> Customer | None:
        return await self.session.scalar(select(Customer).where(Customer.phone == phone))

    async def add(self, customer: Customer) -> Customer:
        self.session.add(customer)
        await self.session.flush()
        return customer
