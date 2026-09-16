"""Subscription plan and monthly analysis-usage helpers.

Authentication is intentionally outside this module.  Callers must provide a
verified ``user_id`` and manage the surrounding database transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AnalysisUsageEvent, Plan, Subscription


DEFAULT_PLANS = (
    {"code": "free", "name": "Free", "price_lkr": Decimal("0.00"), "monthly_analysis_limit": 5},
    {"code": "basic", "name": "Basic", "price_lkr": Decimal("499.00"), "monthly_analysis_limit": 50},
    {"code": "premium", "name": "Premium", "price_lkr": Decimal("999.00"), "monthly_analysis_limit": 200},
)
COUNTED_USAGE_STATUSES = ("reserved", "completed")


class SubscriptionServiceError(RuntimeError):
    """Base error for subscription service operations."""


class PlanNotAvailableError(SubscriptionServiceError):
    """Raised when a requested plan does not exist or is inactive."""


class MonthlyAnalysisLimitReachedError(SubscriptionServiceError):
    """Raised when a user has no remaining analyses in the current period."""


def seed_default_plans(database: Session) -> list[Plan]:
    """Insert the three standard plans when they are absent without overwriting existing rows."""

    plans: list[Plan] = []
    for definition in DEFAULT_PLANS:
        plan = database.get(Plan, definition["code"])
        if plan is None:
            plan = Plan(active=True, **definition)
            database.add(plan)
        plans.append(plan)
    database.flush()
    return plans


def get_active_subscription(
    database: Session, user_id: str, *, now: datetime | None = None
) -> Subscription | None:
    """Return the user's current active subscription, if one exists."""

    current_time = _normalise_now(now)
    return database.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == _required_identifier(user_id, "user_id"),
            Subscription.status == "active",
            Subscription.current_period_start <= current_time,
            Subscription.current_period_end > current_time,
        )
        .order_by(Subscription.current_period_start.desc())
    )


def create_free_subscription_if_missing(
    database: Session, user_id: str, *, now: datetime | None = None
) -> Subscription:
    """Return an active subscription, creating a Free period when none exists."""

    current_time = _normalise_now(now)
    verified_user_id = _required_identifier(user_id, "user_id")
    subscription = get_active_subscription(database, verified_user_id, now=current_time)
    if subscription is not None:
        return subscription

    seed_default_plans(database)
    free_plan = database.get(Plan, "free")
    if free_plan is None or not free_plan.active:
        raise PlanNotAvailableError("The Free plan is not available.")

    subscription = Subscription(
        user_id=verified_user_id,
        plan_code=free_plan.code,
        status="active",
        current_period_start=current_time,
        current_period_end=_one_month_after(current_time),
    )
    database.add(subscription)
    database.flush()
    return subscription


def get_current_period_usage(database: Session, user_id: str, *, now: datetime | None = None) -> int:
    """Count a user's reserved and completed events in the current period."""

    subscription = create_free_subscription_if_missing(database, user_id, now=now)
    return _get_subscription_period_usage(database, subscription)


def _get_subscription_period_usage(database: Session, subscription: Subscription) -> int:
    """Count reserved and completed events for a known subscription period."""

    usage_count = database.scalar(
        select(func.count(AnalysisUsageEvent.id)).where(
            AnalysisUsageEvent.user_id == subscription.user_id,
            AnalysisUsageEvent.subscription_id == subscription.id,
            AnalysisUsageEvent.period_start == subscription.current_period_start,
            AnalysisUsageEvent.status.in_(COUNTED_USAGE_STATUSES),
        )
    )
    return int(usage_count or 0)


def get_remaining_monthly_analyses(
    database: Session, user_id: str, *, now: datetime | None = None
) -> int:
    """Return the active plan's remaining analysis allowance for the user."""

    subscription = create_free_subscription_if_missing(database, user_id, now=now)
    plan = _require_active_plan(database, subscription.plan_code)
    return max(plan.monthly_analysis_limit - _get_subscription_period_usage(database, subscription), 0)


