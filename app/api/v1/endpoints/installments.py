from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import OverdueCheckResponse
from app.db.session import get_db
from app.services import payment_service
from app.services.order_service import today_utc

router = APIRouter(prefix="/installments", tags=["installments"])


@router.post("/check-overdue", response_model=OverdueCheckResponse)
async def check_overdue(db: AsyncSession = Depends(get_db)) -> OverdueCheckResponse:
    today = today_utc()
    marked = await payment_service.mark_overdue_installments(db, today)
    return OverdueCheckResponse(as_of=today, marked_overdue=marked)
