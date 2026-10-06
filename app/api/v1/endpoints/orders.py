import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order
from app.db.schemas import OrderCreateRequest, OrderDetailResponse, OrderPageResponse, OrderStatus
from app.db.session import get_db
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/", response_model=OrderPageResponse)
async def list_orders(
    status: OrderStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db),
) -> OrderPageResponse:
    orders, total = await order_service.list_orders(db, status, limit, offset)
    return OrderPageResponse.model_validate(
        {"items": orders, "total": total, "limit": limit, "offset": offset}, from_attributes=True
    )


@router.post("/", response_model=OrderDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreateRequest, db: AsyncSession = Depends(get_db)) -> Order:
    return await order_service.create_order(db, payload)


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Order:
    return await order_service.get_order(db, order_id)


@router.patch("/{order_id}/cancel", response_model=OrderDetailResponse)
async def cancel_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Order:
    return await order_service.cancel_order(db, order_id)
