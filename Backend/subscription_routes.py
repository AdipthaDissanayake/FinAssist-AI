"""Subscription API routes for the FinAssist academic-project simulation.

Authentication is deliberately not implemented here.  The user-ID dependency
is the integration point for Taniya's verified authentication identity.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_database_session
from .models import AnalysisUsageEvent, Plan, Subscription
from .subscription_service import (
    MonthlyAnalysisLimitReachedError,
    PlanNotAvailableError,
    SubscriptionServiceError,
    get_active_subscription,
    get_current_period_usage,
    get_remaining_monthly_analyses,
    simulate_plan_change,
)


router = APIRouter(prefix="/api/subscription", tags=["subscription"])


class SimulatePlanChangeRequest(BaseModel):
    """An academic-project plan-change simulation request."""

    plan_code: Literal["free", "basic", "premium"]


def get_verified_user_id() -> str:
    """Placeholder for Taniya's future verified-authentication dependency.

    It intentionally fails closed.  Local tests may override this FastAPI
    dependency with an existing, isolated development user ID; no value from a
    browser request is accepted as an identity.
    """

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Subscription access requires the authentication integration to provide a verified user identity.",
    )


@router.get("")
def get_subscription(
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Return the verified user's current plan and allowance."""

    subscription = _require_active_subscription(database, user_id)
    plan = _get_plan(database, subscription.plan_code)
    used = _service_call(lambda: get_current_period_usage(database, user_id), database)
    remaining = _service_call(lambda: get_remaining_monthly_analyses(database, user_id), database)
    return _subscription_payload(subscription, plan, used, remaining)


@router.get("/usage")
def get_subscription_usage(
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Return current-period allowance and its associated usage events."""

    subscription = _require_active_subscription(database, user_id)
    plan = _get_plan(database, subscription.plan_code)
    used = _service_call(lambda: get_current_period_usage(database, user_id), database)
    remaining = _service_call(lambda: get_remaining_monthly_analyses(database, user_id), database)
    events = database.scalars(
        select(AnalysisUsageEvent)
        .where(
            AnalysisUsageEvent.user_id == user_id,
            AnalysisUsageEvent.subscription_id == subscription.id,
            AnalysisUsageEvent.period_start == subscription.current_period_start,
        )
        .order_by(AnalysisUsageEvent.created_at)
    ).all()
    return {
        "plan": plan.code,
        "monthly_analysis_limit": plan.monthly_analysis_limit,
        "used": used,
        "remaining": remaining,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat(),
        "usage_events": [_usage_event_payload(event) for event in events],
    }


@router.post("/simulate-change")
def simulate_subscription_change(
    request: SimulatePlanChangeRequest,
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Simulate a subscription plan change; this endpoint never processes payment."""

    subscription = _service_call(
        lambda: simulate_plan_change(database, user_id, request.plan_code),
        database,
    )
    database.commit()
    database.refresh(subscription)
    plan = _get_plan(database, subscription.plan_code)
    used = _service_call(lambda: get_current_period_usage(database, user_id), database)
    remaining = _service_call(lambda: get_remaining_monthly_analyses(database, user_id), database)
    return {
        "message": "Simulated subscription change recorded for this academic project; no payment was processed.",
        "scheduled_plan_code": subscription.scheduled_plan_code,
        "subscription": _subscription_payload(subscription, plan, used, remaining),
    }


def _require_active_subscription(database: Session, user_id: str) -> Subscription:
    """Return the active subscription or report that the account is unprovisioned."""

    subscription = get_active_subscription(database, user_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription was found for this user.",
        )
    return subscription


def _get_plan(database: Session, plan_code: str) -> Plan:
    plan = database.get(Plan, plan_code)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The current subscription plan is unavailable.",
        )
    return plan


def _subscription_payload(subscription: Subscription, plan: Plan, used: int, remaining: int) -> dict[str, Any]:
    return {
        "current_plan": plan.code,
        "plan_name": plan.name,
        "price_lkr": float(plan.price_lkr),
        "monthly_analysis_limit": plan.monthly_analysis_limit,
        "subscription_status": subscription.status,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat(),
        "used": used,
        "remaining": remaining,
    }


def _usage_event_payload(event: AnalysisUsageEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "message_id": event.message_id,
        "status": event.status,
        "period_start": event.period_start.isoformat(),
        "created_at": event.created_at.isoformat(),
    }


def _service_call(operation: Any, database: Session) -> Any:
    """Map safe service errors to HTTP responses without exposing internals."""

    try:
        return operation()
    except MonthlyAnalysisLimitReachedError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The monthly analysis limit has been reached.",
        ) from exc
    except PlanNotAvailableError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscription plans are temporarily unavailable.",
        ) from exc
    except SubscriptionServiceError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The subscription request could not be completed.",
        ) from exc
