"""Settings and guards that matter once the API is public: provider URLs, CORS, demo mode, rate limit."""

import pytest

from app.api.deps import RateLimiter, risk_limiter
from app.core.config import Settings, settings

ZERO_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Render hands out postgresql:// (internal URL, no SSL options)
        ("postgresql://u:p@db-host/payflow", "postgresql+asyncpg://u:p@db-host/payflow"),
        # Heroku-style scheme
        ("postgres://u:p@db-host:5432/payflow", "postgresql+asyncpg://u:p@db-host:5432/payflow"),
        # Neon: libpq SSL options asyncpg would reject
        (
            "postgresql://u:p@ep-x.neon.tech/payflow?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@ep-x.neon.tech/payflow?ssl=require",
        ),
        # Already in the app's format: untouched
        (
            "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow",
            "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow",
        ),
        # Not Postgres: left for SQLAlchemy to judge
        ("sqlite+aiosqlite:///payflow.db", "sqlite+aiosqlite:///payflow.db"),
    ],
)
def test_provider_database_urls_are_converted_to_asyncpg(given, expected):
    url = Settings(DATABASE_URL=given).DATABASE_URL
    assert url == expected


def test_passwords_with_special_characters_survive_the_conversion():
    url = Settings(DATABASE_URL="postgresql://u:p%40ss%2Fw@host/db").DATABASE_URL
    assert url == "postgresql+asyncpg://u:p%40ss%2Fw@host/db"


@pytest.mark.parametrize(
    "raw",
    [
        '["https://a.example.com", "https://b.example.com"]',
        "https://a.example.com, https://b.example.com",
    ],
)
def test_cors_origins_accept_json_or_comma_separated(monkeypatch, raw):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings().CORS_ORIGINS == ["https://a.example.com", "https://b.example.com"]


# ---------- demo mode ----------


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/users/", {"email": "ana@test.com", "full_name": "Ana"}),
        ("POST", "/merchants/", {"name": "Shop", "category": "retail", "commission_rate": "0.05"}),
        ("POST", "/orders/", {}),
        ("PATCH", f"/orders/{ZERO_ID}/cancel", None),
        ("POST", "/payments/", {}),
        ("POST", "/installments/check-overdue", None),
    ],
)
async def test_demo_mode_rejects_every_write(client, demo_mode, method, path, body):
    r = await client.request(method, path, json=body)

    assert r.status_code == 403
    assert "read-only demo" in r.json()["detail"]


async def test_demo_mode_creates_nothing(client, demo_mode):
    await client.post("/users/", json={"email": "ana@test.com", "full_name": "Ana"})
    assert (await client.get("/orders/")).json()["total"] == 0
    assert (await client.get("/analytics/summary")).status_code == 200


async def test_demo_mode_still_allows_reads_and_risk_checks(client, make_order, monkeypatch):
    order = await make_order()
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    assert (await client.get(f"/orders/{order['order_id']}")).status_code == 200
    assert (await client.post(f"/orders/{order['order_id']}/risk")).status_code == 200


# ---------- risk rate limit ----------


@pytest.fixture
def risk_limit(monkeypatch):
    monkeypatch.setattr(settings, "RISK_CHECKS_PER_MINUTE", 2)
    risk_limiter.reset()
    yield
    risk_limiter.reset()


async def test_risk_checks_are_rate_limited_per_client(client, make_order, risk_limit):
    order = await make_order()
    path = f"/orders/{order['order_id']}/risk"

    assert [(await client.post(path)).status_code for _ in range(2)] == [200, 200]
    r = await client.post(path)

    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert r.headers["cache-control"] == "no-store"  # security headers on errors too


async def test_the_limit_counts_every_attempt_even_failed_ones(client, risk_limit):
    # The limit runs before the service: the 404s count, so probing random IDs is limited too
    statuses = [(await client.post(f"/orders/{ZERO_ID}/risk")).status_code for _ in range(3)]
    assert statuses == [404, 404, 429]


def test_rate_limiter_window_slides():
    limiter = RateLimiter(window_seconds=60)

    assert limiter.retry_after("ip-1", limit=2, now=0) is None
    assert limiter.retry_after("ip-1", limit=2, now=10) is None
    assert limiter.retry_after("ip-1", limit=2, now=20) == 40  # oldest hit expires at t=60
    assert limiter.retry_after("ip-2", limit=2, now=20) is None  # other clients unaffected
    assert limiter.retry_after("ip-1", limit=2, now=60) is None  # first hit left the window
