"""Fill the database with realistic demo data by simulating months of activity, day by day.

Customers place orders through the real services, pay according to their profile
(punctual, sometimes late, defaulter) and the overdue job runs every simulated day, so
every business rule holds: customers with overdue installments get blocked, late
payments are marked, and finished orders become completed.

Usage, from the project root:
    docker compose exec app python -m scripts.seed_demo --reset
"""

import argparse
import asyncio
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Installment, Merchant, Order, Payment, User
from app.db.schemas import OrderCreateRequest, PaymentCreateRequest, PaymentMethod
from app.db.session import AsyncSessionLocal
from app.services import order_service, payment_service
from app.services.exceptions import ConflictError
from app.services.order_service import today_utc

# name, category, commission rate, price range in dollars
MERCHANTS = [
    ("Northwind Electronics", "electronics", "0.0600", (180, 1200)),
    ("Bloom & Co.", "apparel", "0.0450", (40, 260)),
    ("Lumen Home", "home", "0.0500", (60, 650)),
    ("Summit Outdoor", "outdoor", "0.0550", (80, 700)),
    ("Pulse Fitness", "fitness", "0.0400", (30, 300)),
    ("Atlas Travel", "travel", "0.0700", (250, 1800)),
]
FIRST_NAMES = [
    "Ana",
    "Bruno",
    "Carla",
    "Diego",
    "Elena",
    "Felipe",
    "Gabriela",
    "Hugo",
    "Isabel",
    "Javier",
    "Karen",
    "Lucas",
    "Mariana",
    "Nicolás",
    "Olivia",
    "Pablo",
    "Renata",
    "Samuel",
    "Tamara",
    "Valentina",
    "Andrés",
    "Camila",
    "Daniel",
    "Emma",
    "Gonzalo",
    "Julia",
    "Martín",
    "Paula",
    "Sofía",
    "Tomás",
]
LAST_NAMES = [
    "García",
    "Martínez",
    "López",
    "Rodríguez",
    "Pérez",
    "Gómez",
    "Díaz",
    "Torres",
    "Ramírez",
    "Flores",
    "Rojas",
    "Vargas",
    "Castro",
    "Herrera",
    "Medina",
    "Silva",
    "Ortiz",
    "Morales",
    "Navarro",
    "Romero",
]
PROFILES = [("punctual", 0.70), ("sometimes_late", 0.20), ("defaulter", 0.10)]
METHODS: list[PaymentMethod] = ["card", "card", "card", "bank_transfer", "wallet"]


@dataclass
class Customer:
    user_id: str
    profile: str


def _ascii(name: str) -> str:
    return name.lower().translate(str.maketrans("áéíóúñ", "aeioun"))


def _at(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(rng.randint(8, 21), rng.randint(0, 59)), tzinfo=UTC)


def _payment_day(
    profile: str, due: date, ordered: date, index: int, stop_after: int, rng: random.Random
) -> date | None:
    """When this customer pays an installment, or None if they never do."""
    if profile == "defaulter" and index >= stop_after:
        return None
    if profile == "sometimes_late" and rng.random() < 0.35:
        return due + timedelta(days=rng.randint(1, 12))
    return max(ordered + timedelta(days=1), due - timedelta(days=rng.randint(0, 5)))


async def seed(
    db: AsyncSession, *, days: int = 340, customers: int = 60, rng_seed: int = 7, today: date | None = None
) -> Counter[str]:
    rng = random.Random(rng_seed)
    today = today or today_utc()
    start = today - timedelta(days=days)

    merchants = []
    for name, category, rate, prices in MERCHANTS:
        merchant = Merchant(name=name, category=category, commission_rate=Decimal(rate))
        db.add(merchant)
        merchants.append((merchant, prices))
    people: list[Customer] = []
    used: set[str] = set()
    for _ in range(customers):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{_ascii(first)}.{_ascii(last)}@example.com"
        while email in used:
            email = email.replace("@", f"{rng.randint(1, 99)}@", 1)
        used.add(email)
        user = User(email=email, full_name=f"{first} {last}")
        db.add(user)
        await db.flush()
        profile = rng.choices([p for p, _ in PROFILES], weights=[w for _, w in PROFILES])[0]
        people.append(Customer(str(user.user_id), profile))
    await db.commit()
    await db.execute(update(User).values(created_at=datetime.combine(start, time(9), tzinfo=UTC)))
    await db.commit()

    planned: dict[date, list[tuple[str, Decimal]]] = defaultdict(list)
    stats: Counter[str] = Counter()
    for offset in range(days + 1):
        day = start + timedelta(days=offset)

        # 1. payments customers make today
        for installment_id, amount in planned.pop(day, []):
            await payment_service.process_payment(
                db,
                PaymentCreateRequest(
                    installment_id=installment_id, method=rng.choice(METHODS), amount=amount
                ),
                now=_at(day, rng),
            )
            stats["payments"] += 1

        # 2. the daily overdue job
        await payment_service.mark_overdue_installments(db, today=day)

        # 3. new purchases, growing over time
        expected_orders = 0.4 + 1.8 * offset / days
        for _ in range(int(expected_orders) + (rng.random() < expected_orders % 1)):
            customer = rng.choice(people)
            merchant, (low, high) = rng.choice(merchants)
            total = Decimal(rng.randint(low * 100, high * 100)) / 100
            installments = 6 if total > 600 else rng.choice([4, 4, 4, 3])
            try:
                order = await order_service.create_order(
                    db,
                    OrderCreateRequest(
                        user_id=customer.user_id,
                        merchant_id=merchant.merchant_id,
                        total_amount=total,
                        num_installments=installments,
                    ),
                    today=day,
                )
            except ConflictError:  # overdue installments: blocked, as in production
                stats["blocked_purchases"] += 1
                continue
            await db.execute(
                update(Order).where(Order.order_id == order.order_id).values(created_at=_at(day, rng))
            )
            await db.commit()
            stats["orders"] += 1

            if rng.random() < 0.04:  # buyer's remorse, before any payment
                await order_service.cancel_order(db, order.order_id)
                stats["cancelled"] += 1
                continue
            stop_after = rng.randint(0, 2)
            for index, installment in enumerate(order.installments):
                pay_on = _payment_day(customer.profile, installment.due_date, day, index, stop_after, rng)
                if pay_on and pay_on <= today:
                    planned[pay_on].append((str(installment.installment_id), installment.amount))
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete ALL existing data first")
    parser.add_argument("--days", type=int, default=340)
    parser.add_argument("--customers", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7, help="random seed (same seed, same data)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(func.count()).select_from(Order))
        if existing and not args.reset:
            raise SystemExit(
                f"The database already has {existing} orders. Re-run with --reset to replace them."
            )
        if args.reset:
            await db.execute(text("TRUNCATE payments, installments, orders, merchants, users CASCADE"))
            await db.commit()
        stats = await seed(db, days=args.days, customers=args.customers, rng_seed=args.seed)

        rows = await db.execute(select(Order.status, func.count()).group_by(Order.status))
        by_status: dict[str, int] = {status: count for status, count in rows.all()}
        overdue = await db.scalar(select(func.count()).where(Installment.status == "overdue"))
        print(
            f"Seeded {args.customers} customers, {len(MERCHANTS)} merchants, {stats['orders']} orders "
            f"({by_status}), {await db.scalar(select(func.count()).select_from(Payment))} payments, "
            f"{overdue} overdue installments, {stats['blocked_purchases']} purchases blocked by overdue debt."
        )


if __name__ == "__main__":
    asyncio.run(main())
