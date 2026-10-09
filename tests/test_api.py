import pytest


async def test_health_checks_the_database(client):
    r = await client.get("http://test/health")
    assert r.json() == {"status": "ok", "database": "ok"}


async def test_create_and_get_user(client):
    r = await client.post("/users/", json={"email": "Ana@Test.com", "full_name": "  Ana  "})

    assert r.status_code == 201
    user = r.json()
    assert (user["email"], user["full_name"]) == ("ana@test.com", "Ana")
    assert (await client.get(f"/users/{user['user_id']}")).json() == user


async def test_duplicate_email_is_a_conflict_regardless_of_case(client):
    await client.post("/users/", json={"email": "ana@test.com", "full_name": "Ana"})
    r = await client.post("/users/", json={"email": "ANA@TEST.COM", "full_name": "Ana"})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "body", [{"email": "not-an-email", "full_name": "Ana"}, {"email": "a@b.com", "full_name": "   "}]
)
async def test_invalid_user_is_rejected_with_details(client, body):
    r = await client.post("/users/", json=body)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)  # Pydantic's shape, unlike our domain errors


async def test_unknown_user_and_bad_uuid(client):
    assert (await client.get("/users/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await client.get("/users/hola")).status_code == 422


async def test_user_orders_history(client, make_user, make_order):
    user = await make_user()
    await make_order(user=user)
    await make_order(user=user)
    r = await client.get(f"/users/{user['user_id']}/orders")
    assert r.status_code == 200 and len(r.json()) == 2


async def test_merchant_commission_must_be_a_fraction(client):
    ok = await client.post(
        "/merchants/", json={"name": "Shop", "category": "retail", "commission_rate": "0.06"}
    )
    assert ok.status_code == 201
    assert (await client.get(f"/merchants/{ok.json()['merchant_id']}")).json()["commission_rate"] == "0.0600"
    bad = await client.post(
        "/merchants/", json={"name": "Shop", "category": "retail", "commission_rate": "1.5"}
    )
    assert bad.status_code == 422


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [("http://localhost:5173", True), ("http://127.0.0.1:5173", True), ("http://evil.example", False)],
)
async def test_cors_only_allows_the_dashboard_origins(client, origin, allowed):
    r = await client.options("/orders/", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert (r.status_code == 200) is allowed
    assert (r.headers.get("access-control-allow-origin") == origin) is allowed


async def test_unknown_merchant(client):
    assert (await client.get("/merchants/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_health_reports_degraded_when_the_database_is_down(client):
    from app.db.session import get_db
    from app.main import app

    class DownSession:
        async def execute(self, *args, **kwargs):
            raise OSError("connection refused")

    async def down_db():
        yield DownSession()

    app.dependency_overrides[get_db] = down_db
    try:
        r = await client.get("http://test/health")
    finally:
        app.dependency_overrides.clear()
    assert r.json() == {"status": "degraded", "database": "unreachable"}


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("POST", "/orders/00000000-0000-0000-0000-000000000000/risk", 404),  # domain error
        ("GET", "/users/hola", 422),  # validation error
        ("GET", "http://test/health", 200),
    ],
)
async def test_every_response_carries_security_headers(client, method, path, status):
    r = await client.request(method, path)

    assert r.status_code == status
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["strict-transport-security"].startswith("max-age=")


async def test_risk_decisions_are_never_cached(client, make_order):
    order = await make_order()
    r = await client.post(f"/orders/{order['order_id']}/risk")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
