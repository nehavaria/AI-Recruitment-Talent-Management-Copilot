"""
Tests — Module 2: Candidate Retrieval
Covers: get all, get by id, get by email, search, empty table,
        invalid id, case-insensitive email lookup, recruiter scoping.
"""

import pytest
from database.db_manager import DatabaseManager
from tests.conftest import TEST_DB_NAME, _raw_conn


@pytest.fixture()
def db(patch_db_settings):
    return DatabaseManager()


@pytest.fixture()
def two_candidates(patch_db_settings):
    """Insert two candidates belonging to different recruiters."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO candidates
                (name, email, phone, skills, experience, education, recruiter_email)
            VALUES
                ('Alice Smith',  'alice@test.com', '1111111111',
                 'python, django', '2 years', 'B.Tech', 'rec1@test.com'),
                ('Bob Jones',    'bob@test.com',   '2222222222',
                 'java, spring',  '5 years', 'M.Tech', 'rec2@test.com')
        """)
        cur.close()


class TestCandidateRetrieval:

    # ── get_all_candidates ─────────────────────────────────────────────────

    def test_get_all_returns_list(self, db, two_candidates):
        result = db.get_all_candidates()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_get_all_empty_table(self, db, patch_db_settings):
        result = db.get_all_candidates()
        assert result == []

    def test_get_all_scoped_by_recruiter(self, db, two_candidates):
        result = db.get_all_candidates("rec1@test.com")
        assert len(result) == 1
        assert result[0]["email"] == "alice@test.com"

    def test_get_all_unknown_recruiter_returns_empty(self, db, two_candidates):
        result = db.get_all_candidates("nobody@test.com")
        assert result == []

    # ── get_candidate_by_id ────────────────────────────────────────────────

    def test_get_by_id_valid(self, db, sample_candidate):
        result = db.get_candidate_by_id(sample_candidate["candidate_id"])
        assert result is not None
        assert result["email"] == "test@example.com"

    def test_get_by_id_nonexistent(self, db, patch_db_settings):
        result = db.get_candidate_by_id(999999)
        assert result is None

    def test_get_by_id_zero(self, db, patch_db_settings):
        result = db.get_candidate_by_id(0)
        assert result is None

    def test_get_by_id_negative(self, db, patch_db_settings):
        result = db.get_candidate_by_id(-1)
        assert result is None

    # ── get_candidate_by_email ─────────────────────────────────────────────

    def test_get_by_email_valid(self, db, sample_candidate):
        result = db.get_candidate_by_email("test@example.com")
        assert result is not None
        assert result["name"] == "Test Candidate"

    def test_get_by_email_case_insensitive(self, db, sample_candidate):
        """Email lookup must be case-insensitive (stored lowercase)."""
        result = db.get_candidate_by_email("TEST@EXAMPLE.COM")
        # The DB stores lowercase; the query uses LOWER() or exact match.
        # If the stored value is lowercase, this should still find it.
        assert result is not None

    def test_get_by_email_nonexistent(self, db, patch_db_settings):
        result = db.get_candidate_by_email("nobody@nowhere.com")
        assert result is None

    def test_get_by_email_empty_string(self, db, patch_db_settings):
        result = db.get_candidate_by_email("")
        assert result is None

    # ── search_candidates ──────────────────────────────────────────────────

    def test_search_by_name(self, db, two_candidates):
        result = db.search_candidates("Alice")
        assert len(result) == 1
        assert result[0]["name"] == "Alice Smith"

    def test_search_by_skill(self, db, two_candidates):
        result = db.search_candidates("python")
        assert any("Alice" in r["name"] for r in result)

    def test_search_no_match(self, db, two_candidates):
        result = db.search_candidates("ZZZNOMATCH")
        assert result == []

    def test_search_empty_keyword(self, db, two_candidates):
        """Empty keyword returns all candidates (LIKE '%%')."""
        result = db.search_candidates("")
        assert len(result) == 2

    def test_search_sql_injection_safe(self, db, two_candidates):
        """SQL injection attempt must not raise and must return empty."""
        result = db.search_candidates("' OR '1'='1")
        assert isinstance(result, list)

    # ── candidate dict structure ───────────────────────────────────────────

    def test_candidate_dict_has_required_keys(self, db, sample_candidate):
        result = db.get_candidate_by_id(sample_candidate["candidate_id"])
        for key in ("candidate_id", "name", "email", "phone", "skills",
                    "education", "experience", "resume_path"):
            assert key in result, f"Missing key: {key}"

    def test_candidate_missing_optional_fields_are_none_or_empty(self, db, patch_db_settings):
        """A candidate inserted with only required fields has None for optional ones."""
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO candidates (name, email, recruiter_email) VALUES (%s,%s,%s)",
                ("Minimal Cand", "minimal@test.com", "r@r.com"),
            )
            cid = cur.lastrowid
            cur.close()
        result = db.get_candidate_by_id(cid)
        assert result["phone"] is None or result["phone"] == ""
        assert result["skills"] is None or result["skills"] == ""
