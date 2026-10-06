"""SQL conditions that define installment health.

Shared by orders, risk scoring and analytics so "overdue" and "on time" mean
exactly the same thing everywhere.
"""

from datetime import date

from sqlalchemy import ColumnElement, Date, and_, cast, func, or_

from app.db.models import Installment


def paid_on_date() -> ColumnElement[date]:
    return cast(func.timezone("UTC", Installment.paid_at), Date)


def is_overdue(today: date) -> ColumnElement[bool]:
    """Unpaid and past due. Pending installments count too, so the rule holds
    even if the overdue check has not run yet today."""
    return or_(
        Installment.status == "overdue",
        and_(Installment.status == "pending", Installment.due_date < today),
    )


def is_paid_on_time() -> ColumnElement[bool]:
    return and_(Installment.status == "paid", paid_on_date() <= Installment.due_date)


def is_paid_late() -> ColumnElement[bool]:
    return and_(Installment.status == "paid", paid_on_date() > Installment.due_date)
