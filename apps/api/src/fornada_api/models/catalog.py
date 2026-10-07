from decimal import Decimal

from sqlalchemy import ForeignKey, Identity, Numeric, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fornada_api.models.base import Base
from fornada_api.models.enums import AllergenKind


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    description: Mapped[str]
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cost_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_custom: Mapped[bool] = mapped_column(server_default=false())
    active: Mapped[bool] = mapped_column(server_default=true())

    allergen_links: Mapped[list[ProductAllergen]] = relationship(
        back_populates="product", lazy="raise"
    )


class Allergen(Base):
    __tablename__ = "allergens"

    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]


class ProductAllergen(Base):
    __tablename__ = "product_allergens"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    allergen_code: Mapped[str] = mapped_column(ForeignKey("allergens.code"), primary_key=True)
    kind: Mapped[AllergenKind]

    product: Mapped[Product] = relationship(back_populates="allergen_links", lazy="raise")
    allergen: Mapped[Allergen] = relationship(lazy="raise")


class PanSize(Base):
    __tablename__ = "pan_sizes"

    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    min_kg: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    max_kg: Mapped[Decimal] = mapped_column(Numeric(4, 1))
