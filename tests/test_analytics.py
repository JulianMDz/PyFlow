from datetime import date

import pytest

from app.services.order_service import today_utc
from tests.conftest import run_sql

THIS_MONTH = today_utc().strftime("%Y-%m")


async def test_revenue_counts_commissions_gmv_and_collected(
    client, make_order, make_user, make_merchant, pay
):
    user, merchant = await make_user(), await make_merchant(commission_rate="0.10")
    order = await make_order(total="100.00", user=user, merchant=merchant)
    cancelled = await make_order(total="50.00", user=user, merchant=merchant)
    await client.patch(f"/orders/{cancelled['order_id']}/cancel")
    await pay(order["installments"][0])

    report = (await client.get("/analytics/revenue")).json()

    month = report["by_month"][-1]
    assert month["month"] == THIS_MONTH
    # the cancelled order counts for nothing; the paid installment counts as collected
    assert (month["orders"], month["gmv"], month["revenue"], month["collected"]) == (
        1,
        "100.00",
        "10.00",
        "25.00",
    )
    assert report["totals"] == {"orders": 1, "gmv": "100.00", "revenue": "10.00", "collected": "25.00"}


async def test_revenue_default_range_is_twelve_months_with_zeros(client):
    report = (await client.get("/analytics/revenue")).json()

    months = [m["month"] for m in report["by_month"]]
    assert len(months) == 12 and months[-1] == THIS_MONTH
    assert report["end"] == today_utc().isoformat()
    assert all(m["orders"] == 0 and m["revenue"] == "0.00" for m in report["by_month"])


async def test_revenue_custom_range_crosses_the_year(client):
    report = (
        await client.get("/analytics/revenue", params={"start": "2025-11-15", "end": "2026-02-03"})
    ).json()
    assert [m["month"] for m in report["by_month"]] == ["2025-11", "2025-12", "2026-01", "2026-02"]


async def test_revenue_rounds_half_up_per_month(client, make_order, make_merchant):
    merchant = await make_merchant(commission_rate="0.0125")  # 10.00 * 1.25% = 0.125
    await make_order(total="10.00", installments=1, merchant=merchant)
    month = (await client.get("/analytics/revenue")).json()["by_month"][-1]
    assert month["revenue"] == "0.13"


@pytest.mark.parametrize(
    ("params", "status"), [({"start": "2026-03-01", "end": "2026-02-01"}, 422), ({"start": "ayer"}, 422)]
)
async def test_revenue_rejects_invalid_ranges(client, params, status):
    assert (await client.get("/analytics/revenue", params=params)).status_code == status


async def test_summary_metrics(client, make_order, make_user, make_merchant, make_past_due, pay):
    merchant = await make_merchant(commission_rate="0.10")
    on_time = await make_order(total="20.00", installments=2, merchant=merchant)
    for installment in on_time["installments"]:
        await pay(installment)  # 2 paid on time, order completed
    late = await make_order(total="40.00", installments=4, merchant=merchant, user=await make_user())
    await make_past_due(late["installments"][0])  # 1 unpaid and past due

    summary = (await client.get("/analytics/summary")).json()

    assert summary["as_of"] == today_utc().isoformat()
    assert summary["active_orders"] == 1
    assert summary["total_revenue"] == "6.00"  # 10% of 20 + 10% of 40
    assert summary["overdue_installments"] == 1
    assert summary["on_time_payment_rate"] == pytest.approx(2 / 3, abs=1e-4)


async def test_summary_rate_is_null_when_nothing_is_due(client, make_order):
    await make_order()
    assert (await client.get("/analytics/summary")).json()["on_time_payment_rate"] is None


async def test_orders_count_in_the_month_they_were_created(client, make_order):
    order = await make_order()
    await run_sql(
        "UPDATE orders SET created_at = :ts WHERE order_id = :id", ts=date(2026, 1, 15), id=order["order_id"]
    )
    report = (
        await client.get("/analytics/revenue", params={"start": "2026-01-01", "end": today_utc().isoformat()})
    ).json()
    january = next(m for m in report["by_month"] if m["month"] == "2026-01")
    assert january["orders"] == 1


async def test_overview_and_report_agree_to_the_cent(client, make_order, make_merchant):
    merchant = await make_merchant(commission_rate="0.0125")
    for total in ["10.00", "10.00", "10.00"]:  # 0.125 each: rounding the sum would give 0.38, not 0.39
        await make_order(total=total, installments=1, merchant=merchant)

    summary = (await client.get("/analytics/summary")).json()
    report = (await client.get("/analytics/revenue")).json()

    assert summary["total_revenue"] == report["totals"]["revenue"] == "0.39"
