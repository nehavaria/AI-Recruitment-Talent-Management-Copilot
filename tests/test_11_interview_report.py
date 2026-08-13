"""
Tests — Module 11: Interview Report
Covers: save_report, load_latest_report, load_all_sessions,
        load_session_by_id, delete_session — valid data, empty data,
        malformed JSON, missing fields.
"""

import json
import pytest
from tests.conftest import TEST_DB_NAME, _raw_conn


def _make_report(candidate_id=1, job_id=1, avg_score=75.0, verdict="Good Effort 👍"):
    return {
        "candidate": {"candidate_id": candidate_id, "name": "Test Candidate",
                      "email": "test@example.com"},
        "job":       {"job_id": job_id, "job_title": "Python Developer"},
        "answers": [
            {"question": "What is Python?",
             "answer": "A high-level language.",
             "evaluation": {"score": 75, "level": "Good", "feedback": "Decent.",
                            "technical": 70, "communication": 75, "confidence": 72,
                            "problem_solving": 78, "grammar": 80, "improvements": []}}
        ],
        "avg_score": avg_score,
        "verdict":   verdict,
    }


class TestInterviewReport:

    # ── save_report ────────────────────────────────────────────────────────

    def test_save_report_returns_int(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = _make_report(sample_candidate["candidate_id"], sample_job["job_id"])
        sid = save_report(report)
        assert isinstance(sid, int)
        assert sid > 0

    def test_save_report_persists_to_db(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = _make_report(sample_candidate["candidate_id"], sample_job["job_id"], 80.0)
        sid = save_report(report)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM interview_sessions WHERE session_id=%s", (sid,))
            row = cur.fetchone()
            cur.close()
        assert row is not None
        assert row["avg_score"] == pytest.approx(80.0)
        assert row["verdict"] == "Good Effort 👍"

    def test_save_report_stores_valid_json(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = _make_report(sample_candidate["candidate_id"], sample_job["job_id"])
        sid = save_report(report)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT report_json FROM interview_sessions WHERE session_id=%s", (sid,))
            row = cur.fetchone()
            cur.close()
        parsed = json.loads(row[0])
        assert "answers" in parsed
        assert "avg_score" in parsed

    def test_save_report_missing_candidate_defaults(self, patch_db_settings):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = {"answers": [], "avg_score": 0, "verdict": ""}
        sid = save_report(report)
        assert sid > 0   # must not raise

    def test_save_report_zero_score(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = _make_report(sample_candidate["candidate_id"], sample_job["job_id"],
                               avg_score=0.0, verdict="Needs More Preparation 📚")
        sid = save_report(report)
        assert sid > 0

    def test_save_report_max_score(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report
        init_db()
        report = _make_report(sample_candidate["candidate_id"], sample_job["job_id"],
                               avg_score=100.0, verdict="Strong Performance 🎉")
        sid = save_report(report)
        assert sid > 0

    # ── load_latest_report ─────────────────────────────────────────────────

    def test_load_latest_returns_dict(self, patch_db_settings, sample_session):
        from milestone3.interview_db import load_latest_report
        report = load_latest_report()
        assert isinstance(report, dict)
        assert "answers" in report

    def test_load_latest_by_candidate(self, patch_db_settings, sample_candidate, sample_session):
        from milestone3.interview_db import load_latest_report
        report = load_latest_report(sample_candidate["candidate_id"])
        assert report is not None
        assert report["candidate"]["candidate_id"] == sample_candidate["candidate_id"]

    def test_load_latest_empty_db(self, patch_db_settings):
        from milestone3.interview_db import init_db, load_latest_report
        init_db()
        result = load_latest_report()
        assert result is None

    def test_load_latest_nonexistent_candidate(self, patch_db_settings, sample_session):
        from milestone3.interview_db import load_latest_report
        result = load_latest_report(999999)
        assert result is None

    # ── load_all_sessions ──────────────────────────────────────────────────

    def test_load_all_sessions_returns_list(self, patch_db_settings, sample_session):
        from milestone3.interview_db import load_all_sessions
        sessions = load_all_sessions()
        assert isinstance(sessions, list)
        assert len(sessions) >= 1

    def test_load_all_sessions_empty(self, patch_db_settings):
        from milestone3.interview_db import init_db, load_all_sessions
        init_db()
        sessions = load_all_sessions()
        assert sessions == []

    def test_load_all_sessions_has_required_keys(self, patch_db_settings, sample_session):
        from milestone3.interview_db import load_all_sessions
        sessions = load_all_sessions()
        row = sessions[0]
        for key in ("session_id", "candidate_name", "job_title", "avg_score",
                    "verdict", "created_at"):
            assert key in row

    # ── load_session_by_id ─────────────────────────────────────────────────

    def test_load_session_by_id_valid(self, patch_db_settings, sample_session):
        from milestone3.interview_db import load_session_by_id
        report = load_session_by_id(sample_session)
        assert report is not None
        assert "answers" in report

    def test_load_session_by_id_nonexistent(self, patch_db_settings):
        from milestone3.interview_db import init_db, load_session_by_id
        init_db()
        result = load_session_by_id(999999)
        assert result is None

    # ── delete_session ─────────────────────────────────────────────────────

    def test_delete_session_removes_row(self, patch_db_settings, sample_session):
        from milestone3.interview_db import delete_session, load_session_by_id
        delete_session(sample_session)
        result = load_session_by_id(sample_session)
        assert result is None

    def test_delete_nonexistent_session_no_raise(self, patch_db_settings):
        from milestone3.interview_db import init_db, delete_session
        init_db()
        delete_session(999999)   # must not raise

    # ── multiple sessions ordering ─────────────────────────────────────────

    def test_load_latest_returns_most_recent(self, patch_db_settings,
                                              sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report, load_latest_report
        init_db()
        save_report(_make_report(sample_candidate["candidate_id"],
                                  sample_job["job_id"], 50.0))
        save_report(_make_report(sample_candidate["candidate_id"],
                                  sample_job["job_id"], 95.0, "Strong Performance 🎉"))
        report = load_latest_report(sample_candidate["candidate_id"])
        assert report["avg_score"] == pytest.approx(95.0)
