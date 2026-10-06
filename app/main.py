from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.schemas import HealthResponse
from app.db.session import get_db
from app.services.exceptions import BusinessRuleError, ConflictError, DomainError, NotFoundError

app = FastAPI(
    title="PayFlow",
    description="BNPL payment API — split purchases into interest-free installments.",
    version="0.1.0",
)

DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    BusinessRuleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = next(
        (code for cls, code in DOMAIN_ERROR_STATUS.items() if isinstance(exc, cls)),
        status.HTTP_400_BAD_REQUEST,
    )
    return JSONResponse(status_code=status_code, content={"detail": exc.detail})


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        return HealthResponse(status="degraded", database="unreachable")
    return HealthResponse(status="ok", database="ok")
