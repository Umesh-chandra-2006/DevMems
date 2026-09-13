"""
Key Pool & Usage Tracking: Manages multi-key rotation pools per provider,
enforcing pre-emptive daily rate limits and tracking request quotas using SQLite.
"""

from datetime import date
import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "usage_log.db")


def get_today_str() -> str:
    """Return today's date formatted as YYYY-MM-DD."""
    return date.today().isoformat()


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Get a SQLite connection and ensure schema tables exist."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS key_usage (
                provider          TEXT NOT NULL,
                key_id            TEXT NOT NULL,
                date              DATE NOT NULL,
                requests_used     INTEGER DEFAULT 0,
                PRIMARY KEY (provider, key_id, date)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_call_log (
                call_id          TEXT PRIMARY KEY,
                provider         TEXT NOT NULL,
                model            TEXT NOT NULL,
                purpose          TEXT NOT NULL,
                tokens_in        INTEGER,
                tokens_out       INTEGER,
                sim_day          INTEGER,
                agent_id         TEXT,
                condition        TEXT,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    return conn


def get_usage(provider: str, key_id: str, date_str: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> int:
    """Get number of requests used today for a specific (provider, key_id)."""
    if date_str is None:
        date_str = get_today_str()

    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT requests_used FROM key_usage WHERE provider = ? AND key_id = ? AND date = ?",
            (provider, key_id, date_str)
        )
        row = cursor.fetchone()
        return row["requests_used"] if row else 0
    finally:
        conn.close()


def increment_usage(provider: str, key_id: str, date_str: Optional[str] = None, count: int = 1, db_path: str = DEFAULT_DB_PATH) -> int:
    """Increment requests_used count for a given (provider, key_id) pair."""
    if date_str is None:
        date_str = get_today_str()

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO key_usage (provider, key_id, date, requests_used)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, key_id, date)
                DO UPDATE SET requests_used = requests_used + excluded.requests_used
            """, (provider, key_id, date_str, count))

        return get_usage(provider, key_id, date_str, db_path=db_path)
    finally:
        conn.close()


def mark_key_exhausted(provider: str, key_id: str, date_str: Optional[str] = None, exhausted_val: int = 9999999, db_path: str = DEFAULT_DB_PATH):
    """Mark a key as exhausted for the day upon encountering a rate limit (HTTP 429)."""
    if date_str is None:
        date_str = get_today_str()

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO key_usage (provider, key_id, date, requests_used)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, key_id, date)
                DO UPDATE SET requests_used = MAX(requests_used, excluded.requests_used)
            """, (provider, key_id, date_str, exhausted_val))
    finally:
        conn.close()


def is_key_available(provider: str, key_id: str, limit: int, date_str: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Check if the given key has remaining quota for today."""
    current_usage = get_usage(provider, key_id, date_str, db_path=db_path)
    return current_usage < limit


def reset_usage_for_test(provider: str, key_id: str, date_str: Optional[str] = None, db_path: str = DEFAULT_DB_PATH):
    """Utility function to clear key usage during tests."""
    if date_str is None:
        date_str = get_today_str()

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                "DELETE FROM key_usage WHERE provider = ? AND key_id = ? AND date = ?",
                (provider, key_id, date_str)
            )
    finally:
        conn.close()
