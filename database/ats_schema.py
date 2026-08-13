"""
ATS MySQL schema — 4 tables, created only if they do not already exist.

Tables
------
1. ats_candidates      — pipeline entry per candidate (job_id nullable, no FK)
2. recruiter_notes     — FK → ats_candidates
3. interview_schedule  — FK → ats_candidates
4. interview_feedback  — FK → ats_candidates + interview_schedule

Existing tables (candidates, jobs) are never touched.
"""

import logging
from contextlib import contextmanager
from typing import Generator

import mysql.connector

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)

logger = logging.getLogger(__name__)

# ── DDL — job_id is nullable, no FK to jobs ────────────────────────────────

_DDL: list[str] = [

    # 1. ats_candidates  (job_id nullable — no FK constraint on job_id)
    """
    CREATE TABLE IF NOT EXISTS ats_candidates (
        ats_id         INT           NOT NULL AUTO_INCREMENT,
        candidate_id   INT           NOT NULL,
        job_id         INT           NULL DEFAULT NULL,
        cand_name      VARCHAR(255),
        email          VARCHAR(255),
        phone          VARCHAR(50),
        resume_score   FLOAT         NOT NULL DEFAULT 0,
        stage          VARCHAR(50)   NOT NULL DEFAULT 'Applied',
        recruiter      VARCHAR(255),
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (ats_id),
        UNIQUE  KEY uq_cand_job (candidate_id, job_id),
        CONSTRAINT fk_atsc_candidate
            FOREIGN KEY (candidate_id) REFERENCES candidates (candidate_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # 2. recruiter_notes
    """
    CREATE TABLE IF NOT EXISTS recruiter_notes (
        note_id        INT           NOT NULL AUTO_INCREMENT,
        ats_id         INT           NOT NULL,
        recruiter      VARCHAR(255),
        note           TEXT          NOT NULL,
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (note_id),
        CONSTRAINT fk_rn_ats
            FOREIGN KEY (ats_id) REFERENCES ats_candidates (ats_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # 3. interview_schedule
    """
    CREATE TABLE IF NOT EXISTS interview_schedule (
        schedule_id    INT           NOT NULL AUTO_INCREMENT,
        ats_id         INT           NOT NULL,
        interview_date DATE,
        interview_time VARCHAR(10),
        mode           VARCHAR(50)   DEFAULT 'In-Person',
        interviewer    VARCHAR(255),
        location       VARCHAR(255),
        status         VARCHAR(50)   DEFAULT 'Scheduled',
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (schedule_id),
        CONSTRAINT fk_is_ats
            FOREIGN KEY (ats_id) REFERENCES ats_candidates (ats_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # 4. interview_feedback
    """
    CREATE TABLE IF NOT EXISTS interview_feedback (
        feedback_id    INT           NOT NULL AUTO_INCREMENT,
        ats_id         INT           NOT NULL,
        schedule_id    INT,
        interviewer    VARCHAR(255),
        rating         TINYINT       DEFAULT NULL COMMENT '1-5 scale',
        strengths      TEXT,
        weaknesses     TEXT,
        recommendation VARCHAR(50)   DEFAULT 'Pending',
        comments       TEXT,
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (feedback_id),
        CONSTRAINT fk_if_ats
            FOREIGN KEY (ats_id)      REFERENCES ats_candidates    (ats_id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        CONSTRAINT fk_if_schedule
            FOREIGN KEY (schedule_id) REFERENCES interview_schedule (schedule_id)
            ON DELETE SET NULL ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


# ── Connection helpers ─────────────────────────────────────────────────────

@contextmanager
def _connect(autocommit: bool = False) -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        autocommit=autocommit, charset="utf8mb4",
        collation="utf8mb4_unicode_ci", raise_on_warnings=False,
    )
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


def _query_one(sql: str, params: tuple = ()) -> any:
    """Run a SELECT and return the first column of the first row."""
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
    return row[0] if row else None


def _exec(sql: str) -> None:
    """Run a single DDL/ALTER statement with autocommit=True."""
    with _connect(autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cur.close()


# ── Patch helpers — each check + alter is fully independent ───────────────

# ── Public entry point ─────────────────────────────────────────────────────

_schema_initialized = False  # module-level guard — runs once per process


def init_ats_schema() -> None:
    """
    Create all 4 ATS tables if they do not exist.
    Runs only once per process — subsequent calls are no-ops.
    """
    global _schema_initialized
    if _schema_initialized:
        return

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for ddl in _DDL:
            cur.execute(ddl)
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.close()

    _schema_initialized = True
    logger.info("ATS schema ready — ats_candidates, recruiter_notes, interview_schedule, interview_feedback")
