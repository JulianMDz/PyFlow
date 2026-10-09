"""The demo seed doubles as a long integration test: months of simulated activity
through the real services must leave the data consistent."""

from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine
from scripts.seed_demo import seed


async def scalar(sql: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar_one()


async def test_seed_produces_consistent_data():
    async with AsyncSessionLocal() as db:
        stats = await seed(db, days=150, customers=20, rng_seed=1)

    assert stats["orders"] > 50 and stats["payments"] > 100
    assert stats["blocked_purchases"] > 0  # defaulters get blocked, as in production
    # installments add up to their order
    assert (
        await scalar(
            "SELECT count(*) FROM orders o WHERE total_amount <> "
            "(SELECT sum(amount) FROM installments i WHERE i.order_id = o.order_id)"
        )
        == 0
    )
    # one payment per paid installment, at the same instant, never before the order existed
    assert await scalar("SELECT count(*) FROM payments") == await scalar(
        "SELECT count(*) FROM installments WHERE status = 'paid'"
    )
    assert (
        await scalar(
            "SELECT count(*) FROM installments i JOIN payments p USING (installment_id) "
            "JOIN orders o USING (order_id) "
            "WHERE i.paid_at <> p.processed_at OR p.processed_at < o.created_at"
        )
        == 0
    )
    # states agree with each other
    assert (
        await scalar(
            "SELECT count(*) FROM orders o WHERE status = 'completed' AND EXISTS "
            "(SELECT 1 FROM installments i WHERE i.order_id = o.order_id AND i.status <> 'paid')"
        )
        == 0
    )
    assert (
        await scalar(
            "SELECT count(*) FROM orders o JOIN installments i USING (order_id) "
            "WHERE o.status = 'cancelled' AND i.status <> 'cancelled'"
        )
        == 0
    )
    assert (
        await scalar(
            "SELECT count(*) FROM installments WHERE status = 'overdue' AND due_date >= CURRENT_DATE"
        )
        == 0
    )
    assert await scalar("SELECT count(*) FROM installments WHERE status = 'overdue'") > 0
    assert (
        await scalar("SELECT count(*) FROM installments WHERE status = 'paid' AND paid_at::date > due_date")
        > 0
    )
