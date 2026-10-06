import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Installment, Merchant, Order, Payment, User
from app.db.schemas import OrderCreateRequest
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

INSTALLMENT_INTERVAL = timedelta(days=14)
CENT = Decimal("0.01")


def today_utc() -> date:
    return datetime.now(UTC).date()


def split_amount(total: Decimal, num_installments: int) -> list[Decimal]:
    """Split `total` into `num_installments` equal parts that sum exactly to `total`.

    Each part is rounded down to the cent; the leftover cents go to the first
    installment, e.g. 100.00 / 3 → [33.34, 33.33, 33.33].
    """
    if num_installments < 1:
        raise BusinessRuleError("num_installments must be at least 1")
    if total < CENT * num_installments:
        raise BusinessRuleError(
            f"total_amount must be at least {CENT * num_installments} "
            f"for {num_installments} installments"
        )

    base = (total / num_installments).quantize(CENT, rounding=ROUND_DOWN)
    remainder = total - base * num_installments
    return [base + remainder] + [base] * (num_installments - 1)


def build_due_dates(start: date, num_installments: int) -> list[date]:
    """First installment is due 14 days after `start`, then every 14 days."""
    return [start + INSTALLMENT_INTERVAL * (i + 1) for i in range(num_installments)]


async def user_has_overdue_installments(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> bool:
    # Also counts pending installments already past due, so the rule holds even
    # if the overdue check has not run yet today.
    is_overdue = or_(
        Installment.status == "overdue",
        and_(Installment.status == "pending", Installment.due_date < today),
    )
    stmt = select(
        exists()
        .where(Installment.order_id == Order.order_id)
        .where(Order.user_id == user_id)
        .where(is_overdue)
    )
    return bool(await db.scalar(stmt))


async def get_order(db: AsyncSession, order_id: uuid.UUID, *, lock: bool = False) -> Order:
    """Load an order with its installments.

    `lock=True` takes a row lock on the order (SELECT ... FOR UPDATE) until the
    transaction ends. Every write to an order's state locks the order first, so
    concurrent payments/cancellations on the same order run one at a time.
    """
    stmt = (
        select(Order)
        .where(Order.order_id == order_id)
        .options(selectinload(Order.installments))
        # Overwrite objects already in the session with the stored values (e.g. 100 → 100.00)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    order = await db.scalar(stmt)
    if order is None:
        raise NotFoundError("Order not found")
    return order


async def create_order(
    db: AsyncSession, payload: OrderCreateRequest, today: date | None = None
) -> Order:
    today = today or today_utc()

    if await db.get(User, payload.user_id) is None:
        raise NotFoundError("User not found")
    if await db.get(Merchant, payload.merchant_id) is None:
        raise NotFoundError("Merchant not found")
    if await user_has_overdue_installments(db, payload.user_id, today):
        raise ConflictError("User has overdue installments")

    amounts = split_amount(payload.total_amount, payload.num_installments)
    due_dates = build_due_dates(today, payload.num_installments)

    order = Order(
        user_id=payload.user_id,
        merchant_id=payload.merchant_id,
        total_amount=payload.total_amount,
        num_installments=payload.num_installments,
        status="active",
        installments=[
            Installment(due_date=due_date, amount=amount, status="pending")
            for due_date, amount in zip(due_dates, amounts, strict=True)
        ],
    )
    db.add(order)
    await db.commit()
    return await get_order(db, order.order_id)


async def cancel_order(db: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await get_order(db, order_id, lock=True)

    if order.status != "active":
        raise ConflictError(f"Only active orders can be cancelled (status: {order.status})")

    has_payments = await db.scalar(
        select(
            exists()
            .where(Payment.installment_id == Installment.installment_id)
            .where(Installment.order_id == order_id)
        )
    )
    if has_payments:
        raise ConflictError("Order has payments and cannot be cancelled")

    order.status = "cancelled"
    for installment in order.installments:
        installment.status = "cancelled"
    await db.commit()
    return order
