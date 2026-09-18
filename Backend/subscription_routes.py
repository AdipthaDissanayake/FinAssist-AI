"""Subscription API routes for the FinAssist academic-project simulation.

Authentication is deliberately not implemented here.  The user-ID dependency
is the integration point for Taniya's verified authentication identity.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_database_session
from .models import AnalysisUsageEvent, PaymentMethod, Plan, Subscription, User
from .payment_utils import validate_card_details
from .subscription_service import (
    MonthlyAnalysisLimitReachedError,
    PlanNotAvailableError,
    SubscriptionServiceError,
    create_free_subscription_if_missing,
    get_active_subscription,
    get_current_period_usage,
    get_remaining_monthly_analyses,
    seed_default_plans,
    simulate_plan_change,
)

from .auth import get_current_user


router = APIRouter(prefix="/api/subscription", tags=["subscription"])


class CardDetailsInput(BaseModel):
    """Card inputs for immediate payment and optional vaulting."""

    card_holder_name: str
    card_number: str
    exp_month: int
    exp_year: int
    cvv: str
    save_card: bool = True


class AddPaymentMethodRequest(BaseModel):
    """Request schema for saving a new payment method."""

    card_holder_name: str
    card_number: str
    exp_month: int
    exp_year: int
    cvv: str
    is_default: bool = True


class SimulatePlanChangeRequest(BaseModel):
    """An academic-project plan-change simulation request."""

    plan_code: Literal["free", "basic", "premium"]
    payment_method_id: str | None = None
    card_details: CardDetailsInput | None = None


DEV_USER_EMAIL = "dev@finassist.local"


def get_verified_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Resolve the verified user identity from the incoming JWT token."""
    return current_user.id


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


@router.get("/payment-methods")
def list_payment_methods(
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> list[dict[str, Any]]:
    """Return all saved payment cards for the verified user."""
    methods = database.scalars(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == user_id)
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    ).all()
    return [_payment_method_payload(m) for m in methods]


@router.post("/payment-methods")
def add_payment_method(
    request: AddPaymentMethodRequest,
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Validate and store a new payment method (masked card details only)."""
    is_valid, error_msg, brand, last4, exp_month, exp_year = validate_card_details(
        card_holder_name=request.card_holder_name,
        card_number=request.card_number,
        exp_month=request.exp_month,
        exp_year=request.exp_year,
        cvv=request.cvv,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_msg,
        )

    # Check if user already has methods; if this is the first, make it default
    has_existing = database.scalar(
        select(func.count(PaymentMethod.id)).where(PaymentMethod.user_id == user_id)
    )
    is_default = request.is_default or (has_existing == 0)

    if is_default:
        existing_defaults = database.scalars(
            select(PaymentMethod).where(
                PaymentMethod.user_id == user_id,
                PaymentMethod.is_default.is_(True),
            )
        ).all()
        for ed in existing_defaults:
            ed.is_default = False

    pm = PaymentMethod(
        user_id=user_id,
        card_holder_name=request.card_holder_name.strip(),
        brand=brand,
        last4=last4,
        exp_month=exp_month,
        exp_year=exp_year,
        is_default=is_default,
    )
    database.add(pm)
    database.commit()
    database.refresh(pm)
    return {
        "message": "Payment method saved successfully.",
        "payment_method": _payment_method_payload(pm),
    }


@router.delete("/payment-methods/{payment_method_id}")
def delete_payment_method(
    payment_method_id: str,
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Remove a saved payment method."""
    pm = database.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == payment_method_id,
            PaymentMethod.user_id == user_id,
        )
    )
    if pm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found.",
        )
    was_default = pm.is_default
    database.delete(pm)
    database.commit()

    if was_default:
        remaining = database.scalar(
            select(PaymentMethod).where(PaymentMethod.user_id == user_id).order_by(PaymentMethod.created_at.desc())
        )
        if remaining:
            remaining.is_default = True
            database.commit()

    return {"message": "Payment method removed successfully."}


