"""The attendant's nine tools, as LangChain tools for a LangGraph `ToolNode`.

Tools are thin: each call opens one session and one transaction, builds the
services, calls one of them and returns its result as JSON-ready data. A
`DomainError` becomes an error `ToolMessage` the LLM can read; anything else
is logged and reaches the LLM only as a generic message.

v0 has no defenses on purpose: arguments come straight from the LLM (phones,
order ids, message targets). See the `agent-tools` spec.
"""

import dataclasses
import datetime as dt
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import ToolRuntime
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fornada_api import repositories
from fornada_api.core.config import get_settings
from fornada_api.infrastructure.engine import get_sessionmaker
from fornada_api.models import Fulfillment
from fornada_api.services.capacity import CapacityService
from fornada_api.services.catalog import CatalogService
from fornada_api.services.clock import Clock, SystemClock
from fornada_api.services.coupons import CouponService
from fornada_api.services.errors import DomainError
from fornada_api.services.messaging import MessagingService
from fornada_api.services.orders import OrderService
from fornada_api.services.quotes import QuoteService

logger = logging.getLogger(__name__)

FulfillmentArg = Annotated[
    Literal["pickup", "delivery"],
    Field(description="'pickup' at the shop or 'delivery' to a neighborhood"),
]
WeightArg = Annotated[Decimal, Field(description="Cake weight in kg, in steps of 0.5")]
SlugArg = Annotated[str, Field(description="Product slug from search_catalog")]
PhoneArg = Annotated[str, Field(description="Customer phone with area code")]
OrderIdArg = Annotated[int, Field(description="Order number")]
NeighborhoodArg = Annotated[
    str | None, Field(description="Delivery neighborhood; required for delivery")
]


@dataclass(frozen=True)
class Services:
    catalog: CatalogService
    capacity: CapacityService
    quotes: QuoteService
    orders: OrderService
    messaging: MessagingService


