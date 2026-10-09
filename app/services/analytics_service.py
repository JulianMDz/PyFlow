from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import ColumnElement, Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.models import Installment, Merchant, Order, Payment
from app.db.schemas import (
    DashboardSummaryResponse,
    RevenueMonth,
    RevenueReportResponse,
    RevenueTotals,
)
from app.services.exceptions import BusinessRuleError
from app.services.installment_rules import is_overdue, is_paid_late, is_paid_on_time
from app.services.order_service import CENT, today_utc

DEFAULT_REPORT_MONTHS = 12


def money(value: Decimal | int | None) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def utc_day(column: InstrumentedAttribute[datetime]) -> ColumnElement[date]:
    return cast(func.timezone("UTC", column), Date)


def utc_month(column: InstrumentedAttribute[datetime]) -> ColumnElement[str]:
    return func.to_char(func.timezone("UTC", column), "YYYY-MM")


def commission_per_order() -> ColumnElement[Decimal]:
    """Each order's fee, rounded to the cent like a real charge, so every total adds up."""
    return func.round(Order.total_amount * Merchant.commission_rate, 2)


def default_start(end: date) -> date:
    """First day of the month that makes [start, end] span DEFAULT_REPORT_MONTHS months."""
    index = end.year * 12 + end.month - 1 - (DEFAULT_REPORT_MONTHS - 1)
    return date(index // 12, index % 12 + 1, 1)


def month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


async def revenue_report(
    db: AsyncSession, start: date | None = None, end: date | None = None
) -> RevenueReportResponse:
    """Per-month GMV, commission revenue and collected payments, with empty months as zeros.

    Orders count in the month they were created; payments in the month they were processed.
    """
    end = end or today_utc()
    start = start or default_start(end)
    if start > end:
        raise BusinessRuleError("start must be on or before end")

    order_month = utc_month(Order.created_at).label("month")
    order_rows = await db.execute(
        select(
            order_month,
            func.count(),
            func.sum(Order.total_amount),
            func.sum(commission_per_order()),
        )
        .join(Merchant, Order.merchant_id == Merchant.merchant_id)
        .where(Order.status != "cancelled", utc_day(Order.created_at).between(start, end))
        .group_by(order_month)
    )
    orders_by_month = {month: (count, gmv, revenue) for month, count, gmv, revenue in order_rows}

    payment_month = utc_month(Payment.processed_at).label("month")
    payment_rows = await db.execute(
        select(payment_month, func.sum(Payment.amount))
        .where(utc_day(Payment.processed_at).between(start, end))
        .group_by(payment_month)
    )
    collected_by_month = {month: collected for month, collected in payment_rows}

    by_month: list[RevenueMonth] = []
    for month in month_range(start, end):
        count, gmv, revenue = orders_by_month.get(month, (0, 0, 0))
        by_month.append(
            RevenueMonth(
                month=month,
                orders=count,
                gmv=money(gmv),
                revenue=money(revenue),
                collected=money(collected_by_month.get(month)),
            )
        )

    # Totals are sums of the rounded months, so the chart always adds up to the total
    totals = RevenueTotals(
        orders=sum(m.orders for m in by_month),
        gmv=sum((m.gmv for m in by_month), Decimal("0.00")),
        revenue=sum((m.revenue for m in by_month), Decimal("0.00")),
        collected=sum((m.collected for m in by_month), Decimal("0.00")),
    )
    return RevenueReportResponse(start=start, end=end, totals=totals, by_month=by_month)


async def dashboard_summary(db: AsyncSession, today: date | None = None) -> DashboardSummaryResponse:
    today = today or today_utc()

    active_orders, total_revenue = (
        await db.execute(
            select(
                func.count().filter(Order.status == "active"),
                func.sum(commission_per_order()).filter(Order.status != "cancelled"),
            ).join(Merchant, Order.merchant_id == Merchant.merchant_id)
        )
    ).one()

    overdue, on_time, late = (
        await db.execute(
            select(
                func.count().filter(is_overdue(today)),
                func.count().filter(is_paid_on_time()),
                func.count().filter(or_(is_paid_late(), is_overdue(today))),
            ).select_from(Installment)
        )
    ).one()

    already_due = on_time + late
    return DashboardSummaryResponse(
        as_of=today,
        active_orders=active_orders,
        total_revenue=money(total_revenue),
        overdue_installments=overdue,
        on_time_payment_rate=round(on_time / already_due, 4) if already_due else None,
    )