@router.post("/simulate-change")
def simulate_subscription_change(
    request: SimulatePlanChangeRequest,
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Simulate a subscription plan change; validates payment choice for paid tiers."""

    target_plan = _get_plan(database, request.plan_code)

    # If selecting a paid plan, require a payment method (saved card, new card, or existing default)
    if target_plan.price_lkr > 0:
        if request.payment_method_id:
            pm = database.scalar(
                select(PaymentMethod).where(
                    PaymentMethod.id == request.payment_method_id,
                    PaymentMethod.user_id == user_id,
                )
            )
            if pm is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected payment method was not found.",
                )
        elif request.card_details:
            cd = request.card_details
            is_valid, error_msg, brand, last4, exp_month, exp_year = validate_card_details(
                card_holder_name=cd.card_holder_name,
                card_number=cd.card_number,
                exp_month=cd.exp_month,
                exp_year=cd.exp_year,
                cvv=cd.cvv,
            )
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_msg,
                )
            if cd.save_card:
                has_existing = database.scalar(
                    select(func.count(PaymentMethod.id)).where(PaymentMethod.user_id == user_id)
                )
                is_default = has_existing == 0
                new_pm = PaymentMethod(
                    user_id=user_id,
                    card_holder_name=cd.card_holder_name.strip(),
                    brand=brand,
                    last4=last4,
                    exp_month=exp_month,
                    exp_year=exp_year,
                    is_default=is_default,
                )
                database.add(new_pm)
                database.flush()
        else:
            # Check if user has an active default saved card
            default_pm = database.scalar(
                select(PaymentMethod).where(
                    PaymentMethod.user_id == user_id,
                    PaymentMethod.is_default.is_(True),
                )
            )
            if default_pm is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A valid payment method is required to subscribe to a paid plan.",
                )

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
        "message": "Simulated subscription change recorded for this academic project; payment verified.",
        "scheduled_plan_code": subscription.scheduled_plan_code,
        "subscription": _subscription_payload(subscription, plan, used, remaining),
    }


@router.get("/plans")
def get_public_plans(database: Session = Depends(get_database_session)) -> list[dict[str, Any]]:
    """Return all active subscription plans and pricing for visitors."""
    plans = seed_default_plans(database)
    return [
        {
            "code": plan.code,
            "name": plan.name,
            "price_lkr": float(plan.price_lkr),
            "monthly_analysis_limit": plan.monthly_analysis_limit,
            "active": plan.active,
        }
        for plan in plans
        if plan.active
    ]


@router.post("/cancel")
def cancel_subscription(
    user_id: str = Depends(get_verified_user_id),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    """Cancel subscription renewal by scheduling a switch to the Free plan."""
    subscription = _service_call(
        lambda: simulate_plan_change(database, user_id, "free"),
        database,
    )
    database.commit()
    database.refresh(subscription)
    plan = _get_plan(database, subscription.plan_code)
    used = _service_call(lambda: get_current_period_usage(database, user_id), database)
    remaining = _service_call(lambda: get_remaining_monthly_analyses(database, user_id), database)
    return {
        "message": "Subscription scheduled to cancel at the end of the current period.",
        "scheduled_plan_code": subscription.scheduled_plan_code,
        "subscription": _subscription_payload(subscription, plan, used, remaining),
    }


def _require_active_subscription(database: Session, user_id: str) -> Subscription:
    """Return the active subscription, provisioning the Free tier if missing."""

    subscription = get_active_subscription(database, user_id)
    if subscription is None:
        subscription = create_free_subscription_if_missing(database, user_id)
        database.commit()
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
        "scheduled_plan_code": subscription.scheduled_plan_code,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat(),
        "used": used,
        "remaining": remaining,
    }


def _payment_method_payload(pm: PaymentMethod) -> dict[str, Any]:
    return {
        "id": pm.id,
        "card_holder_name": pm.card_holder_name,
        "brand": pm.brand,
        "last4": pm.last4,
        "exp_month": pm.exp_month,
        "exp_year": pm.exp_year,
        "is_default": pm.is_default,
        "created_at": pm.created_at.isoformat() if pm.created_at else None,
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