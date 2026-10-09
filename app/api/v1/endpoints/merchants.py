import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Merchant
from app.db.schemas import MerchantCreateRequest, MerchantResponse
from app.db.session import get_db

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.post("/", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant(payload: MerchantCreateRequest, db: AsyncSession = Depends(get_db)) -> Merchant:
    merchant = Merchant(**payload.model_dump())
    db.add(merchant)
    await db.commit()
    await db.refresh(merchant)
    return merchant


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return merchant
