from datetime import date, timedelta

import pytest

from app.services.order_service import today_utc
from tests.conftest import money


async def test_create_order_generates_correct_installments(make_order):
    order = await make_order(total="100.00", installments=4)

    assert order["status"] == "active"
    installments = order["installments"]
    assert len(installments) == 4
    assert [i["amount"] for i in installments] == ["25.00"] * 4
    assert all(i["status"] == "pending" and i["paid_at"] is None for i in installments)
    today = today_utc()
    assert [date.fromisoformat(i["due_date"]) for i in installments] == [
        today + timedelta(days=14 * k) for k in range(1, 5)
    ]


@pytest.mark.parametrize(
    ("total", "n", "first", "rest"),
    [
        ("100.00", 3, "33.34", "33.33"),
        ("999.99", 12, "83.36", "83.33"),
        ("0.05", 4, "0.02", "0.01"),
        ("0.04", 4, "0.01", "0.01"),
        ("10", 1, "10.00", None),
    ],
)
async def test_order_installment_amounts_sum_to_total(make_order, total, n, first, rest):
    order = await make_order(total=total, installments=n)

    amounts = [money(i["amount"]) for i in order["installments"]]
    assert sum(amounts) == money(total)
    assert amounts[0] == money(first)  # leftover cents go to the first installment
    assert all(a == money(rest) for a in amounts[1:])


async def test_order_total_is_returned_as_stored(make_order):
    order = await make_order(total="100")
    assert order["total_amount"] == "100.00"


@pytest.mark.parametrize("status", ["pending", "overdue"])
async def test_order_denied_if_user_has_overdue_installments(client, make_order, make_past_due, status):
    first = await make_order()
    await make_past_due(first["installments"][0], status=status)

    r = await client.post(
        "/orders/",
        json={"user_id": first["user_id"], "merchant_id": first["merchant_id"], "total_amount": "50.00"},
    )

    assert r.status_code == 409
    assert r.json()["detail"] == "User has overdue installments"


async def test_order_amount_too_small_for_installments(client, make_user, make_merchant):
    user, merchant = await make_user(), await make_merchant()
    r = await client.post(
        "/orders/",
        json={
            "user_id": user["user_id"],
            "merchant_id": merchant["merchant_id"],
            "total_amount": "0.03",
            "num_installments": 4,
        },
    )
    assert r.status_code == 422
    assert "at least 0.04" in r.json()["detail"]


@pytest.mark.parametrize("missing", ["user_id", "merchant_id"])
async def test_order_with_unknown_user_or_merchant(client, make_user, make_merchant, missing):
    body = {
        "user_id": (await make_user())["user_id"],
        "merchant_id": (await make_merchant())["merchant_id"],
        "total_amount": "10",
    }
    body[missing] = "00000000-0000-0000-0000-000000000000"
    r = await client.post("/orders/", json=body)
    assert r.status_code == 404


async def test_get_order_includes_installments(client, make_order):
    order = await make_order(installments=3)
    r = await client.get(f"/orders/{order['order_id']}")
    assert r.status_code == 200
    assert len(r.json()["installments"]) == 3
    assert (await client.get("/orders/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_cancel_order_with_no_payments(client, make_order):
    order = await make_order()

    r = await client.patch(f"/orders/{order['order_id']}/cancel")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"
    assert {i["status"] for i in body["installments"]} == {"cancelled"}
    again = await client.patch(f"/orders/{order['order_id']}/cancel")
    assert again.status_code == 409


async def test_cancel_order_with_payments_is_rejected(client, make_order, pay):
    order = await make_order()
    assert (await pay(order["installments"][0])).status_code == 201

    r = await client.patch(f"/orders/{order['order_id']}/cancel")

    assert r.status_code == 409
    assert r.json()["detail"] == "Order has payments and cannot be cancelled"


async def test_list_orders_paginates_newest_first_and_filters(client, make_order, make_user, make_merchant):
    user, merchant = await make_user(), await make_merchant()
    created = [await make_order(total=f"{10 + k}.00", user=user, merchant=merchant) for k in range(5)]
    await client.patch(f"/orders/{created[0]['order_id']}/cancel")

    page1 = (await client.get("/orders/", params={"limit": 2})).json()
    page2 = (await client.get("/orders/", params={"limit": 2, "offset": 2})).json()

    assert page1["total"] == 5
    newest_first = [o["order_id"] for o in reversed(created)]
    assert [o["order_id"] for o in page1["items"] + page2["items"]] == newest_first[:4]
    assert page1["items"][0]["user"]["email"] == user["email"]
    assert page1["items"][0]["merchant"]["name"] == "Shop"

    cancelled = (await client.get("/orders/", params={"status": "cancelled"})).json()
    assert cancelled["total"] == 1 and cancelled["items"][0]["order_id"] == created[0]["order_id"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"status": "foo"}])
async def test_list_orders_rejects_invalid_params(client, params):
    assert (await client.get("/orders/", params=params)).status_code == 422
