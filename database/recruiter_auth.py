"""Recruiter authentication — table, registration, login verification."""

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
CREATE TABLE IF NOT EXISTS recruiter_users (
    id             INT          NOT NULL AUTO_INCREMENT,
    name           VARCHAR(255) NOT NULL,
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    account_status VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_recruiter_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_schema_ready = False


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


def init_recruiter_auth_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(_DDL)
        cur.close()
    _schema_ready = True
    logger.info("recruiter_users table ready")


def _hash(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16).hex()
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return digest, salt


def _verify(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split(":", 1)
    except ValueError:
        return False
    digest, _ = _hash(password, salt)
    return digest == expected


def _make_hash(password: str) -> str:
    digest, salt = _hash(password)
    return f"{salt}:{digest}"


def register_recruiter(name: str, email: str, password: str) -> dict:
    email = email.strip().lower()
    name  = name.strip()

    if not name:
        return {"success": False, "message": "Name is required."}
    if len(password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters."}

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM recruiter_users WHERE email = %s", (email,))
        if cur.fetchone():
            return {"success": False, "message": "An account with this email already exists."}
        cur.execute(
            "INSERT INTO recruiter_users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, _make_hash(password)),
        )
        cur.close()

    logger.info("Recruiter registered email=%s", email)
    return {"success": True, "message": "Account created! You can now log in.", "name": name}


def verify_recruiter_login(email: str, password: str) -> dict:
    email = email.strip().lower()

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, password_hash, account_status FROM recruiter_users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        return {"success": False, "message": "Invalid email or password."}

    rid, name, stored_hash, status = row
    if status != "active":
        return {"success": False, "message": "Account is inactive. Contact admin."}
    if not _verify(password, stored_hash):
        return {"success": False, "message": "Invalid email or password."}

    logger.info("Recruiter login success email=%s", email)
    return {"success": True, "message": f"Welcome, {name}!", "name": name, "email": email}