def can_perform_analysis(database: Session, user_id: str, *, now: datetime | None = None) -> bool:
    """Return whether the user has at least one analysis remaining this period."""

    return get_remaining_monthly_analyses(database, user_id, now=now) > 0


def reserve_analysis(
    database: Session, user_id: str, message_id: str, *, now: datetime | None = None
) -> AnalysisUsageEvent:
    """Reserve one analysis without charging the same message twice.

    Existing reserved or completed events are returned unchanged.  A released
    event may be reserved again because it does not count against the quota.
    """

    verified_user_id = _required_identifier(user_id, "user_id")
    verified_message_id = _required_identifier(message_id, "message_id")
    current_time = _normalise_now(now)
    existing_event = database.scalar(
        select(AnalysisUsageEvent).where(AnalysisUsageEvent.message_id == verified_message_id)
    )
    if existing_event is not None:
        if existing_event.user_id != verified_user_id:
            raise SubscriptionServiceError("The message is already associated with another user.")
        if existing_event.status in COUNTED_USAGE_STATUSES:
            return existing_event

    subscription = create_free_subscription_if_missing(database, verified_user_id, now=current_time)
    if get_remaining_monthly_analyses(database, verified_user_id, now=current_time) <= 0:
        raise MonthlyAnalysisLimitReachedError("The monthly analysis limit has been reached.")

    if existing_event is None:
        event = AnalysisUsageEvent(
            user_id=verified_user_id,
            subscription_id=subscription.id,
            message_id=verified_message_id,
            period_start=subscription.current_period_start,
            status="reserved",
        )
        database.add(event)
    else:
        event = existing_event
        event.subscription_id = subscription.id
        event.period_start = subscription.current_period_start
        event.status = "reserved"
    database.flush()
    return event


def complete_reserved_analysis(database: Session, user_id: str, message_id: str) -> AnalysisUsageEvent:
    """Mark a reserved event completed after the agent workflow succeeds."""

    event = _require_usage_event(database, user_id, message_id)
    if event.status == "reserved":
        event.status = "completed"
        database.flush()
    return event


def release_reserved_analysis(database: Session, user_id: str, message_id: str) -> AnalysisUsageEvent:
    """Release a reserved event when the agent workflow fails."""

    event = _require_usage_event(database, user_id, message_id)
    if event.status == "reserved":
        event.status = "released"
        database.flush()
    return event


def simulate_plan_change(
    database: Session, user_id: str, plan_code: str, *, now: datetime | None = None
) -> Subscription:
    """Simulate an upgrade now or schedule a lower-priced plan for renewal."""

    subscription = create_free_subscription_if_missing(database, user_id, now=now)
    current_plan = _require_active_plan(database, subscription.plan_code)
    target_plan = _require_active_plan(database, _required_identifier(plan_code, "plan_code"))

    if target_plan.code == current_plan.code:
        subscription.scheduled_plan_code = None
    elif target_plan.price_lkr < current_plan.price_lkr:
        subscription.scheduled_plan_code = target_plan.code
    else:
        subscription.plan_code = target_plan.code
        subscription.scheduled_plan_code = None
    database.flush()
    return subscription


def _require_active_plan(database: Session, plan_code: str) -> Plan:
    plan = database.get(Plan, plan_code)
    if plan is None or not plan.active:
        raise PlanNotAvailableError("The requested plan is not available.")
    return plan


def _require_usage_event(database: Session, user_id: str, message_id: str) -> AnalysisUsageEvent:
    event = database.scalar(
        select(AnalysisUsageEvent).where(
            AnalysisUsageEvent.user_id == _required_identifier(user_id, "user_id"),
            AnalysisUsageEvent.message_id == _required_identifier(message_id, "message_id"),
        )
    )
    if event is None:
        raise SubscriptionServiceError("No matching analysis usage event was found.")
    return event


def _required_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


def _normalise_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _one_month_after(value: datetime) -> datetime:
    """Return the same UTC clock time in the following calendar month."""

    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    days_in_target_month = _days_in_month(year, month)
    return value.replace(year=year, month=month, day=min(value.day, days_in_target_month))


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in {4, 6, 9, 11} else 31
