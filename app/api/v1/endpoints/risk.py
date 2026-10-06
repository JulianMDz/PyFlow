import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import RiskAssessmentResponse
from app.db.session import get_db
from app.services import ai_service

router = APIRouter(prefix="/orders", tags=["risk"])


@router.post("/{order_id}/risk", response_model=RiskAssessmentResponse)
async def assess_order_risk(
    order_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RiskAssessmentResponse:
    return await ai_service.assess_order_risk(db, order_id)
