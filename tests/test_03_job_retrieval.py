"""
Tests — Module 3: Job Retrieval
Covers: get all, get by id, get open jobs, search, recruiter scoping,
        empty table, invalid inputs.
"""

import pytest
from database.db_manager import DatabaseManager
from tests.conftest import TEST_DB_NAME, _raw_conn


@pytest.fixture()
def db(patch_db_settings):
    return DatabaseManager()


@pytest.fixture()
def two_jobs(patch_db_settings):
    """Insert two jobs: one Open (rec1), one Closed (rec2)."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jobs
                (job_title, department, skills_required, status,
                 experience_level, recruiter_email)
            VALUES
                ('Python Developer', 'Engineering', 'python, django',
                 'Open',   'Mid-Level', 'rec1@test.com'),
                ('Java Developer',   'Engineering', 'java, spring',
                 'Closed', 'Senior',   'rec2@test.com')
        """)
        cur.close()


class TestJobRetrieval:

    # ── get_all_jobs ───────────────────────────────────────────────────────

    def test_get_all_returns_list(self, db, two_jobs):
        result = db.get_all_jobs()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_get_all_empty_table(self, db, patch_db_settings):
        result = db.get_all_jobs()
        assert result == []

    def test_get_all_scoped_by_recruiter(self, db, two_jobs):
        result = db.get_all_jobs("rec1@test.com")
        assert len(result) == 1
        assert result[0]["job_title"] == "Python Developer"

    def test_get_all_unknown_recruiter_returns_empty(self, db, two_jobs):
        result = db.get_all_jobs("nobody@test.com")
        assert result == []

    # ── get_job_by_id ──────────────────────────────────────────────────────

    def test_get_by_id_valid(self, db, sample_job):
        result = db.get_job_by_id(sample_job["job_id"])
        assert result is not None
        assert result["job_title"] == "Python Developer"

    def test_get_by_id_nonexistent(self, db, patch_db_settings):
        result = db.get_job_by_id(999999)
        assert result is None

    def test_get_by_id_zero(self, db, patch_db_settings):
        result = db.get_job_by_id(0)
        assert result is None

    # ── get_open_jobs ──────────────────────────────────────────────────────

    def test_get_open_jobs_filters_closed(self, db, two_jobs):
        result = db.get_open_jobs()
        assert all(j["status"] == "Open" for j in result)
        assert len(result) == 1

    def test_get_open_jobs_empty(self, db, patch_db_settings):
        result = db.get_open_jobs()
        assert result == []

    def test_get_open_jobs_scoped_by_recruiter(self, db, two_jobs):
        result = db.get_open_jobs("rec1@test.com")
        assert len(result) == 1
        assert result[0]["job_title"] == "Python Developer"

    # ── search_jobs ────────────────────────────────────────────────────────

    def test_search_by_title(self, db, two_jobs):
        result = db.search_jobs("Python")
        assert len(result) == 1
        assert result[0]["job_title"] == "Python Developer"

    def test_search_by_skill(self, db, two_jobs):
        result = db.search_jobs("django")
        assert len(result) == 1

    def test_search_no_match(self, db, two_jobs):
        result = db.search_jobs("ZZZNOMATCH")
        assert result == []

    def test_search_empty_keyword(self, db, two_jobs):
        result = db.search_jobs("")
        assert len(result) == 2

    def test_search_sql_injection_safe(self, db, two_jobs):
        result = db.search_jobs("' OR '1'='1")
        assert isinstance(result, list)

    # ── job dict structure ─────────────────────────────────────────────────

    def test_job_dict_has_required_keys(self, db, sample_job):
        result = db.get_job_by_id(sample_job["job_id"])
        for key in ("job_id", "job_title", "department", "skills_required",
                    "status", "experience_level"):
            assert key in result, f"Missing key: {key}"
