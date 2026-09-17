"""Database configuration shared by the FinAssist backend.

The preferred configuration file is `<project-root>/.env`. During this team's
early development, `IR_NLP_Agent/.env` is also supported as a fallback so the
existing Tavily key continues to work. Do not commit either file.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "IR_NLP_Agent" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Add it to .env at the project root, for example: "
        "mysql+pymysql://finassist_app:password@localhost:3306/finassist_ai"
    )

engine_options: dict[str, object] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    # A shared connection keeps the optional in-memory test database available
    # to FastAPI's startup task and request threads.
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all persistent FinAssist records."""


def initialise_database() -> None:
    """Create the required tables in the configured database when absent."""
    # Imported lazily so all models are registered before create_all executes.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_google_identity_column()


def _add_google_identity_column() -> None:
    """Apply the small backwards-compatible migration for existing databases."""
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    indexes = {index["name"] for index in inspector.get_indexes("users")}

    # This project currently manages its schema with create_all rather than a
    # migration framework. Keep existing email/password rows intact while
    # adding the optional Google provider identity.
    with engine.begin() as connection:
        if "google_sub" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255) NULL"))
        if "ix_users_google_sub" not in indexes:
            connection.execute(text("CREATE UNIQUE INDEX ix_users_google_sub ON users (google_sub)"))


def get_database_session() -> Generator[Session, None, None]:
    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()
