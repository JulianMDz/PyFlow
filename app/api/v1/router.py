from fastapi import APIRouter

from app.api.v1.endpoints import installments, merchants, orders, payments, risk, users

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(merchants.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(installments.router)
api_router.include_router(risk.router)
