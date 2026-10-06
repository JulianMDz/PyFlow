import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]

OrderStatus = Literal["active", "completed", "cancelled"]
InstallmentStatus = Literal["pending", "paid", "overdue", "cancelled"]
PaymentMethod = Literal["card", "bank_transfer", "wallet"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
Recommendation = Literal["APPROVE", "REVIEW", "DENY"]
RiskSource = Literal["llm", "rules"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Users ----------


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: NonEmptyStr


class UserResponse(ORMModel):
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    created_at: datetime


# ---------- Merchants ----------


class MerchantCreateRequest(BaseModel):
    name: NonEmptyStr
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    commission_rate: Annotated[
        Decimal,
        Field(ge=0, le=1, max_digits=5, decimal_places=4, description="Fraction, e.g. 0.06 = 6%"),
    ]


class MerchantResponse(ORMModel):
    merchant_id: uuid.UUID
    name: str
    category: str
    commission_rate: Decimal


# ---------- Installments ----------


class InstallmentResponse(ORMModel):
    installment_id: uuid.UUID
    order_id: uuid.UUID
    due_date: date
    amount: Decimal
    status: InstallmentStatus
    paid_at: datetime | None


class OverdueCheckResponse(BaseModel):
    as_of: date
    marked_overdue: int


# ---------- Orders ----------


class OrderCreateRequest(BaseModel):
    user_id: uuid.UUID
    merchant_id: uuid.UUID
    total_amount: Money
    num_installments: Annotated[int, Field(ge=1, le=12)] = 4


class OrderResponse(ORMModel):
    order_id: uuid.UUID
    user_id: uuid.UUID
    merchant_id: uuid.UUID
    total_amount: Decimal
    num_installments: int
    status: OrderStatus
    created_at: datetime


class OrderDetailResponse(OrderResponse):
    installments: list[InstallmentResponse]


class OrderListItemResponse(OrderDetailResponse):
    user: UserResponse
    merchant: MerchantResponse


class OrderPageResponse(BaseModel):
    items: list[OrderListItemResponse]
    total: int
    limit: int
    offset: int


# ---------- Payments ----------


class PaymentCreateRequest(BaseModel):
    installment_id: uuid.UUID
    method: PaymentMethod
    amount: Money


class PaymentResponse(ORMModel):
    payment_id: uuid.UUID
    installment_id: uuid.UUID
    method: str
    amount: Decimal
    processed_at: datetime


# ---------- Risk ----------


class RiskFeatures(BaseModel):
    """Aggregated history the score is based on (never names or emails)."""

    total_orders: int
    on_time_payments: int
    late_payments: int
    active_installments: int
    requested_amount: Decimal
    avg_order_amount: Decimal


class RiskAssessmentResponse(BaseModel):
    order_id: uuid.UUID
    score: Annotated[int, Field(ge=0, le=100, description="0 = lowest risk, 100 = highest")]
    risk_level: RiskLevel
    recommendation: Recommendation
    reasoning: str
    source: RiskSource
    llm_model: str | None
    features: RiskFeatures


# ---------- Analytics ----------


class RevenueTotals(BaseModel):
    orders: int
    gmv: Decimal = Field(description="Value of non-cancelled orders created in the period")
    revenue: Decimal = Field(description="Merchant commissions on those orders")
    collected: Decimal = Field(description="Installment payments processed in the period")


class RevenueMonth(RevenueTotals):
    month: str = Field(description="YYYY-MM, UTC")


class RevenueReportResponse(BaseModel):
    start: date
    end: date
    totals: RevenueTotals
    by_month: list[RevenueMonth]


class DashboardSummaryResponse(BaseModel):
    as_of: date
    active_orders: int
    total_revenue: Decimal
    overdue_installments: int
    on_time_payment_rate: float | None = Field(
        description="Paid on time / installments already due (paid or overdue); null if none"
    )


# ---------- Health ----------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unreachable"]
