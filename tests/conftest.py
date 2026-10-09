"""Shared fixtures: a disposable test database, an HTTP client and small data factories.

The environment is configured before any `app` module is imported, so the app's
settings, engine and Groq client all point at the test setup.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = "payflow_test"

# Same server as the app (localhost from Windows, "db" inside Docker), separate database
_base_url = os.environ.get("DATABASE_URL") or dotenv_values(ROOT / ".env").get(
    "DATABASE_URL", "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow"
)
TEST_DATABASE_URL = _base_url.rsplit("/", 1)[0] + f"/{TEST_DB}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["GROQ_API_KEY"] = ""  # tests never call the real LLM

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

Json = dict[str, Any]


async def _recreate_test_database() -> None:
    admin_dsn = TEST_DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Fresh database per run, built with the real Alembic migrations."""
    asyncio.run(_recreate_test_database())
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE payments, installments, orders, merchants, users CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as c:
        yield c


async def run_sql(sql: str, **params: Any) -> None:
    """Shortcut for states the API can't produce on demand, e.g. a due date in the past."""
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


# ---------- factories ----------


@pytest.fixture
def make_user(client: AsyncClient) -> Callable[..., Awaitable[Json]]:
    counter = iter(range(1, 10_000))

    async def _make(email: str | None = None) -> Json:
        n = next(counter)
        r = await client.post(
            "/users/", json={"email": email or f"user{n}@test.com", "full_name": f"User {n}"}
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make


@pytest.fixture
def make_merchant(client: AsyncClient) -> Callable[..., Awaitable[Json]]:
    async def _make(commission_rate: str = "0.05") -> Json:
        r = await client.post(
            "/merchants/", json={"name": "Shop", "category": "retail", "commission_rate": commission_rate}
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make


@pytest.fixture
def make_order(client: AsyncClient, make_user, make_merchant) -> Callable[..., Awaitable[Json]]:
    async def _make(
        total: str = "100.00", installments: int = 4, user: Json | None = None, merchant: Json | None = None
    ) -> Json:
        user = user or await make_user()
        merchant = merchant or await make_merchant()
        r = await client.post(
            "/orders/",
            json={
                "user_id": user["user_id"],
                "merchant_id": merchant["merchant_id"],
                "total_amount": total,
                "num_installments": installments,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make


@pytest.fixture
def pay(client: AsyncClient) -> Callable[..., Awaitable[Any]]:
    async def _pay(installment: Json, amount: str | None = None, method: str = "card"):
        return await client.post(
            "/payments/",
            json={
                "installment_id": installment["installment_id"],
                "method": method,
                "amount": amount or installment["amount"],
            },
        )

    return _pay


@pytest.fixture
def make_past_due() -> Callable[..., Awaitable[None]]:
    """Move an installment's due date to yesterday (still 'pending' unless status is given)."""

    async def _make(installment: Json, status: str = "pending") -> None:
        await run_sql(
            "UPDATE installments SET due_date = CURRENT_DATE - 1, status = :status "
            "WHERE installment_id = :id",
            status=status,
            id=installment["installment_id"],
        )

    return _make


def money(value: str | Decimal) -> Decimal:
    return Decimal(str(value))
