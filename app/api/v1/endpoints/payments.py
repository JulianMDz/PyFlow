from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.db.schemas import PaymentCreateRequest, PaymentResponse
from app.db.session import get_db
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreateRequest, db: AsyncSession = Depends(get_db)
) -> Payment:
    return await payment_service.process_payment(db, payload)
