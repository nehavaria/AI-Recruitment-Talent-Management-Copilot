"""
Shared fixtures for the AI Recruitment & Talent Management Copilot test suite.

All fixtures that touch MySQL use a dedicated test database (myrecruitment_test)
so the production database is never modified.  The test DB is created/torn down
automatically by the session-scoped `test_db` fixture.
"""

import io
import json
import struct
import wave
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import mysql.connector
import pytest

# ── Test-database config ───────────────────────────────────────────────────
# Mirrors config/settings.py but points at a separate test schema.
TEST_DB_CFG = {
    "host":      "localhost",
    "port":      3306,
    "user":      "root",
    "password":  "Nu<2406>",
    "charset":   "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}
TEST_DB_NAME = "myrecruitment_test"


# ── Low-level helpers ──────────────────────────────────────────────────────

@contextmanager
def _raw_conn(database: str | None = None):
    """Open a raw MySQL connection, optionally selecting a database."""
    cfg = dict(TEST_DB_CFG)
    if database:
        cfg["database"] = database
    conn = mysql.connector.connect(**cfg)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Session-scoped: create / drop test database ────────────────────────────

@pytest.fixture(scope="session")
def test_db():
    """
    Create the test database and all required tables once per test session.
    Drops the database after all tests finish.
    """
    # Create schema
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{TEST_DB_NAME}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.close()

    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")

        # candidates
        cur.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id   INT          PRIMARY KEY AUTO_INCREMENT,
                name           VARCHAR(255) NOT NULL,
                email          VARCHAR(255) NOT NULL UNIQUE,
                phone          VARCHAR(50),
                education      TEXT,
                skills         TEXT,
                experience     TEXT,
                projects       TEXT,
                certifications TEXT,
                resume_path    VARCHAR(500),
                recruiter_email VARCHAR(255) NOT NULL DEFAULT '',
                created_date   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_date   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # jobs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id           INT           PRIMARY KEY AUTO_INCREMENT,
                job_title        VARCHAR(255)  NOT NULL,
                department       VARCHAR(150),
                location         VARCHAR(150),
                job_type         VARCHAR(50)   DEFAULT 'Full-Time',
                experience_level VARCHAR(50)   DEFAULT 'Mid-Level',
                salary_min       DECIMAL(12,2),
                salary_max       DECIMAL(12,2),
                description      TEXT,
                requirements     TEXT,
                responsibilities TEXT,
                skills_required  TEXT,
                benefits         TEXT,
                status           VARCHAR(20)   DEFAULT 'Open',
                openings         INT           DEFAULT 1,
                posted_by        VARCHAR(255),
                deadline         DATE,
                certification    VARCHAR(255)  DEFAULT '',
                recruiter_email  VARCHAR(255)  NOT NULL DEFAULT '',
                created_date     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_date     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                               ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # ats_candidates
        cur.execute("""
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
                CONSTRAINT fk_atsc_candidate_test
                    FOREIGN KEY (candidate_id) REFERENCES candidates (candidate_id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # interview_sessions
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

        # voice_screening_answers
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voice_screening_answers (
                answer_id      INT          NOT NULL AUTO_INCREMENT,
                session_id     INT          NOT NULL DEFAULT 0,
                candidate_id   INT          NOT NULL,
                job_id         INT          NOT NULL DEFAULT 0,
                question_index TINYINT      NOT NULL,
                question_text  TEXT         NOT NULL,
                audio_path     VARCHAR(500) NOT NULL DEFAULT '',
                transcript     TEXT         NOT NULL,
                evaluation     JSON         NOT NULL,
                created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (answer_id),
                INDEX idx_vsa_candidate (candidate_id),
                INDEX idx_vsa_session   (session_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # recruiter_interviews
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recruiter_interviews (
                id             INT          NOT NULL AUTO_INCREMENT,
                candidate_id   INT          NOT NULL,
                job_title      VARCHAR(255),
                interviewer    VARCHAR(255),
                interview_date DATE,
                interview_time VARCHAR(10),
                mode           VARCHAR(50)  DEFAULT 'Online',
                meeting_link   VARCHAR(500),
                notes          TEXT,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # ats_pipeline (used by recruitment_analytics)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ats_pipeline (
                pipeline_id    INT          NOT NULL AUTO_INCREMENT,
                candidate_id   INT          NOT NULL,
                job_id         INT,
                stage          VARCHAR(50)  NOT NULL DEFAULT 'Applied',
                resume_score   FLOAT        NOT NULL DEFAULT 0,
                interview_date DATE,
                notes          TEXT,
                feedback       TEXT,
                recruiter_notes TEXT,
                recruiter_email VARCHAR(255) NOT NULL DEFAULT '',
                created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (pipeline_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.close()

    yield TEST_DB_NAME

    # Teardown — drop the entire test database
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB_NAME}`")
        cur.close()


# ── Function-scoped: clean tables between tests ────────────────────────────

@pytest.fixture()
def clean_db(test_db):
    """
    Truncate all data tables before each test so tests are fully isolated.
    Returns a context-manager factory for raw connections to the test DB.
    """
    # Clear st.cache_data caches so cached analytics functions don't return
    # stale results from a previous test's empty/populated DB state.
    try:
        from milestone4.recruitment_analytics import (
            _load_summary, _q_stage_distribution, _q_score_buckets,
            _q_skill_match_buckets, _q_candidates_by_job,
            _q_interview_performance, _q_selected_vs_rejected,
            _load_jobs_for_filter,
        )
        for fn in (_load_summary, _q_stage_distribution, _q_score_buckets,
                   _q_skill_match_buckets, _q_candidates_by_job,
                   _q_interview_performance, _q_selected_vs_rejected,
                   _load_jobs_for_filter):
            fn.clear()
    except Exception:
        pass

    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for tbl in (
            "voice_screening_answers", "interview_sessions",
            "ats_candidates", "ats_pipeline", "recruiter_interviews",
            "jobs", "candidates",
        ):
            cur.execute(f"TRUNCATE TABLE {tbl}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.close()

    yield TEST_DB_NAME


# ── Patched settings so all modules use the test DB ───────────────────────

@pytest.fixture()
def patch_db_settings(clean_db):
    """
    Monkey-patch config.settings MySQL constants to point at the test DB.
    Also patches every module that caches its own _CFG dict at import time.
    """
    patches = [
        patch("config.settings.MYSQL_DATABASE", TEST_DB_NAME),
        patch("database.db_manager.MYSQL_DATABASE", TEST_DB_NAME),
        patch("database.ats_schema.MYSQL_DATABASE", TEST_DB_NAME),
        patch("milestone3.interview_db.MYSQL_DATABASE", TEST_DB_NAME),
        patch("milestone4.voice_screening.MYSQL_DATABASE", TEST_DB_NAME),
        patch("milestone4.recruitment_analytics.MYSQL_DATABASE", TEST_DB_NAME),
        # Patch the _CFG dicts that are built at module level
        patch("milestone3.interview_db._CFG",
              dict(host="localhost", port=3306, database=TEST_DB_NAME,
                   user="root", password="Nu<2406>",
                   autocommit=False, charset="utf8mb4",
                   collation="utf8mb4_unicode_ci")),
        patch("milestone4.voice_screening._CFG",
              dict(host="localhost", port=3306, database=TEST_DB_NAME,
                   user="root", password="Nu<2406>",
                   autocommit=False, charset="utf8mb4",
                   collation="utf8mb4_unicode_ci")),
        patch("milestone4.recruitment_analytics._CFG",
              dict(host="localhost", port=3306, database=TEST_DB_NAME,
                   user="root", password="Nu<2406>",
                   autocommit=False, charset="utf8mb4")),
    ]
    started = [p.start() for p in patches]
    yield TEST_DB_NAME
    for p in patches:
        p.stop()


# ── Reusable data factories ────────────────────────────────────────────────

@pytest.fixture()
def sample_candidate(patch_db_settings):
    """Insert one candidate into the test DB and return its dict."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO candidates
                (name, email, phone, education, skills, experience,
                 projects, certifications, resume_path, recruiter_email)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            "Test Candidate",
            "test@example.com",
            "9999999999",
            "B.Tech Computer Science",
            "python, django, mysql, docker, aws",
            "3 years at TechCorp as Python Developer",
            "E-commerce platform",
            "AWS Certified Developer",
            "uploads/test_resume.pdf",
            "recruiter@example.com",
        ))
        cid = cur.lastrowid
        cur.close()
    return {
        "candidate_id": cid,
        "name": "Test Candidate",
        "email": "test@example.com",
        "phone": "9999999999",
        "education": "B.Tech Computer Science",
        "skills": "python, django, mysql, docker, aws",
        "experience": "3 years at TechCorp as Python Developer",
        "projects": "E-commerce platform",
        "certifications": "AWS Certified Developer",
        "resume_path": "uploads/test_resume.pdf",
        "recruiter_email": "recruiter@example.com",
    }


