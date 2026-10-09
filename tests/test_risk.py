import json
from types import SimpleNamespace

import httpx
import pytest
from groq import APITimeoutError

from app.core.config import settings
from app.services import ai_service

VALID = {
    "score": 12,
    "risk_level": "LOW",
    "recommendation": "APPROVE",
    "reasoning": "Buen historial de pagos",
}


@pytest.fixture
def fake_groq(mocker):
    """Replace the Groq client: `respond(...)` sets the model's raw text, `fail(...)` an exception."""
    mocker.patch.object(settings, "GROQ_API_KEY", "test-key")
    create = mocker.AsyncMock()

    def respond(content: str | dict) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        create.side_effect = None
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )

    def fail(error: Exception) -> None:
        create.side_effect = error

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    mocker.patch.object(ai_service, "get_groq_client", return_value=client)
    return SimpleNamespace(create=create, respond=respond, fail=fail)


async def assess(client, order) -> dict:
    r = await client.post(f"/orders/{order['order_id']}/risk")
    assert r.status_code == 200, r.text
    return r.json()


async def clean_user_with_new_order(make_order, make_user, make_merchant, pay):
    user, merchant = await make_user(), await make_merchant()
    for _ in range(2):
        paid = await make_order(total="120.00", user=user, merchant=merchant)
        for installment in paid["installments"]:
            await pay(installment)
    return user, await make_order(total="130.00", user=user, merchant=merchant)


async def test_risk_endpoint_returns_valid_schema(client, make_order, fake_groq):
    fake_groq.respond(VALID)
    order = await make_order()

    body = await assess(client, order)

    assert body["order_id"] == order["order_id"]
    assert (body["score"], body["risk_level"], body["recommendation"]) == (12, "LOW", "APPROVE")
    assert body["source"] == "llm" and body["llm_model"] == settings.GROQ_MODEL
    assert set(body["features"]) == {
        "total_orders",
        "on_time_payments",
        "late_payments",
        "active_installments",
        "requested_amount",
        "avg_order_amount",
    }
    call = fake_groq.create.await_args.kwargs
    assert call["response_format"] == {"type": "json_object"}
    assert (call["temperature"], call["max_tokens"]) == (0.1, 256)


async def test_risk_low_score_for_clean_user(client, make_order, make_user, make_merchant, pay):
    _, order = await clean_user_with_new_order(make_order, make_user, make_merchant, pay)

    body = await assess(client, order)  # no API key in tests -> deterministic rules

    assert body["source"] == "rules"
    features = body["features"]
    assert (features["total_orders"], features["on_time_payments"], features["late_payments"]) == (2, 8, 0)
    assert features["avg_order_amount"] == "120.00"
    assert body["score"] < 40
    assert (body["risk_level"], body["recommendation"]) == ("LOW", "APPROVE")


async def test_risk_high_score_for_user_with_overdue(
    client, make_order, make_user, make_merchant, make_past_due, pay
):
    user, merchant = await make_user(), await make_merchant()
    old = await make_order(total="200.00", user=user, merchant=merchant)
    new = await make_order(total="90.00", user=user, merchant=merchant)
    await pay(old["installments"][0])
    await make_past_due(old["installments"][0], status="paid")  # paid, but after its due date
    await make_past_due(old["installments"][1], status="overdue")

    body = await assess(client, new)

    assert body["features"]["late_payments"] == 2
    assert body["score"] > 70
    assert (body["risk_level"], body["recommendation"]) == ("HIGH", "DENY")


async def test_assessed_order_and_cancelled_orders_are_not_history(
    client, make_order, make_user, make_merchant
):
    user, merchant = await make_user(), await make_merchant()
    cancelled = await make_order(total="999.00", user=user, merchant=merchant)
    await client.patch(f"/orders/{cancelled['order_id']}/cancel")
    order = await make_order(total="50.00", user=user, merchant=merchant)

    features = (await assess(client, order))["features"]

    assert (features["total_orders"], features["active_installments"], features["avg_order_amount"]) == (
        0,
        0,
        "0.00",
    )


async def test_prompt_contains_only_aggregates(client, make_order, make_user, fake_groq):
    fake_groq.respond(VALID)
    user = await make_user(email="private.person@example.com")
    order = await make_order(user=user)

    await assess(client, order)

    prompt = fake_groq.create.await_args.kwargs["messages"][0]["content"]
    assert "private.person@example.com" not in prompt
    assert user["full_name"] not in prompt and order["order_id"] not in prompt
    assert "Requested amount: $100.00" in prompt
    assert '{\n  "score"' in prompt  # schema braces survived str.format()


async def test_policy_overrides_a_contradictory_model(client, make_order, fake_groq):
    fake_groq.respond({**VALID, "score": 85})  # 85 labelled LOW / APPROVE

    body = await assess(client, await make_order())

    assert (body["score"], body["risk_level"], body["recommendation"]) == (85, "HIGH", "DENY")


async def test_guardrail_never_approves_late_payers(
    client, make_order, make_user, make_merchant, make_past_due, fake_groq
):
    fake_groq.respond({**VALID, "score": 10})
    user, merchant = await make_user(), await make_merchant()
    old = await make_order(user=user, merchant=merchant)
    new = await make_order(user=user, merchant=merchant)
    await make_past_due(old["installments"][0])

    body = await assess(client, new)

    assert body["source"] == "llm"
    assert (body["score"], body["risk_level"], body["recommendation"]) == (40, "MEDIUM", "REVIEW")


async def test_long_reasoning_is_truncated(client, make_order, fake_groq):
    fake_groq.respond({**VALID, "reasoning": "x" * 150})
    body = await assess(client, await make_order())
    assert body["source"] == "llm" and len(body["reasoning"]) == 100


@pytest.mark.parametrize(
    "content",
    [
        "Claro, el score es 20",  # not JSON
        {**VALID, "score": 150},  # out of range
        {**VALID, "risk_level": "Low"},  # not in the enum
        {"score": 10},  # missing fields
    ],
)
async def test_unusable_model_output_falls_back_to_rules(client, make_order, fake_groq, content):
    fake_groq.respond(content)
    body = await assess(client, await make_order())
    assert body["source"] == "rules" and body["llm_model"] is None


async def test_model_timeout_falls_back_to_rules(client, make_order, fake_groq):
    fake_groq.fail(APITimeoutError(request=httpx.Request("POST", "https://api.groq.com")))
    body = await assess(client, await make_order())
    assert body["source"] == "rules"


async def test_risk_for_unknown_order(client):
    r = await client.post("/orders/00000000-0000-0000-0000-000000000000/risk")
    assert r.status_code == 404
