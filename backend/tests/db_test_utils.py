"""
Database testing utilities for Domain-Copilot.

Provides helpers to resolve the test database URL and ensure the isolated
test database (domain_copilot_test) exists before test sessions execute.
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

# Load .env from project root if present
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_test_db_url() -> str:
    """
    Returns the isolated test database URL.

    Precedence:
    1. TEST_DATABASE_URL environment variable if set.
    2. If only DATABASE_URL is set (e.g. in CI or dynamic container), derive
       the test URL by targeting 'domain_copilot_test' on the same host/port.
    3. Fall back to local default 'postgresql://postgres:postgres@localhost:5432/domain_copilot_test'.
    """
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        raw = test_url
    elif os.getenv("DATABASE_URL"):
        url = make_url(os.getenv("DATABASE_URL"))
        raw = str(url.set(database="domain_copilot_test"))
    else:
        raw = "postgresql://postgres:postgres@localhost:5432/domain_copilot_test"

    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    return raw


def ensure_test_db_exists(db_url: str) -> None:
    """
    Checks if the target test database exists; if not, connects to an available
    maintenance database on the same host/port to create it automatically.
    """
    url = make_url(db_url)
    target_db = url.database
    if not target_db:
        return

    # 1. Attempt connection to target database
    try:
        conn = psycopg2.connect(
            dbname=target_db,
            user=url.username or "postgres",
            password=url.password or "postgres",
            host=url.host or "localhost",
            port=url.port or 5432,
        )
        conn.close()
        return
    except psycopg2.OperationalError as exc:
        if "does not exist" not in str(exc):
            raise

    # 2. Database does not exist — connect to a maintenance DB and create it
    candidates: list[str] = []
    if os.getenv("DATABASE_URL"):
        try:
            db_name = make_url(os.getenv("DATABASE_URL")).database
            if db_name:
                candidates.append(db_name)
        except Exception:  # noqa: BLE001, S110
            pass
    candidates.extend(["postgres", "domain_copilot", "template1"])

    for maint_db in candidates:
        if not maint_db or maint_db == target_db:
            continue
        try:
            conn = psycopg2.connect(
                dbname=maint_db,
                user=url.username or "postgres",
                password=url.password or "postgres",
                host=url.host or "localhost",
                port=url.port or 5432,
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{target_db}";')
            conn.close()
            return
        except psycopg2.Error:
            continue
