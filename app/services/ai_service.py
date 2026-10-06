import logging
import uuid
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from groq import APIError, AsyncGroq
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Installment, Order
from app.db.schemas import Recommendation, RiskAssessmentResponse, RiskFeatures, RiskLevel
from app.services.exceptions import NotFoundError
from app.services.installment_rules import is_overdue, is_paid_late, is_paid_on_time
from app.services.order_service import CENT, today_utc

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 8.0
REASONING_MAX_CHARS = 100
# Guardrail: a user with late installments is never auto-approved, whatever the model says
LATE_PAYMENT_SCORE_FLOOR = 40

RECOMMENDATION_FOR: dict[RiskLevel, Recommendation] = {
    "LOW": "APPROVE",
    "MEDIUM": "REVIEW",
    "HIGH": "DENY",
}

# Literal braces of the JSON schema are doubled because the prompt goes through str.format()
RISK_PROMPT = """
Eres un motor de scoring de riesgo crediticio para una plataforma BNPL.
Analiza los siguientes datos y responde SOLO con JSON válido.

Historial del usuario:
- Órdenes totales: {total_orders}
- Cuotas pagadas a tiempo: {on_time_payments}
- Cuotas vencidas (pagadas con atraso o vencidas sin pagar): {late_payments}
- Cuotas pendientes activas: {active_installments}
- Monto solicitado: ${requested_amount}
- Monto promedio histórico: ${avg_order_amount}

El score mide el RIESGO: 0 = riesgo mínimo, 100 = riesgo máximo.
risk_level: LOW si score < 40, MEDIUM si score está entre 40 y 70, HIGH si score > 70.
recommendation: LOW → APPROVE, MEDIUM → REVIEW, HIGH → DENY.

Schema de respuesta (exacto):
{{
  "score": <int 0-100>,
  "risk_level": <"LOW" | "MEDIUM" | "HIGH">,
  "recommendation": <"APPROVE" | "REVIEW" | "DENY">,
  "reasoning": <string, máximo 100 caracteres>
}}
"""


class RiskModelUnavailable(Exception):
    """The LLM could not produce a usable answer; the caller falls back to rules."""


class LLMRiskOutput(BaseModel):
    """Contract the model's JSON must satisfy before we trust any of it."""

    score: Annotated[int, Field(ge=0, le=100)]
    risk_level: RiskLevel
    recommendation: Recommendation
    reasoning: str

    @field_validator("reasoning")
    @classmethod
    def truncate_reasoning(cls, value: str) -> str:
        return value.strip()[:REASONING_MAX_CHARS]


async def build_risk_features(db: AsyncSession, order: Order, today: date) -> RiskFeatures:
    """Aggregate the user's history, excluding the order being assessed."""
    history = and_(Order.user_id == order.user_id, Order.order_id != order.order_id)

    total_orders, avg_amount = (
        await db.execute(
            select(func.count(), func.coalesce(func.avg(Order.total_amount), 0)).where(
                history, Order.status != "cancelled"
            )
        )
    ).one()

    on_time, late, active = (
        await db.execute(
            select(
                func.count().filter(is_paid_on_time()),
                func.count().filter(or_(is_paid_late(), is_overdue(today))),
                func.count().filter(Installment.status.in_(("pending", "overdue"))),
            )
            .join(Order, Installment.order_id == Order.order_id)
            .where(history)
        )
    ).one()

    return RiskFeatures(
        total_orders=total_orders,
        on_time_payments=on_time,
        late_payments=late,
        active_installments=active,
        requested_amount=order.total_amount,
        avg_order_amount=Decimal(avg_amount).quantize(CENT),
    )


def score_with_rules(features: RiskFeatures) -> tuple[int, str]:
    """Deterministic fallback when the LLM is unavailable.

    Base 30 · +25 per late installment · −3 per on-time one (max −15) ·
    +2 per active installment · +15 for an unusually large amount.
    """
    score = 30
    reasons: list[str] = []
    if features.late_payments:
        score += 25 * features.late_payments
        reasons.append(f"{features.late_payments} cuota(s) con atraso")
    if features.on_time_payments:
        score -= min(3 * features.on_time_payments, 15)
        reasons.append(f"{features.on_time_payments} pagada(s) a tiempo")
    if features.active_installments:
        score += 2 * features.active_installments
        reasons.append(f"{features.active_installments} cuota(s) activas")
    if features.total_orders == 0:
        reasons.append("sin historial")
        if features.requested_amount > 500:
            score += 15
            reasons.append("monto alto para una primera compra")
    elif features.requested_amount > 2 * features.avg_order_amount:
        score += 15
        reasons.append("monto mayor al doble de su promedio")

    reasoning = ("Reglas: " + ", ".join(reasons))[:REASONING_MAX_CHARS]
    return max(0, min(100, score)), reasoning


@lru_cache
def get_groq_client() -> AsyncGroq:
    # One client per process: it reuses its HTTP connections between requests
    return AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=LLM_TIMEOUT_SECONDS, max_retries=1)


async def score_with_llm(features: RiskFeatures) -> LLMRiskOutput:
    if not settings.GROQ_API_KEY:
        raise RiskModelUnavailable("GROQ_API_KEY is not set")
    try:
        response = await get_groq_client().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": RISK_PROMPT.format(**features.model_dump())}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=256,
        )
        return LLMRiskOutput.model_validate_json(response.choices[0].message.content or "")
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'json'}: {e['msg']}" for e in exc.errors())
        raise RiskModelUnavailable(f"invalid LLM output ({problems})") from exc
    except APIError as exc:
        raise RiskModelUnavailable(f"{type(exc).__name__}: {exc}") from exc


def risk_level_for(score: int) -> RiskLevel:
    if score < 40:
        return "LOW"
    if score <= 70:
        return "MEDIUM"
    return "HIGH"


async def assess_order_risk(
    db: AsyncSession, order_id: uuid.UUID, today: date | None = None
) -> RiskAssessmentResponse:
    today = today or today_utc()
    order = await db.get(Order, order_id)
    if order is None:
        raise NotFoundError("Order not found")

    features = await build_risk_features(db, order, today)
    # End the read-only transaction before the slow external call, so the pooled
    # connection isn't held idle for seconds while we wait for the LLM.
    await db.commit()

    try:
        llm = await score_with_llm(features)
        score, reasoning, source, llm_model = llm.score, llm.reasoning, "llm", settings.GROQ_MODEL
    except RiskModelUnavailable as exc:
        logger.warning("LLM risk scoring unavailable, using rules: %s", exc)
        score, reasoning = score_with_rules(features)
        source, llm_model = "rules", None

    # The model estimates; business policy decides. Level and recommendation always
    # follow from the score, so the three fields can never contradict each other.
    if features.late_payments:
        score = max(score, LATE_PAYMENT_SCORE_FLOOR)
    risk_level = risk_level_for(score)

    return RiskAssessmentResponse(
        order_id=order.order_id,
        score=score,
        risk_level=risk_level,
        recommendation=RECOMMENDATION_FOR[risk_level],
        reasoning=reasoning,
        source=source,
        llm_model=llm_model,
        features=features,
    )
