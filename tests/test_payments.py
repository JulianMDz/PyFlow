import asyncio
import uuid
from collections import Counter

from sqlalchemy import func, select

from app.db.models import Payment
from app.db.session import engine


async def payment_rows(installment_id: str) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.installment_id == uuid.UUID(installment_id))
        )


async def test_payment_marks_installment_as_paid(client, make_order, pay):
    order = await make_order()
    first = order["installments"][0]

    r = await pay(first)

    assert r.status_code == 201
    payment = r.json()
    assert payment["amount"] == first["amount"]
    stored = (await client.get(f"/orders/{order['order_id']}")).json()
    paid = stored["installments"][0]
    assert paid["status"] == "paid"
    assert paid["paid_at"] == payment["processed_at"]  # one timestamp for both
    assert stored["status"] == "active"


async def test_payment_wrong_amount_is_rejected(make_order, pay):
    order = await make_order(total="100.00")

    r = await pay(order["installments"][0], amount="24.99")

    assert r.status_code == 422
    assert "must equal the installment amount (25.00)" in r.json()["detail"]
    assert await payment_rows(order["installments"][0]["installment_id"]) == 0


async def test_invalid_method_and_unknown_installment(client, make_order, pay):
    order = await make_order()
    assert (await pay(order["installments"][0], method="cash")).status_code == 422
    r = await client.post(
        "/payments/",
        json={"installment_id": "00000000-0000-0000-0000-000000000000", "method": "card", "amount": "10.00"},
    )
    assert r.status_code == 404


async def test_all_installments_paid_completes_order(client, make_order, pay):
    order = await make_order(total="30.00", installments=3)

    for installment in order["installments"]:
        assert (await pay(installment)).status_code == 201

    assert (await client.get(f"/orders/{order['order_id']}")).json()["status"] == "completed"


async def test_paying_twice_is_a_conflict(make_order, pay):
    order = await make_order()
    first = order["installments"][0]
    assert (await pay(first)).status_code == 201

    r = await pay(first)

    assert r.status_code == 409
    assert r.json()["detail"] == "Installment is not payable (status: paid)"


async def test_cancelled_order_installments_are_not_payable(client, make_order, pay):
    order = await make_order()
    await client.patch(f"/orders/{order['order_id']}/cancel")
    assert (await pay(order["installments"][0])).status_code == 409


async def test_concurrent_payments_charge_an_installment_once(make_order, pay):
    """Five simultaneous requests for the same installment: exactly one may succeed."""
    order = await make_order()
    first = order["installments"][0]

    responses = await asyncio.gather(*(pay(first) for _ in range(5)))

    assert Counter(r.status_code for r in responses) == Counter({201: 1, 409: 4})
    assert await payment_rows(first["installment_id"]) == 1


async def test_concurrent_last_payments_still_complete_the_order(client, make_order, pay):
    """Both remaining installments paid at the same time: one of them must see the other."""
    for _ in range(5):
        order = await make_order(total="20.00", installments=2)
        a, b = order["installments"]

        ra, rb = await asyncio.gather(pay(a), pay(b))

        assert (ra.status_code, rb.status_code) == (201, 201)
        assert (await client.get(f"/orders/{order['order_id']}")).json()["status"] == "completed"


async def test_overdue_installment_is_payable(make_order, make_past_due, pay):
    order = await make_order()
    await make_past_due(order["installments"][0], status="overdue")
    assert (await pay(order["installments"][0])).status_code == 201


async def test_check_overdue_marks_past_due_and_is_idempotent(client, make_order, make_past_due):
    order = await make_order()
    await make_past_due(order["installments"][0])

    first = (await client.post("/installments/check-overdue")).json()
    second = (await client.post("/installments/check-overdue")).json()

    assert first["marked_overdue"] == 1
    assert second["marked_overdue"] == 0
    statuses = [
        i["status"] for i in (await client.get(f"/orders/{order['order_id']}")).json()["installments"]
    ]
    assert statuses == ["overdue", "pending", "pending", "pending"]
