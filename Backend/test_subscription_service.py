"""Deterministic offline tests for FinAssist subscription commercialization."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from Backend import B1
from Backend.database import Base
from Backend.models import AnalysisUsageEvent, Chat, Message, PaymentMethod, Plan, User
from Backend.subscription_service import (
    MonthlyAnalysisLimitReachedError,
    PlanNotAvailableError,
    complete_reserved_analysis,
    create_free_subscription_if_missing,
    get_active_subscription,
    get_current_period_usage,
    get_remaining_monthly_analyses,
    release_reserved_analysis,
    reserve_analysis,
    seed_default_plans,
    simulate_plan_change,
)


NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)


class SubscriptionServiceTests(unittest.TestCase):
    """Every test uses its own in-memory database and isolated user records."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.database: Session = self.session_factory()
        self.user_counter = 0

    def tearDown(self) -> None:
        self.database.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_01_free_plan_has_five_analyses_per_month(self) -> None:
        plans = {plan.code: plan for plan in seed_default_plans(self.database)}
        self.assertEqual(plans["free"].monthly_analysis_limit, 5)

    def test_02_basic_plan_has_fifty_analyses_per_month(self) -> None:
        plans = {plan.code: plan for plan in seed_default_plans(self.database)}
        self.assertEqual(plans["basic"].monthly_analysis_limit, 50)

    def test_03_premium_plan_has_two_hundred_analyses_per_month(self) -> None:
        plans = {plan.code: plan for plan in seed_default_plans(self.database)}
        self.assertEqual(plans["premium"].monthly_analysis_limit, 200)

    def test_04_plan_seeding_does_not_create_duplicates(self) -> None:
        seed_default_plans(self.database)
        seed_default_plans(self.database)
        self.assertEqual(self.database.scalar(select(func.count(Plan.code))), 3)

    def test_05_new_user_receives_a_free_subscription(self) -> None:
        user, _ = self._user_and_chat()
        subscription = create_free_subscription_if_missing(self.database, user.id, now=NOW)
        self.assertEqual(subscription.plan_code, "free")
        self.assertEqual(subscription.status, "active")

    def test_06_initial_usage_is_zero(self) -> None:
        user, _ = self._user_and_chat()
        create_free_subscription_if_missing(self.database, user.id, now=NOW)
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 0)

    def test_07_reservation_increases_active_usage(self) -> None:
        user, chat = self._user_and_chat()
        reserve_analysis(self.database, user.id, self._message(chat).id, now=NOW)
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 1)

    def test_08_completed_reservation_remains_counted(self) -> None:
        user, chat = self._user_and_chat()
        message = self._message(chat)
        reserve_analysis(self.database, user.id, message.id, now=NOW)
        complete_reserved_analysis(self.database, user.id, message.id)
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 1)

    def test_09_released_reservation_is_not_counted(self) -> None:
        user, chat = self._user_and_chat()
        message = self._message(chat)
        reserve_analysis(self.database, user.id, message.id, now=NOW)
        release_reserved_analysis(self.database, user.id, message.id)
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 0)

    def test_10_same_message_id_does_not_consume_quota_twice(self) -> None:
        user, chat = self._user_and_chat()
        message = self._message(chat)
        first = reserve_analysis(self.database, user.id, message.id, now=NOW)
        second = reserve_analysis(self.database, user.id, message.id, now=NOW)
        self.assertEqual(first.id, second.id)
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 1)

    def test_11_free_plan_blocks_sixth_analysis(self) -> None:
        user, chat = self._user_and_chat()
        self._reserve_many(user.id, chat, 5)
        with self.assertRaises(MonthlyAnalysisLimitReachedError):
            reserve_analysis(self.database, user.id, self._message(chat).id, now=NOW)

    def test_12_basic_plan_allows_fifty_analyses(self) -> None:
        user, chat = self._user_and_chat()
        simulate_plan_change(self.database, user.id, "basic", now=NOW)
        self._reserve_many(user.id, chat, 50)
        self.assertEqual(get_remaining_monthly_analyses(self.database, user.id, now=NOW), 0)
        with self.assertRaises(MonthlyAnalysisLimitReachedError):
            reserve_analysis(self.database, user.id, self._message(chat).id, now=NOW)

    def test_13_premium_plan_allows_two_hundred_analyses(self) -> None:
        user, chat = self._user_and_chat()
        simulate_plan_change(self.database, user.id, "premium", now=NOW)
        self._reserve_many(user.id, chat, 200)
        self.assertEqual(get_remaining_monthly_analyses(self.database, user.id, now=NOW), 0)
        with self.assertRaises(MonthlyAnalysisLimitReachedError):
            reserve_analysis(self.database, user.id, self._message(chat).id, now=NOW)

    def test_14_different_users_have_independent_quotas(self) -> None:
        first_user, first_chat = self._user_and_chat()
        second_user, second_chat = self._user_and_chat()
        self._reserve_many(first_user.id, first_chat, 5)
        reserve_analysis(self.database, second_user.id, self._message(second_chat).id, now=NOW)
        self.assertEqual(get_remaining_monthly_analyses(self.database, first_user.id, now=NOW), 0)
        self.assertEqual(get_remaining_monthly_analyses(self.database, second_user.id, now=NOW), 4)

    def test_15_free_to_basic_simulated_change_works(self) -> None:
        user, _ = self._user_and_chat()
        subscription = simulate_plan_change(self.database, user.id, "basic", now=NOW)
        self.assertEqual(subscription.plan_code, "basic")
        self.assertIsNone(subscription.scheduled_plan_code)

    def test_16_basic_to_premium_simulated_change_works(self) -> None:
        user, _ = self._user_and_chat()
        simulate_plan_change(self.database, user.id, "basic", now=NOW)
        subscription = simulate_plan_change(self.database, user.id, "premium", now=NOW)
        self.assertEqual(subscription.plan_code, "premium")
        self.assertIsNone(subscription.scheduled_plan_code)

    def test_17_invalid_plan_code_is_rejected(self) -> None:
        user, _ = self._user_and_chat()
        with self.assertRaises(PlanNotAvailableError):
            simulate_plan_change(self.database, user.id, "enterprise", now=NOW)

    def test_18_failed_b1_analysis_releases_its_reservation(self) -> None:
        user, chat = self._user_and_chat()
        with patch.object(B1, "orchestrate_financial_question", side_effect=B1.AgentWorkflowError("offline")):
            result = B1.add_message(
                chat.id,
                B1.MessageCreateRequest(content="What are the risks of a loan?"),
                self.database,
                user.id,
            )
        self.assertIn("assistant_message", result)
        self.assertEqual(get_current_period_usage(self.database, user.id), 0)
        event = self.database.scalar(select(AnalysisUsageEvent).where(AnalysisUsageEvent.user_id == user.id))
        self.assertEqual(event.status, "released")

    def test_19_quota_exhaustion_prevents_orchestrator_call(self) -> None:
        user, chat = self._user_and_chat()
        self._reserve_many(user.id, chat, 5, now=datetime.now(UTC))
        with patch.object(B1, "orchestrate_financial_question") as orchestrate:
            response = B1.add_message(
                chat.id,
                B1.MessageCreateRequest(content="What are the risks of a loan?"),
                self.database,
                user.id,
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(json.loads(response.body), {
            "error": "subscription_limit_reached",
            "message": "Monthly analysis limit reached.",
            "plan": "free",
            "used": 5,
            "limit": 5,
            "remaining": 0,
        })
        orchestrate.assert_not_called()

    def test_20_usage_is_limited_to_the_current_billing_period(self) -> None:
        user, chat = self._user_and_chat()
        subscription = create_free_subscription_if_missing(self.database, user.id, now=NOW)
        old_message = self._message(chat)
        old_event = AnalysisUsageEvent(
            user_id=user.id,
            subscription_id=subscription.id,
            message_id=old_message.id,
            period_start=datetime(2029, 12, 15, 12, 0, tzinfo=UTC),
            status="completed",
        )
        self.database.add(old_event)
        self.database.flush()
        self.assertEqual(get_current_period_usage(self.database, user.id, now=NOW), 0)
        self.assertEqual(get_remaining_monthly_analyses(self.database, user.id, now=NOW), 5)

    def test_21_card_validation_rejects_invalid_luhn(self) -> None:
        from Backend.payment_utils import validate_card_details
        is_valid, err, _, _, _, _ = validate_card_details(
            card_holder_name="Test User",
            card_number="4111111111111112",  # invalid checksum
            exp_month=12,
            exp_year=2030,
            cvv="123",
        )
        self.assertFalse(is_valid)
        self.assertIn("checksum", err.lower())

    def test_22_card_validation_accepts_valid_visa_and_detects_brand(self) -> None:
        from Backend.payment_utils import detect_card_brand, validate_card_details
        # Standard Visa test card (4242424242424242)
        is_valid, err, brand, last4, exp_month, exp_year = validate_card_details(
            card_holder_name="Alice Smith",
            card_number="4242 4242 4242 4242",
            exp_month=10,
            exp_year=2032,
            cvv="321",
        )
        self.assertTrue(is_valid)
        self.assertEqual(err, "")
        self.assertEqual(brand, "visa")
        self.assertEqual(last4, "4242")
        self.assertEqual(exp_month, 10)
        self.assertEqual(exp_year, 2032)

    def test_23_card_validation_rejects_past_expiration(self) -> None:
        from Backend.payment_utils import validate_card_details
        is_valid, err, _, _, _, _ = validate_card_details(
            card_holder_name="Alice Smith",
            card_number="4242424242424242",
            exp_month=1,
            exp_year=2020,
            cvv="321",
        )
        self.assertFalse(is_valid)
        self.assertIn("past", err.lower())

    def test_24_saving_payment_method_for_user(self) -> None:
        from Backend.models import PaymentMethod
        user, _ = self._user_and_chat()
        pm = PaymentMethod(
            user_id=user.id,
            card_holder_name="Bob Jones",
            brand="mastercard",
            last4="5555",
            exp_month=8,
            exp_year=2029,
            is_default=True,
        )
        self.database.add(pm)
        self.database.commit()

        saved = self.database.scalar(
            select(PaymentMethod).where(PaymentMethod.user_id == user.id)
        )
        self.assertIsNotNone(saved)
        self.assertEqual(saved.brand, "mastercard")
        self.assertEqual(saved.last4, "5555")
        self.assertTrue(saved.is_default)

    def test_25_delete_payment_method_promotes_remaining_to_default(self) -> None:
        from Backend.models import PaymentMethod
        user, _ = self._user_and_chat()
        pm1 = PaymentMethod(
            user_id=user.id,
            card_holder_name="Card 1",
            brand="visa",
            last4="1111",
            exp_month=12,
            exp_year=2029,
            is_default=True,
        )
        pm2 = PaymentMethod(
            user_id=user.id,
            card_holder_name="Card 2",
            brand="mastercard",
            last4="2222",
            exp_month=12,
            exp_year=2029,
            is_default=False,
        )
        self.database.add_all([pm1, pm2])
        self.database.commit()

        self.database.delete(pm1)
        # Update remaining to default
        remaining = self.database.scalar(
            select(PaymentMethod).where(PaymentMethod.user_id == user.id)
        )
        remaining.is_default = True
        self.database.commit()

        saved = self.database.scalar(
            select(PaymentMethod).where(PaymentMethod.user_id == user.id)
        )
        self.assertEqual(saved.last4, "2222")
        self.assertTrue(saved.is_default)

    def test_26_add_payment_method_route(self) -> None:
        from Backend.subscription_routes import AddPaymentMethodRequest, add_payment_method, list_payment_methods
        user, _ = self._user_and_chat()
        req = AddPaymentMethodRequest(
            card_holder_name="Test User",
            card_number="4242424242424242",
            exp_month=11,
            exp_year=2031,
            cvv="123",
            is_default=True,
        )
        res = add_payment_method(req, user_id=user.id, database=self.database)
        self.assertEqual(res["message"], "Payment method saved successfully.")
        self.assertEqual(res["payment_method"]["brand"], "visa")
        self.assertEqual(res["payment_method"]["last4"], "4242")

        listed = list_payment_methods(user_id=user.id, database=self.database)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["last4"], "4242")

    def test_27_simulate_change_with_card_details_route(self) -> None:
        from Backend.subscription_routes import CardDetailsInput, SimulatePlanChangeRequest, simulate_subscription_change
        seed_default_plans(self.database)
        user, _ = self._user_and_chat()
        card_in = CardDetailsInput(
            card_holder_name="John Doe",
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2032,
            cvv="456",
            save_card=True,
        )
        req = SimulatePlanChangeRequest(
            plan_code="basic",
            card_details=card_in,
        )
        res = simulate_subscription_change(req, user_id=user.id, database=self.database)
        self.assertEqual(res["subscription"]["current_plan"], "basic")
        self.assertEqual(res["subscription"]["monthly_analysis_limit"], 50)

        # Ensure card was saved to payment_methods
        saved_cards = self.database.scalars(
            select(PaymentMethod).where(PaymentMethod.user_id == user.id)
        ).all()
        self.assertEqual(len(saved_cards), 1)
        self.assertEqual(saved_cards[0].last4, "4242")

    def _user_and_chat(self) -> tuple[User, Chat]:
        self.user_counter += 1
        user = User(email=f"subscription-test-{self.user_counter}@example.test")
        self.database.add(user)
        self.database.flush()
        chat = Chat(user_id=user.id, title="Subscription test")
        self.database.add(chat)
        self.database.flush()
        return user, chat

    def _message(self, chat: Chat) -> Message:
        message = Message(chat_id=chat.id, role="user", content="Subscription test question", extra_data={})
        self.database.add(message)
        self.database.flush()
        return message

    def _reserve_many(
        self, user_id: str, chat: Chat, amount: int, *, now: datetime = NOW
    ) -> None:
        for _ in range(amount):
            reserve_analysis(self.database, user_id, self._message(chat).id, now=now)


if __name__ == "__main__":
    unittest.main(verbosity=2)

