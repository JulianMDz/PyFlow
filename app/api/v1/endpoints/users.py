import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Order, User
from app.db.schemas import OrderDetailResponse, UserCreateRequest, UserResponse
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])


async def get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreateRequest, db: AsyncSession = Depends(get_db)) -> User:
    user = User(email=payload.email.lower(), full_name=payload.full_name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from None
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> User:
    return await get_user_or_404(db, user_id)


@router.get("/{user_id}/orders", response_model=list[OrderDetailResponse])
async def list_user_orders(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Order]:
    await get_user_or_404(db, user_id)
    result = await db.scalars(
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.installments))
        .order_by(Order.created_at.desc())
    )
    return list(result.all())