def jsonable(value: Any) -> Any:
    """Service results -> JSON-ready data: decimals as fixed-place strings, dates in ISO."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    return value


def build_tools(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    clock: Clock,
    daily_capacity_kg: Decimal,
) -> list[BaseTool]:
    """The nine tools, bound to a session factory. Tests pass their own."""

    def services(session: AsyncSession) -> Services:
        catalog_repo = repositories.CatalogRepository(session)
        orders_repo = repositories.OrderRepository(session)
        quotes = QuoteService(catalog_repo)
        return Services(
            catalog=CatalogService(catalog_repo),
            capacity=CapacityService(
                repositories.CapacityRepository(session), clock, daily_capacity_kg
            ),
            quotes=quotes,
            orders=OrderService(
                repositories.CustomerRepository(session),
                orders_repo,
                quotes,
                CouponService(repositories.CouponRepository(session), clock),
                clock,
            ),
            messaging=MessagingService(repositories.SideEffectRepository(session), orders_repo),
        )

    async def run(name: str, call: Callable[[Services], Awaitable[object]]) -> Any:
        try:
            # One transaction per call: commit on success, roll back on any error.
            async with sessionmaker() as session, session.begin():
                result = await call(services(session))
        except DomainError as error:
            raise ToolException(str(error)) from error
        except Exception:
            # Driver errors can carry hosts and credentials: log them, never return them.
            logger.exception("tool failed", extra={"tool": name})
            raise ToolException(
                f"internal error in {name}; try again later or escalate to a human"
            ) from None
        return jsonable(result)

    @tool
    async def search_catalog(
        query: Annotated[
            str | None, Field(description="Words to match in product names or descriptions")
        ] = None,
    ) -> dict[str, Any]:
        """List the bakery's cakes with price per kg and allergens, plus pan sizes and
        delivery neighborhoods with fees. Without a query, lists every product."""
        return await run("search_catalog", lambda s: s.catalog.search(query))

    @tool
    async def check_capacity(
        date: Annotated[dt.date, Field(description="Delivery date, YYYY-MM-DD")],
    ) -> dict[str, Any]:
        """Free oven capacity in kg on a date, and whether the date meets the minimum
        lead time for regular and custom cakes."""
        return await run("check_capacity", lambda s: s.capacity.check(date))

    @tool
    async def calculate_quote(
        product_slug: SlugArg,
        weight_kg: WeightArg,
        fulfillment: FulfillmentArg,
        neighborhood: NeighborhoodArg = None,
    ) -> dict[str, Any]:
        """Price one cake: pan size, subtotal, delivery fee, total and the 50% deposit."""
        return await run(
            "calculate_quote",
            lambda s: s.quotes.quote(
                product_slug, weight_kg, Fulfillment(fulfillment), neighborhood
            ),
        )

    @tool
    async def create_order(
        customer_name: Annotated[str, Field(description="Customer's name")],
        phone: PhoneArg,
        product_slug: SlugArg,
        weight_kg: WeightArg,
        delivery_date: Annotated[dt.date, Field(description="Delivery date, YYYY-MM-DD")],
        fulfillment: FulfillmentArg,
        neighborhood: NeighborhoodArg = None,
        address: Annotated[
            str | None, Field(description="Street address; required for delivery")
        ] = None,
        reference_photo_description: Annotated[
            str | None, Field(description="Customer's description of a reference photo")
        ] = None,
        notes: Annotated[str | None, Field(description="Other notes for the bakery")] = None,
    ) -> dict[str, Any]:
        """Save the order with status pending_payment and return its number, amounts
        and a payment link for the deposit."""
        return await run(
            "create_order",
            lambda s: s.orders.create_order(
                customer_name=customer_name,
                phone=phone,
                product_slug=product_slug,
                weight_kg=weight_kg,
                delivery_date=delivery_date,
                fulfillment=Fulfillment(fulfillment),
                neighborhood=neighborhood,
                address=address,
                reference_photo_description=reference_photo_description,
                notes=notes,
            ),
        )

    @tool
    async def get_order(order_id: OrderIdArg, phone: PhoneArg) -> dict[str, Any]:
        """Status and details of an order, for the phone number it was placed with."""
        return await run("get_order", lambda s: s.orders.get_order(order_id, phone))

    @tool
    async def cancel_order(
        order_id: OrderIdArg,
        phone: PhoneArg,
        reason: Annotated[str, Field(description="Why the customer is cancelling")],
    ) -> dict[str, Any]:
        """Cancel an order under the refund policy and return the refund amount."""
        return await run("cancel_order", lambda s: s.orders.cancel_order(order_id, phone, reason))

    @tool
    async def apply_coupon(
        order_id: OrderIdArg,
        coupon_code: Annotated[str, Field(description="Coupon code the customer gave")],
    ) -> dict[str, Any]:
        """Apply a discount coupon to an order awaiting payment and return the new
        total and deposit."""
        return await run("apply_coupon", lambda s: s.orders.apply_coupon(order_id, coupon_code))

    @tool
    async def send_message(
        phone: Annotated[str, Field(description="Destination phone with area code")],
        text: Annotated[str, Field(description="Message text")],
        order_id: Annotated[
            int | None, Field(description="Order the message is about, if any")
        ] = None,
    ) -> dict[str, Any]:
        """Send a text message (for example, an order confirmation) to a phone number."""
        return await run("send_message", lambda s: s.messaging.send_message(phone, text, order_id))

    @tool
    async def escalate_to_human(
        reason: Annotated[str, Field(description="Why a human is needed")],
        runtime: ToolRuntime,
        phone: Annotated[str | None, Field(description="Customer phone, if known")] = None,
    ) -> dict[str, Any]:
        """Hand the conversation off to the shop owner."""
        # The thread id comes from the run configuration, never from the LLM.
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        if not thread_id:
            raise ToolException("escalate_to_human needs a conversation thread id")
        return await run(
            "escalate_to_human",
            lambda s: s.messaging.escalate(str(thread_id), reason, phone),
        )

    tools: list[BaseTool] = [
        search_catalog,
        check_capacity,
        calculate_quote,
        create_order,
        get_order,
        cancel_order,
        apply_coupon,
        send_message,
        escalate_to_human,
    ]
    for each in tools:
        # Turns ToolException into a ToolMessage with status="error".
        each.handle_tool_error = True
    return tools


def default_tools() -> list[BaseTool]:
    """The tools wired to the app's database and settings."""
    settings = get_settings()
    return build_tools(
        get_sessionmaker(),
        clock=SystemClock(settings.app.timezone),
        daily_capacity_kg=settings.app.daily_capacity_kg,
    )
