"""MySQL database manager: schema, CRUD for candidates and jobs."""

import logging
from contextlib import contextmanager
from typing import Any, Generator

import mysql.connector

from config.settings import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_SSL_CA,
)

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────

_CANDIDATES_TABLE = """
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
);
"""

_JOBS_TABLE = """
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
);
"""


class DatabaseManager:
    """Manages all MySQL interactions for the recruitment database."""

    def __init__(self) -> None:
        self._config = {
            "host":              MYSQL_HOST,
            "port":              MYSQL_PORT,
            "database":          MYSQL_DATABASE,
            "user":              MYSQL_USER,
            "password":          MYSQL_PASSWORD,
            "autocommit":        False,
            "charset":           "utf8mb4",
            "collation":         "utf8mb4_unicode_ci",
            "raise_on_warnings": False,
        }
        # SSL for cloud-hosted MySQL (PlanetScale, Railway, Aiven, etc.)
        if MYSQL_SSL_CA:
            self._config["ssl_ca"] = MYSQL_SSL_CA
            self._config["ssl_verify_cert"] = True
        self._init_schema()

    # ── Connection ─────────────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Generator[mysql.connector.MySQLConnection, None, None]:
        conn = mysql.connector.connect(**self._config)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(_CANDIDATES_TABLE)
            cur.execute(_JOBS_TABLE)
            # Add recruiter_email to existing tables that predate this change
            for table in ("candidates", "jobs"):
                try:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN recruiter_email VARCHAR(255) NOT NULL DEFAULT ''")
                except Exception:
                    pass  # column already exists
            cur.close()
        logger.info("MySQL schema ready — host=%s db=%s", MYSQL_HOST, MYSQL_DATABASE)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(cursor: Any, row: tuple) -> dict[str, Any]:
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))

    # ══════════════════════════════════════════════════════════════════════
    #  CANDIDATES CRUD
    # ══════════════════════════════════════════════════════════════════════

    def create_candidate(self, data: dict[str, Any]) -> int:
        sql = """
            INSERT INTO candidates
                (name, email, phone, education, skills, experience,
                 projects, certifications, resume_path, recruiter_email)
            VALUES
                (%(name)s, %(email)s, %(phone)s, %(education)s, %(skills)s,
                 %(experience)s, %(projects)s, %(certifications)s, %(resume_path)s,
                 %(recruiter_email)s)
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, data)
            row_id: int = cur.lastrowid
            cur.close()
        logger.info("Created candidate id=%s email=%s", row_id, data.get("email"))
        return row_id

    def replace_candidate(self, data: dict[str, Any]) -> int:
        """
        Replace a candidate's record or insert a new one using REPLACE INTO.

        This works based on a PRIMARY KEY or UNIQUE index. If a row with the
        same `candidate_id` or `email` exists, it's deleted and the new
        row is inserted. Otherwise, it's a standard insertion.
        """
        sql = """
            REPLACE INTO candidates
                (candidate_id, name, email, phone, education, skills, experience,
                 projects, certifications, resume_path)
            VALUES
                (%(candidate_id)s, %(name)s, %(email)s, %(phone)s, %(education)s, %(skills)s,
                 %(experience)s, %(projects)s, %(certifications)s, %(resume_path)s)
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, data)
            row_id: int = cur.lastrowid
            cur.close()
        logger.info("Replaced/Created candidate id=%s email=%s", row_id, data.get("email"))
        return row_id

    def upsert_candidate(self, data: dict[str, Any]) -> int:
        sql = """
            INSERT INTO candidates
                (name, email, phone, education, skills, experience,
                 projects, certifications, resume_path)
            VALUES
                (%(name)s, %(email)s, %(phone)s, %(education)s, %(skills)s,
                 %(experience)s, %(projects)s, %(certifications)s, %(resume_path)s)
            ON DUPLICATE KEY UPDATE
                name           = VALUES(name),
                phone          = VALUES(phone),
                education      = VALUES(education),
                skills         = VALUES(skills),
                experience     = VALUES(experience),
                projects       = VALUES(projects),
                certifications = VALUES(certifications),
                resume_path    = VALUES(resume_path)
            ;
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, data)
            # For ON DUPLICATE KEY UPDATE, LAST_INSERT_ID() returns the ID of the updated row.
            cur.execute("SELECT LAST_INSERT_ID()")
            row = cur.fetchone()
            cur.close()
        candidate_id: int = row[0] if row else -1
        logger.info("Upserted candidate id=%s email=%s", candidate_id, data.get("email"))
        return candidate_id

    def get_all_candidates(self, recruiter_email: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            if recruiter_email:
                cur.execute("SELECT * FROM candidates WHERE recruiter_email = %s ORDER BY created_date DESC", (recruiter_email,))
            else:
                cur.execute("SELECT * FROM candidates ORDER BY created_date DESC")
            rows = cur.fetchall()
            result = [self._row_to_dict(cur, r) for r in rows]
            cur.close()
        return result

    def get_candidate_by_id(self, candidate_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM candidates WHERE candidate_id = %s", (candidate_id,))
            row = cur.fetchone()
            result = self._row_to_dict(cur, row) if row else None
            cur.close()
        return result

    def get_candidate_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM candidates WHERE email = %s", (email.lower(),))
            row = cur.fetchone()
            result = self._row_to_dict(cur, row) if row else None
            cur.close()
        return result

    def search_candidates(self, keyword: str) -> list[dict[str, Any]]:
        pattern = f"%{keyword}%"
        sql = """
            SELECT * FROM candidates
            WHERE name LIKE %s OR skills LIKE %s
               OR experience LIKE %s OR education LIKE %s
            ORDER BY created_date DESC
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (pattern, pattern, pattern, pattern))
            rows = cur.fetchall()
            result = [self._row_to_dict(cur, r) for r in rows]
            cur.close()
        return result

    def update_candidate(self, candidate_id: int, data: dict[str, Any]) -> bool:
        allowed = {
            "name", "email", "phone", "education", "skills",
            "experience", "projects", "certifications", "resume_path",
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{col} = %({col})s" for col in fields)
        fields["candidate_id"] = candidate_id
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE candidates SET {set_clause} WHERE candidate_id = %(candidate_id)s",
                fields,
            )
            updated = cur.rowcount > 0
            cur.close()
        if updated:
            logger.info("Updated candidate id=%s", candidate_id)
        return updated

    def delete_candidate(self, candidate_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM candidates WHERE candidate_id = %s", (candidate_id,))
            deleted = cur.rowcount > 0
            cur.close()
        if deleted:
            logger.info("Deleted candidate id=%s", candidate_id)
        return deleted

    # ══════════════════════════════════════════════════════════════════════
    #  JOBS CRUD
    # ══════════════════════════════════════════════════════════════════════

    def create_job(self, data: dict[str, Any]) -> int:
        sql = """
            INSERT INTO jobs
                (job_title, department, location, job_type, experience_level,
                 salary_min, salary_max, description, requirements,
                 responsibilities, skills_required, benefits, certification,
                 status, openings, posted_by, deadline, recruiter_email)
            VALUES
                (%(job_title)s, %(department)s, %(location)s, %(job_type)s,
                 %(experience_level)s, %(salary_min)s, %(salary_max)s,
                 %(description)s, %(requirements)s, %(responsibilities)s,
                 %(skills_required)s, %(benefits)s, %(certification)s, %(status)s,
                 %(openings)s, %(posted_by)s, %(deadline)s, %(recruiter_email)s)
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, data)
            job_id: int = cur.lastrowid
            cur.close()
        logger.info("Created job id=%s title=%s", job_id, data.get("job_title"))
        return job_id

    def replace_job(self, data: dict[str, Any]) -> int:
        """
        Replace a job's record or insert a new one using REPLACE INTO.

        This works based on a PRIMARY KEY (job_id). If a row with the
        same `job_id` exists, it's deleted and the new row is inserted.
        Otherwise, it's a standard insertion.
        """
        sql = """
            REPLACE INTO jobs
                (job_id, job_title, department, location, job_type, experience_level,
                 salary_min, salary_max, description, requirements,
                 responsibilities, skills_required, benefits, certification,
                 status, openings, posted_by, deadline)
            VALUES
                (%(job_id)s, %(job_title)s, %(department)s, %(location)s, %(job_type)s,
                 %(experience_level)s, %(salary_min)s, %(salary_max)s,
                 %(description)s, %(requirements)s, %(responsibilities)s,
                 %(skills_required)s, %(benefits)s, %(certification)s, %(status)s,
                 %(openings)s, %(posted_by)s, %(deadline)s)
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, data)
            row_id: int = cur.lastrowid
            cur.close()
        logger.info("Replaced/Created job id=%s title=%s", row_id, data.get("job_title"))
        return row_id

    def get_all_jobs(self, recruiter_email: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            if recruiter_email:
                cur.execute("SELECT * FROM jobs WHERE recruiter_email = %s ORDER BY created_date DESC", (recruiter_email,))
            else:
                cur.execute("SELECT * FROM jobs ORDER BY created_date DESC")
            rows = cur.fetchall()
            result = [self._row_to_dict(cur, r) for r in rows]
            cur.close()
        return result

    def get_job_by_id(self, job_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
            result = self._row_to_dict(cur, row) if row else None
            cur.close()
        return result

    def get_open_jobs(self, recruiter_email: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            if recruiter_email:
                cur.execute(
                    "SELECT * FROM jobs WHERE status = 'Open' AND recruiter_email = %s ORDER BY created_date DESC",
                    (recruiter_email,)
                )
            else:
                cur.execute("SELECT * FROM jobs WHERE status = 'Open' ORDER BY created_date DESC")
            rows = cur.fetchall()
            result = [self._row_to_dict(cur, r) for r in rows]
            cur.close()
        return result

    def search_jobs(self, keyword: str) -> list[dict[str, Any]]:
        pattern = f"%{keyword}%"
        sql = """
            SELECT * FROM jobs
            WHERE job_title LIKE %s OR department LIKE %s
               OR skills_required LIKE %s OR description LIKE %s
            ORDER BY created_date DESC
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (pattern, pattern, pattern, pattern))
            rows = cur.fetchall()
            result = [self._row_to_dict(cur, r) for r in rows]
            cur.close()
        return result

    def update_job(self, job_id: int, data: dict[str, Any]) -> bool:
        allowed = {
            "job_title", "department", "location", "job_type", "experience_level",
            "salary_min", "salary_max", "description", "requirements",
            "responsibilities", "skills_required", "benefits", "certification",
            "status", "openings", "posted_by", "deadline",
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{col} = %({col})s" for col in fields)
        fields["job_id"] = job_id
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE jobs SET {set_clause} WHERE job_id = %(job_id)s",
                fields,
            )
            updated = cur.rowcount > 0
            cur.close()
        if updated:
            logger.info("Updated job id=%s", job_id)
        return updated

    def delete_job(self, job_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
            deleted = cur.rowcount > 0
            cur.close()
        if deleted:
            logger.info("Deleted job id=%s", job_id)
        return deleted
