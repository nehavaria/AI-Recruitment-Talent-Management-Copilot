"""
interview_db.py — MySQL persistence for AI Interview Simulator reports.
Stores full session data so reports survive Streamlit restarts.
Uses the same MySQL connection as the rest of the project.
Never modifies any existing table or file.
"""

import json
import logging
from contextlib import contextmanager
from typing import Generator

import mysql.connector

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)

logger = logging.getLogger(__name__)

_CFG = dict(
    host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
    user=MYSQL_USER, password=MYSQL_PASSWORD,
    autocommit=False, charset="utf8mb4",
    collation="utf8mb4_unicode_ci",
)


@contextmanager
def _conn() -> Generator[mysql.connector.MySQLConnection, None, None]:
    """Context manager for MySQL connection with auto-commit/rollback."""
    con = mysql.connector.connect(**_CFG)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create the interview_sessions table in MySQL if it does not exist."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interview_sessions (
                session_id     INT          NOT NULL AUTO_INCREMENT,
                candidate_id   INT          NOT NULL DEFAULT 0,
                candidate_name VARCHAR(255) NOT NULL DEFAULT '',
                job_id         INT          NOT NULL DEFAULT 0,
                job_title      VARCHAR(255) NOT NULL DEFAULT '',
                avg_score      FLOAT        NOT NULL DEFAULT 0,
                verdict        VARCHAR(255) NOT NULL DEFAULT '',
                report_json    LONGTEXT     NOT NULL,
                created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id),
                INDEX idx_candidate (candidate_id),
                INDEX idx_created   (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.close()
    logger.info("interview_sessions table ready in MySQL db=%s", MYSQL_DATABASE)


def save_report(report: dict) -> int:
    """
    Persist a simulator report dict to MySQL.
    Returns the new session_id (auto-increment).
    """
    cand    = report.get("candidate", {})
    job     = report.get("job", {})
    cid     = cand.get("candidate_id") or 0
    cname   = (cand.get("name") or "Unknown").splitlines()[0]
    jid     = job.get("job_id") or 0
    jtitle  = job.get("job_title") or "—"
    avg     = report.get("avg_score", 0)
    verdict = report.get("verdict", "")

    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO interview_sessions
                (candidate_id, candidate_name, job_id, job_title,
                 avg_score, verdict, report_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (cid, cname, jid, jtitle, avg, verdict,
             json.dumps(report, default=str)),
        )
        new_id = cur.lastrowid
        cur.close()
    logger.info("Saved interview session id=%s candidate=%s", new_id, cname)
    return new_id


def load_latest_report(candidate_id: int | None = None) -> dict | None:
    """
    Load the most recent report from MySQL, optionally filtered by candidate_id.
    Returns the deserialized report dict or None.
    """
    with _conn() as con:
        cur = con.cursor(dictionary=True)
        if candidate_id:
            cur.execute(
                "SELECT report_json FROM interview_sessions "
                "WHERE candidate_id = %s ORDER BY created_at DESC LIMIT 1",
                (candidate_id,),
            )
        else:
            cur.execute(
                "SELECT report_json FROM interview_sessions "
                "ORDER BY created_at DESC LIMIT 1"
            )
        row = cur.fetchone()
        cur.close()
    return json.loads(row["report_json"]) if row else None


def load_all_sessions() -> list[dict]:
    """
    Load summary rows for all sessions (no full JSON) for the history list.
    Returns list of dicts: session_id, candidate_name, job_title,
    avg_score, verdict, created_at.
    """
    with _conn() as con:
        cur = con.cursor(dictionary=True)
        cur.execute(
            "SELECT session_id, candidate_id, candidate_name, job_id, "
            "job_title, avg_score, verdict, created_at "
            "FROM interview_sessions ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
        cur.close()
    return rows


def load_session_by_id(session_id: int) -> dict | None:
    """Load a full report by its session_id from MySQL."""
    with _conn() as con:
        cur = con.cursor(dictionary=True)
        cur.execute(
            "SELECT report_json FROM interview_sessions WHERE session_id = %s",
            (session_id,),
        )
        row = cur.fetchone()
        cur.close()
    return json.loads(row["report_json"]) if row else None


def delete_session(session_id: int) -> None:
    """Delete a session record by ID from MySQL."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            "DELETE FROM interview_sessions WHERE session_id = %s",
            (session_id,),
        )
        cur.close()
    logger.info("Deleted interview session id=%s", session_id)
