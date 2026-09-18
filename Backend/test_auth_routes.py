"""Unit tests for user registration, login, and authentication routes."""

import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from Backend.B1 import app
from Backend.database import Base, get_database_session
from Backend.models import User, Subscription


class AuthRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.TestingSessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_database_session] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_register_success(self):
        response = self.client.post(
            "/auth/register",
            json={
                "first_name": "Kasun",
                "last_name": "Perera",
                "email": "kasun@example.com",
                "password": "strongPassword123!",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["email"], "kasun@example.com")
        self.assertEqual(data["user"]["first_name"], "Kasun")
        self.assertEqual(data["user"]["last_name"], "Perera")

        # Verify free subscription was created
        db = self.TestingSessionLocal()
        user = db.query(User).filter(User.email == "kasun@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, "Kasun")
        self.assertEqual(user.last_name, "Perera")
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.plan_code, "free")
        db.close()

    def test_register_duplicate_email_fails(self):
        self.client.post(
            "/auth/register",
            json={
                "first_name": "Kasun",
                "last_name": "Perera",
                "email": "kasun@example.com",
                "password": "strongPassword123!",
            },
        )
        dup_resp = self.client.post(
            "/auth/register",
            json={
                "first_name": "Another",
                "last_name": "Person",
                "email": "kasun@example.com",
                "password": "anotherPassword456!",
            },
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertIn("already registered", dup_resp.json()["detail"])

    def test_login_success(self):
        self.client.post(
            "/auth/register",
            json={
                "first_name": "Nimal",
                "last_name": "Silva",
                "email": "nimal@example.com",
                "password": "mySecurePassword1!",
            },
        )
        login_resp = self.client.post(
            "/auth/login",
            json={
                "email": "nimal@example.com",
                "password": "mySecurePassword1!",
            },
        )
        self.assertEqual(login_resp.status_code, 200)
        data = login_resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["first_name"], "Nimal")
        self.assertEqual(data["user"]["last_name"], "Silva")

    def test_login_invalid_password(self):
        self.client.post(
            "/auth/register",
            json={
                "first_name": "Nimal",
                "last_name": "Silva",
                "email": "nimal@example.com",
                "password": "mySecurePassword1!",
            },
        )
        login_resp = self.client.post(
            "/auth/login",
            json={
                "email": "nimal@example.com",
                "password": "wrongPassword",
            },
        )
        self.assertEqual(login_resp.status_code, 401)

    def test_get_me_authenticated(self):
        reg_resp = self.client.post(
            "/auth/register",
            json={
                "first_name": "Kamal",
                "last_name": "Fernando",
                "email": "kamal@example.com",
                "password": "secureKamalPassword!",
            },
        )
        token = reg_resp.json()["access_token"]
        me_resp = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertEqual(me_data["email"], "kamal@example.com")
        self.assertEqual(me_data["first_name"], "Kamal")
        self.assertEqual(me_data["last_name"], "Fernando")

    def test_google_login_success(self):
        from unittest.mock import patch
        mock_claims = {
            "sub": "google-user-123456",
            "email": "adipthathisayuru0529@gmail.com",
            "given_name": "Adiptha",
            "family_name": "Thisayuru",
            "name": "Adiptha Thisayuru",
        }
        with patch("Backend.auth_routes._verify_google_id_token", return_value=mock_claims):
            response = self.client.post(
                "/auth/google",
                json={"credential": "mock_google_id_token_xyz"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("access_token", data)
            self.assertEqual(data["user"]["email"], "adipthathisayuru0529@gmail.com")
            self.assertEqual(data["user"]["first_name"], "Adiptha")
            self.assertEqual(data["user"]["last_name"], "Thisayuru")


if __name__ == "__main__":
    unittest.main()
