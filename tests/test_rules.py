"""Pure business rules: no database, no HTTP."""

import itertools
from datetime import date
from decimal import Decimal

import pytest

from app.db.schemas import RiskFeatures
from app.services.ai_service import risk_level_for, score_with_rules
from app.services.analytics_service import default_start, month_range
from app.services.exceptions import BusinessRuleError
from app.services.order_service import build_due_dates, split_amount


@pytest.mark.parametrize(
    ("total", "n"),
    list(
        itertools.product(
            ["0.12", "1.00", "10.01", "99.99", "100.00", "333.33", "1000.07", "999999.99"], range(1, 13)
        )
    ),
)
def test_split_amount_always_adds_up_exactly(total, n):
    amount = Decimal(total)
    if amount < Decimal("0.01") * n:
        pytest.skip("too small for this many installments")
    parts = split_amount(amount, n)

    assert len(parts) == n
    assert sum(parts) == amount
    assert all(p >= Decimal("0.01") and p == p.quantize(Decimal("0.01")) for p in parts)
    assert all(p == parts[1] for p in parts[1:])  # all but the first are equal
    assert Decimal("0") <= parts[0] - parts[-1] < Decimal("0.01") * n


def test_split_amount_rejects_less_than_a_cent_per_installment():
    with pytest.raises(BusinessRuleError):
        split_amount(Decimal("0.03"), 4)


def test_due_dates_every_14_days_across_the_new_year():
    assert build_due_dates(date(2026, 12, 20), 4) == [
        date(2027, 1, 3),
        date(2027, 1, 17),
        date(2027, 1, 31),
        date(2027, 2, 14),
    ]


def features(**kw) -> RiskFeatures:
    base = dict(
        total_orders=0,
        on_time_payments=0,
        late_payments=0,
        active_installments=0,
        requested_amount=Decimal("100"),
        avg_order_amount=Decimal("0"),
    )
    return RiskFeatures(**(base | kw))


@pytest.mark.parametrize(
    ("kw", "score"),
    [
        ({}, 30),  # new user, small amount
        ({"requested_amount": Decimal("800")}, 45),  # big first purchase
        ({"total_orders": 2, "on_time_payments": 8, "avg_order_amount": Decimal("120")}, 15),
        (
            {
                "total_orders": 1,
                "late_payments": 1,
                "active_installments": 4,
                "avg_order_amount": Decimal("200"),
            },
            63,
        ),
        (
            {
                "total_orders": 5,
                "on_time_payments": 20,
                "late_payments": 2,
                "avg_order_amount": Decimal("100"),
            },
            65,
        ),  # -15 cap
        ({"total_orders": 1, "avg_order_amount": Decimal("40")}, 45),  # more than twice the average
    ],
)
def test_rule_based_scores(kw, score):
    assert score_with_rules(features(**kw))[0] == score


@pytest.mark.parametrize(
    ("score", "level"), [(0, "LOW"), (39, "LOW"), (40, "MEDIUM"), (70, "MEDIUM"), (71, "HIGH"), (100, "HIGH")]
)
def test_risk_level_bands(score, level):
    assert risk_level_for(score) == level


def test_report_month_helpers():
    assert default_start(date(2026, 10, 6)) == date(2025, 11, 1)
    assert month_range(date(2025, 11, 15), date(2026, 2, 3)) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_split_amount_needs_at_least_one_installment():
    with pytest.raises(BusinessRuleError):
        split_amount(Decimal("10.00"), 0)


def test_groq_client_fails_fast(monkeypatch):
    from app.core.config import settings
    from app.services.ai_service import LLM_TIMEOUT_SECONDS, get_groq_client

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    get_groq_client.cache_clear()
    try:
        groq = get_groq_client()
        assert (groq.timeout, groq.max_retries) == (LLM_TIMEOUT_SECONDS, 1)
        assert get_groq_client() is groq  # one client per process
    finally:
        get_groq_client.cache_clear()
