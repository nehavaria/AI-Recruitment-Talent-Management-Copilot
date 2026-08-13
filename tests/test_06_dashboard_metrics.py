"""
Tests — Module 6: Dashboard Metrics
Covers: _load_summary, _q_stage_distribution, _q_score_buckets,
        _q_candidates_by_job, _q_interview_performance,
        _q_selected_vs_rejected — with data, empty data, DB error.
"""

import pytest
from tests.conftest import TEST_DB_NAME, _raw_conn


def _insert_ats_row(candidate_id, stage, resume_score, recruiter="rec@test.com"):
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ats_candidates "
            "(candidate_id, job_id, stage, resume_score, recruiter) "
            "VALUES (%s, NULL, %s, %s, %s)",
            (candidate_id, stage, resume_score, recruiter),
        )
        cur.close()


class TestDashboardMetrics:

    # ── _load_summary ──────────────────────────────────────────────────────

    def test_summary_empty_db(self, patch_db_settings):
        from milestone4.recruitment_analytics import _load_summary
        s = _load_summary("")
        assert s["total"] == 0
        assert s["avg_score"] == 0.0
        assert s["selected"] == 0
        assert s["sessions"] == 0

    def test_summary_with_data(self, patch_db_settings, sample_candidate, sample_session):
        from milestone4.recruitment_analytics import _load_summary
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Selected", 85.0)
        s = _load_summary("")
        assert s["total"] >= 1
        assert s["selected"] >= 1
        assert s["sessions"] >= 1

    def test_summary_scoped_by_recruiter(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _load_summary
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Applied", 60.0, recruiter="specific@test.com")
        s = _load_summary("specific@test.com")
        assert s["total"] == 1

    def test_summary_unknown_recruiter_returns_zeros(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _load_summary
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Applied", 60.0)
        s = _load_summary("nobody@test.com")
        assert s["total"] == 0

    def test_summary_returns_dict_with_all_keys(self, patch_db_settings):
        from milestone4.recruitment_analytics import _load_summary
        s = _load_summary("")
        for key in ("total", "avg_score", "selected", "rejected", "interviews", "sessions"):
            assert key in s

    # ── _q_stage_distribution ──────────────────────────────────────────────

    def test_stage_distribution_empty(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_stage_distribution
        rows = _q_stage_distribution("")
        assert rows == []

    def test_stage_distribution_with_data(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _q_stage_distribution
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Applied", 50.0)
        rows = _q_stage_distribution("")
        assert any(r["stage"] == "Applied" for r in rows)

    def test_stage_distribution_counts_correctly(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _q_stage_distribution
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Screening", 60.0)
        rows = _q_stage_distribution("")
        screening = next((r for r in rows if r["stage"] == "Screening"), None)
        assert screening is not None
        assert screening["cnt"] == 1

    # ── _q_score_buckets ───────────────────────────────────────────────────

    def test_score_buckets_empty(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_score_buckets
        rows = _q_score_buckets("")
        assert rows == []

    def test_score_buckets_correct_bucket(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _q_score_buckets
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Applied", 85.0)
        rows = _q_score_buckets("")
        assert any(r["bucket"] == "80–100" for r in rows)

    # ── _q_candidates_by_job ───────────────────────────────────────────────

    def test_candidates_by_job_empty(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_candidates_by_job
        rows = _q_candidates_by_job("")
        assert rows == []

    def test_candidates_by_job_unassigned(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _q_candidates_by_job
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Applied", 50.0)
        rows = _q_candidates_by_job("")
        assert any(r["job_title"] == "Unassigned" for r in rows)

    # ── _q_interview_performance ───────────────────────────────────────────

    def test_interview_performance_empty(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_interview_performance
        rows = _q_interview_performance("")
        assert rows == []

    def test_interview_performance_with_session(self, patch_db_settings, sample_session):
        from milestone4.recruitment_analytics import _q_interview_performance
        rows = _q_interview_performance("")
        assert len(rows) >= 1
        assert all("verdict" in r and "avg_score" in r for r in rows)

    # ── _q_selected_vs_rejected ────────────────────────────────────────────

    def test_selected_vs_rejected_empty(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_selected_vs_rejected
        data = _q_selected_vs_rejected("")
        assert data == {"selected": 0, "rejected": 0, "active": 0}

    def test_selected_vs_rejected_counts(self, patch_db_settings, sample_candidate):
        from milestone4.recruitment_analytics import _q_selected_vs_rejected
        cid = sample_candidate["candidate_id"]
        _insert_ats_row(cid, "Selected", 90.0)
        data = _q_selected_vs_rejected("")
        assert data["selected"] == 1
        assert data["rejected"] == 0

    def test_selected_vs_rejected_all_keys(self, patch_db_settings):
        from milestone4.recruitment_analytics import _q_selected_vs_rejected
        data = _q_selected_vs_rejected("")
        assert set(data.keys()) == {"selected", "rejected", "active"}
