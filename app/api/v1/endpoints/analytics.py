from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import DashboardSummaryResponse, RevenueReportResponse
from app.db.session import get_db
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/revenue", response_model=RevenueReportResponse)
async def revenue_report(
    start: date | None = None, end: date | None = None, db: AsyncSession = Depends(get_db)
) -> RevenueReportResponse:
    """Defaults to the last 12 months (UTC), ending today."""
    return await analytics_service.revenue_report(db, start, end)


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummaryResponse:
    return await analytics_service.dashboard_summary(db)
