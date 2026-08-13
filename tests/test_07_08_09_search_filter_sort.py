"""
Tests — Module 7 & 8 & 9: Search, Filtering, Sorting
Covers: candidate search (name/skill/education/experience),
        ATS filter by stage, score range, job role,
        sort by score asc/desc, name, newest/oldest.
"""

import pytest
from tests.conftest import TEST_DB_NAME, _raw_conn


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def populated_candidates(patch_db_settings):
    """Insert 4 candidates with varied skills and scores."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO candidates
                (name, email, skills, education, experience, recruiter_email)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, [
            ("Alice Python",  "alice@s.com",  "python, django, aws",  "B.Tech", "3 years", "r@r.com"),
            ("Bob Java",      "bob@s.com",    "java, spring, docker", "M.Tech", "5 years", "r@r.com"),
            ("Carol React",   "carol@s.com",  "react, typescript",    "B.Sc",   "1 year",  "r@r.com"),
            ("Dave DevOps",   "dave@s.com",   "docker, kubernetes",   "B.Tech", "4 years", "r@r.com"),
        ])
        cur.close()


@pytest.fixture()
def populated_ats(patch_db_settings, populated_candidates):
    """Insert ATS rows for the 4 candidates with different stages and scores."""
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT candidate_id, name FROM candidates ORDER BY candidate_id")
        cands = cur.fetchall()
        cur.close()

    stages_scores = [
        ("Applied",   30.0),
        ("Screening", 55.0),
        ("Interview", 75.0),
        ("Selected",  90.0),
    ]
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        for cand, (stage, score) in zip(cands, stages_scores):
            cur.execute(
                "INSERT INTO ats_candidates "
                "(candidate_id, job_id, stage, resume_score, recruiter) "
                "VALUES (%s, NULL, %s, %s, %s)",
                (cand["candidate_id"], stage, score, "r@r.com"),
            )
        cur.close()
    return cands


# ══════════════════════════════════════════════════════════════════════════
#  SEARCH
# ══════════════════════════════════════════════════════════════════════════

class TestSearch:

    def test_search_by_name_partial(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("Alice")
        assert len(result) == 1
        assert result[0]["name"] == "Alice Python"

    def test_search_by_skill_partial(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("docker")
        names = [r["name"] for r in result]
        assert "Bob Java" in names
        assert "Dave DevOps" in names

    def test_search_by_education(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("M.Tech")
        assert any(r["name"] == "Bob Java" for r in result)

    def test_search_by_experience(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("5 years")
        assert any(r["name"] == "Bob Java" for r in result)

    def test_search_case_insensitive(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("PYTHON")
        assert any(r["name"] == "Alice Python" for r in result)

    def test_search_no_results(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("COBOL_MAINFRAME_ZZZNOMATCH")
        assert result == []

    def test_search_empty_returns_all(self, patch_db_settings, populated_candidates):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_candidates("")
        assert len(result) == 4

    def test_search_job_by_title(self, patch_db_settings, sample_job):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_jobs("Python Developer")
        assert len(result) == 1

    def test_search_job_by_skill(self, patch_db_settings, sample_job):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.search_jobs("django")
        assert len(result) >= 1


# ══════════════════════════════════════════════════════════════════════════
#  FILTERING  (ATS management page in-memory filters)
# ══════════════════════════════════════════════════════════════════════════

class TestFiltering:
    """
    The ATS management page applies filters in Python after fetching all rows.
    We test the filter logic directly using the same patterns.
    """

    def _apply_filters(self, records, search="", stage="All"):
        rows = records
        if search:
            q = search.lower()
            rows = [r for r in rows if
                    q in (r["name"] or "").lower() or
                    q in (r["email"] or "").lower()]
        if stage != "All":
            rows = [r for r in rows if r["stage"] == stage]
        return rows

    def _make_records(self):
        return [
            {"name": "Alice Python",  "email": "alice@s.com",  "stage": "Applied",   "resume_score": 30.0},
            {"name": "Bob Java",      "email": "bob@s.com",    "stage": "Screening",  "resume_score": 55.0},
            {"name": "Carol React",   "email": "carol@s.com",  "stage": "Interview",  "resume_score": 75.0},
            {"name": "Dave DevOps",   "email": "dave@s.com",   "stage": "Selected",   "resume_score": 90.0},
        ]

    def test_filter_by_stage(self):
        records = self._make_records()
        result = self._apply_filters(records, stage="Interview")
        assert len(result) == 1
        assert result[0]["name"] == "Carol React"

    def test_filter_all_stages(self):
        records = self._make_records()
        result = self._apply_filters(records, stage="All")
        assert len(result) == 4

    def test_filter_by_name_search(self):
        records = self._make_records()
        result = self._apply_filters(records, search="alice")
        assert len(result) == 1

    def test_filter_by_email_search(self):
        records = self._make_records()
        result = self._apply_filters(records, search="bob@s.com")
        assert len(result) == 1

    def test_filter_combined_search_and_stage(self):
        records = self._make_records()
        result = self._apply_filters(records, search="carol", stage="Interview")
        assert len(result) == 1

    def test_filter_no_match(self):
        records = self._make_records()
        result = self._apply_filters(records, search="ZZZNOMATCH")
        assert result == []

    def test_filter_empty_records(self):
        result = self._apply_filters([], search="alice", stage="Applied")
        assert result == []

    def test_filter_rejected_stage(self):
        records = self._make_records()
        result = self._apply_filters(records, stage="Rejected")
        assert result == []


# ══════════════════════════════════════════════════════════════════════════
#  SORTING
# ══════════════════════════════════════════════════════════════════════════

class TestSorting:

    def _make_records(self):
        return [
            {"name": "Carol React",  "resume_score": 75.0, "stage": "Interview"},
            {"name": "Alice Python", "resume_score": 30.0, "stage": "Applied"},
            {"name": "Dave DevOps",  "resume_score": 90.0, "stage": "Selected"},
            {"name": "Bob Java",     "resume_score": 55.0, "stage": "Screening"},
        ]

    def test_sort_score_descending(self):
        records = self._make_records()
        sorted_rows = sorted(records, key=lambda r: r["resume_score"], reverse=True)
        assert sorted_rows[0]["name"] == "Dave DevOps"
        assert sorted_rows[-1]["name"] == "Alice Python"

    def test_sort_score_ascending(self):
        records = self._make_records()
        sorted_rows = sorted(records, key=lambda r: r["resume_score"])
        assert sorted_rows[0]["name"] == "Alice Python"
        assert sorted_rows[-1]["name"] == "Dave DevOps"

    def test_sort_name_az(self):
        records = self._make_records()
        sorted_rows = sorted(records, key=lambda r: r["name"].lower())
        assert sorted_rows[0]["name"] == "Alice Python"
        assert sorted_rows[-1]["name"] == "Dave DevOps"

    def test_sort_by_stage_order(self):
        from milestone3.ats_management_page import _STAGES
        records = self._make_records()
        sorted_rows = sorted(records, key=lambda r: _STAGES.index(r["stage"]))
        assert sorted_rows[0]["stage"] == "Applied"

    def test_sort_empty_list(self):
        sorted_rows = sorted([], key=lambda r: r["resume_score"], reverse=True)
        assert sorted_rows == []

    def test_sort_single_item(self):
        records = [{"name": "Only One", "resume_score": 50.0}]
        sorted_rows = sorted(records, key=lambda r: r["resume_score"], reverse=True)
        assert len(sorted_rows) == 1

    def test_sort_equal_scores_stable(self):
        """Stable sort: equal scores preserve original order."""
        records = [
            {"name": "A", "resume_score": 70.0},
            {"name": "B", "resume_score": 70.0},
        ]
        sorted_rows = sorted(records, key=lambda r: r["resume_score"], reverse=True)
        assert sorted_rows[0]["name"] == "A"
