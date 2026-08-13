"""Candidate authentication — table creation, registration, login verification.

Uses the same MySQL config as DatabaseManager (config.settings).
No new database, no new connection class.
"""

import hashlib
import logging
import os
from contextlib import contextmanager
from typing import Generator

import mysql.connector

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS candidate_users (
    id             INT          NOT NULL AUTO_INCREMENT,
    candidate_id   INT          NOT NULL DEFAULT 0,
    name           VARCHAR(255) NOT NULL,
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    account_status VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_schema_ready = False


# ── Connection (same pattern as ats_schema.py) ─────────────────────────────

@contextmanager
def _connect() -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        autocommit=False, charset="utf8mb4",
        collation="utf8mb4_unicode_ci", raise_on_warnings=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema init ────────────────────────────────────────────────────────────

def init_candidate_auth_schema() -> None:
    """Create candidate_users table if it does not exist. Runs once per process."""
    global _schema_ready
    if _schema_ready:
        return
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(_DDL)
        # Migrate: add candidate_id column if missing (table existed before this column was added)
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'candidate_users' AND COLUMN_NAME = 'candidate_id'
        """, (MYSQL_DATABASE,))
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE candidate_users ADD COLUMN candidate_id INT NOT NULL DEFAULT 0 AFTER id")
            cur.execute("""
                UPDATE candidate_users cu
                JOIN candidates c ON c.email = cu.email
                SET cu.candidate_id = c.candidate_id
            """)
            logger.info("Migrated candidate_users: added candidate_id column")
        cur.close()
    _schema_ready = True
    logger.info("candidate_users table ready")


# ── Password hashing (SHA-256 + per-user salt, no extra deps) ──────────────

def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt). Generate salt if not provided."""
    if salt is None:
        salt = os.urandom(16).hex()
    digest = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
    return digest, salt


def _verify_password(password: str, stored_hash: str) -> bool:
    """stored_hash format: '<salt>:<hash>'"""
    try:
        salt, expected = stored_hash.split(":", 1)
    except ValueError:
        return False
    digest, _ = _hash_password(password, salt)
    return digest == expected


def _make_stored_hash(password: str) -> str:
    digest, salt = _hash_password(password)
    return f"{salt}:{digest}"


# ── Public API ─────────────────────────────────────────────────────────────

def register_candidate(email: str, password: str) -> dict:
    """
    Register a candidate account.

    Rules:
    - email must exist in candidates table (recruiter must have uploaded resume first)
    - email must not already exist in candidate_users
    - password must be at least 6 characters

    Returns dict with keys: success (bool), message (str),
    and on success: candidate_id (int), name (str)
    """
    email = email.strip().lower()

    if len(password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters."}

    with _connect() as conn:
        cur = conn.cursor()

        # Check candidate exists in candidates table
        cur.execute(
            "SELECT candidate_id, name FROM candidates WHERE email = %s",
            (email,)
        )
        row = cur.fetchone()
        if not row:
            return {
                "success": False,
                "message": "No profile found for this email. Ask your recruiter to upload your resume first.",
            }
        candidate_id, name = row[0], row[1]

        # Check not already registered
        cur.execute(
            "SELECT id FROM candidate_users WHERE email = %s",
            (email,)
        )
        if cur.fetchone():
            return {"success": False, "message": "An account with this email already exists. Please log in."}

        # Insert
        stored_hash = _make_stored_hash(password)
        cur.execute(
            """
            INSERT INTO candidate_users (candidate_id, name, email, password_hash, account_status)
            VALUES (%s, %s, %s, %s, 'active')
            """,
            (candidate_id, name, email, stored_hash),
        )
        cur.close()

    logger.info("Candidate registered email=%s candidate_id=%s", email, candidate_id)
    return {"success": True, "message": "Account created successfully!", "candidate_id": candidate_id, "name": name}


def verify_login(email: str, password: str) -> dict:
    """
    Verify candidate login credentials.

    Returns dict with keys: success (bool), message (str),
    and on success: candidate_id (int), name (str), email (str)
    """
    email = email.strip().lower()

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT candidate_id, name, password_hash, account_status FROM candidate_users WHERE email = %s",
            (email,)
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        return {"success": False, "message": "Invalid email or password."}

    candidate_id, name, stored_hash, status = row

    if status != "active":
        return {"success": False, "message": "Your account is inactive. Please contact support."}

    if not _verify_password(password, stored_hash):
        return {"success": False, "message": "Invalid email or password."}

    logger.info("Candidate login success email=%s candidate_id=%s", email, candidate_id)
    return {
        "success":      True,
        "message":      f"Welcome back, {name}!",
        "candidate_id": candidate_id,
        "name":         name,
        "email":        email,
    }
