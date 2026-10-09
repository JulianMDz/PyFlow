import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Deterministic constraint names so Alembic autogenerate produces stable diffs
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UUID_PK_DEFAULT = text("gen_random_uuid()")


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=UUID_PK_DEFAULT
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        CheckConstraint("commission_rate >= 0 AND commission_rate <= 1", name="commission_rate_range"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=UUID_PK_DEFAULT
    )
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100))
    # Fraction of the order total, e.g. 0.0600 = 6%
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))

    orders: Mapped[list["Order"]] = relationship(back_populates="merchant")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="total_amount_positive"),
        CheckConstraint("num_installments > 0", name="num_installments_positive"),
        CheckConstraint("status IN ('active', 'completed', 'cancelled')", name="status_valid"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=UUID_PK_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.merchant_id", ondelete="RESTRICT"), index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    num_installments: Mapped[int] = mapped_column(Integer, server_default=text("4"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="orders")
    merchant: Mapped["Merchant"] = relationship(back_populates="orders")
    installments: Mapped[list["Installment"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Installment.due_date",
    )


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('pending', 'paid', 'overdue', 'cancelled')", name="status_valid"),
    )

    installment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=UUID_PK_DEFAULT
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.order_id", ondelete="CASCADE"), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped["Order"] = relationship(back_populates="installments")
    payments: Mapped[list["Payment"]] = relationship(back_populates="installment")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=UUID_PK_DEFAULT
    )
    installment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installments.installment_id", ondelete="RESTRICT"), index=True
    )
    method: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    installment: Mapped["Installment"] = relationship(back_populates="payments")
