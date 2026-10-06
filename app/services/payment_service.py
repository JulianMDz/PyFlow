from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Installment, Payment
from app.db.schemas import PaymentCreateRequest
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.order_service import get_order, today_utc

PAYABLE_STATUSES = frozenset({"pending", "overdue"})


async def process_payment(
    db: AsyncSession, payload: PaymentCreateRequest, now: datetime | None = None
) -> Payment:
    now = now or datetime.now(UTC)

    order_id = await db.scalar(
        select(Installment.order_id).where(Installment.installment_id == payload.installment_id)
    )
    if order_id is None:
        raise NotFoundError("Installment not found")

    # Lock the order before reading installment state: a concurrent request paying
    # the same installment waits here and then sees it as already paid (no double
    # charge), and payments of the last two installments can't both miss completion.
    order = await get_order(db, order_id, lock=True)
    installment = next(i for i in order.installments if i.installment_id == payload.installment_id)

    if installment.status not in PAYABLE_STATUSES:
        raise ConflictError(f"Installment is not payable (status: {installment.status})")
    if payload.amount != installment.amount:
        raise BusinessRuleError(
            f"Payment amount must equal the installment amount ({installment.amount})"
        )

    payment = Payment(
        installment_id=installment.installment_id,
        method=payload.method,
        amount=installment.amount,
        processed_at=now,
    )
    db.add(payment)
    installment.status = "paid"
    installment.paid_at = now
    if all(i.status == "paid" for i in order.installments):
        order.status = "completed"

    await db.commit()
    return payment


async def mark_overdue_installments(db: AsyncSession, today: date | None = None) -> int:
    """Move pending installments whose due date has passed to 'overdue'.

    Idempotent: running it twice on the same day updates nothing the second time.
    """
    today = today or today_utc()
    result = await db.execute(
        update(Installment)
        .where(Installment.status == "pending", Installment.due_date < today)
        .values(status="overdue")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return result.rowcount