@pytest.fixture()
def sample_job(patch_db_settings):
    """Insert one job into the test DB and return its dict."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jobs
                (job_title, department, location, job_type, experience_level,
                 salary_min, salary_max, description, requirements,
                 responsibilities, skills_required, benefits, certification,
                 status, openings, posted_by, deadline, recruiter_email)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            "Python Developer",
            "Engineering",
            "Bangalore",
            "Full-Time",
            "Mid-Level",
            800000, 1200000,
            "Build scalable Python services",
            "B.Tech or equivalent",
            "Design and implement REST APIs",
            "python, django, mysql, docker",
            "Health insurance",
            "AWS Certified Developer",
            "Open",
            2,
            "recruiter@example.com",
            "2025-12-31",
            "recruiter@example.com",
        ))
        jid = cur.lastrowid
        cur.close()
    return {
        "job_id": jid,
        "job_title": "Python Developer",
        "department": "Engineering",
        "skills_required": "python, django, mysql, docker",
        "experience_level": "Mid-Level",
        "requirements": "B.Tech or equivalent",
        "certification": "AWS Certified Developer",
        "status": "Open",
        "recruiter_email": "recruiter@example.com",
    }


@pytest.fixture()
def sample_session(patch_db_settings, sample_candidate, sample_job):
    """Insert one interview session and return its id."""
    report = {
        "candidate": sample_candidate,
        "job": sample_job,
        "answers": [
            {"question": "Tell me about Python.", "answer": "Python is great.",
             "evaluation": {"score": 80, "level": "Good", "feedback": "Well answered.",
                            "technical": 80, "communication": 75, "confidence": 70,
                            "problem_solving": 78, "grammar": 82, "improvements": []}}
        ],
        "avg_score": 80.0,
        "verdict": "Strong Performance 🎉",
    }
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO interview_sessions
                (candidate_id, candidate_name, job_id, job_title,
                 avg_score, verdict, report_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            sample_candidate["candidate_id"],
            sample_candidate["name"],
            sample_job["job_id"],
            sample_job["job_title"],
            80.0,
            "Strong Performance 🎉",
            json.dumps(report),
        ))
        sid = cur.lastrowid
        cur.close()
    return sid


# ── WAV audio helper ───────────────────────────────────────────────────────

def make_wav_bytes(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate a minimal valid WAV file (silence) as bytes."""
    n_samples = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


@pytest.fixture()
def valid_wav_bytes():
    return make_wav_bytes()


@pytest.fixture()
def invalid_audio_bytes():
    return b"NOT_A_WAV_FILE_GARBAGE_DATA"
