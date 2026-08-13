"""
Tests — Module 16: Complete Recruitment Workflow (Integration)

End-to-end pipeline:
  Candidate data → Job → Matching → Hiring score → Interview →
  Voice screening → Evaluation → Candidate status → Dashboard analytics

Tests both the happy path and failure/edge cases at each stage transition.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import TEST_DB_NAME, _raw_conn, make_wav_bytes


# ── Shared mock evaluation response ───────────────────────────────────────

_MOCK_EVAL = (
    "TECHNICAL: 80\nTECHNICAL_WHY: Good.\n"
    "COMMUNICATION: 75\nCOMMUNICATION_WHY: Clear.\n"
    "CONFIDENCE: 70\nCONFIDENCE_WHY: Steady.\n"
    "PROBLEM_SOLVING: 78\nPROBLEM_SOLVING_WHY: Logical.\n"
    "GRAMMAR: 82\nGRAMMAR_WHY: Correct.\n"
    "OVERALL: 77\nLEVEL: Good\n"
    "FEEDBACK: Solid answer.\n"
    "IMPROVEMENT1: More examples.\nIMPROVEMENT2: Be concise.\nIMPROVEMENT3: Use terms."
)

_MOCK_QUESTION = "Tell me about your experience with Python."


def _mock_groq(monkeypatch):
    """Patch Groq so no real API calls are made."""
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=_MOCK_EVAL))]
    )
    monkeypatch.setattr("milestone3.interview_simulator._GROQ", mock)
    monkeypatch.setattr("milestone3.interview_simulator._use_gemini", lambda: False)
    return mock


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 1 — Candidate data ingestion
# ══════════════════════════════════════════════════════════════════════════

class TestStage1CandidateIngestion:

    def test_candidate_created_in_db(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = db.create_candidate({
            "name": "Integration Candidate",
            "email": "integ@test.com",
            "phone": "9000000001",
            "education": "B.Tech",
            "skills": "python, django, mysql",
            "experience": "3 years",
            "projects": "Portal",
            "certifications": "AWS",
            "resume_path": "uploads/integ.pdf",
            "recruiter_email": "rec@test.com",
        })
        assert cid > 0
        candidate = db.get_candidate_by_id(cid)
        assert candidate["email"] == "integ@test.com"

    def test_duplicate_email_upserts(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        db.create_candidate({
            "name": "Dup Cand", "email": "dup@test.com", "phone": "",
            "education": "", "skills": "python", "experience": "",
            "projects": "", "certifications": "", "resume_path": "",
            "recruiter_email": "r@r.com",
        })
        # upsert with same email — updates existing row
        db.upsert_candidate({
            "name": "Dup Cand Updated", "email": "dup@test.com", "phone": "1111",
            "education": "B.Tech", "skills": "python, django", "experience": "2 years",
            "projects": "", "certifications": "", "resume_path": "",
        })
        # verify the update took effect regardless of returned ID
        updated = db.get_candidate_by_email("dup@test.com")
        assert updated is not None
        assert updated["skills"] == "python, django"


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 2 — Job creation
# ══════════════════════════════════════════════════════════════════════════

class TestStage2JobCreation:

    def test_job_created_in_db(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        jid = db.create_job({
            "job_title": "Integration Engineer",
            "department": "Engineering",
            "location": "Remote",
            "job_type": "Full-Time",
            "experience_level": "Mid-Level",
            "salary_min": 700000,
            "salary_max": 1100000,
            "description": "Build integrations",
            "requirements": "B.Tech",
            "responsibilities": "Design APIs",
            "skills_required": "python, django, mysql",
            "benefits": "Health",
            "certification": "AWS",
            "status": "Open",
            "openings": 1,
            "posted_by": "rec@test.com",
            "deadline": "2025-12-31",
            "recruiter_email": "rec@test.com",
        })
        assert jid > 0
        job = db.get_job_by_id(jid)
        assert job["job_title"] == "Integration Engineer"


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 3 — Matching
# ══════════════════════════════════════════════════════════════════════════

class TestStage3Matching:

    def test_skill_match_computed(self, patch_db_settings, sample_candidate, sample_job):
        from matching_engine import normalize_skills, compare_skills, calculate_overall_score
        resume_skills = normalize_skills(sample_candidate["skills"])
        jd_skills     = normalize_skills(sample_job["skills_required"])
        skill_result  = compare_skills(resume_skills, jd_skills)
        assert skill_result["match_percentage"] > 0

    def test_overall_score_computed(self, patch_db_settings, sample_candidate, sample_job):
        from matching_engine import (
            normalize_skills, compare_skills, compare_experience,
            compare_education, compare_certifications, calculate_overall_score,
        )
        rs = normalize_skills(sample_candidate["skills"])
        js = normalize_skills(sample_job["skills_required"])
        sr = compare_skills(rs, js)
        er = compare_experience(sample_candidate["experience"], sample_job["experience_level"])
        edu = compare_education(sample_candidate["education"], sample_job.get("requirements", ""))
        cr = compare_certifications(sample_candidate["certifications"],
                                     sample_job.get("certification", ""))
        score = calculate_overall_score(sr["match_percentage"], er["meets_experience"],
                                         edu["meets_education"], cr["certification_matched"])
        assert 0 <= score["overall_score"] <= 100
        assert score["grade"] in ("A", "B", "C", "D")


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 4 — Hiring score stored in ATS
# ══════════════════════════════════════════════════════════════════════════

class TestStage4HiringScore:

    def test_ats_upsert_stores_score(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        ats_id = _ats_upsert(cid, "Screening", "rec@test.com", 72.5)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT resume_score FROM ats_candidates WHERE ats_id=%s", (ats_id,))
            row = cur.fetchone()
            cur.close()
        assert row["resume_score"] == pytest.approx(72.5)


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 5 — AI Interview
# ══════════════════════════════════════════════════════════════════════════

class TestStage5AIInterview:

    def test_question_generated(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_simulator import _generate_question
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=_MOCK_QUESTION))]
            )
            q = _generate_question(sample_candidate, sample_job, [], 1)
        assert isinstance(q, str)
        assert len(q) > 0

    def test_answer_evaluated(self, patch_db_settings):
        from milestone3.interview_simulator import _evaluate
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=_MOCK_EVAL))]
            )
            ev = _evaluate("What is Python?", "A high-level language.", "Python Developer")
        assert ev["score"] == 77
        assert ev["level"] == "Good"

    def test_report_saved(self, patch_db_settings, sample_candidate, sample_job):
        from milestone3.interview_db import init_db, save_report, load_session_by_id
        init_db()
        report = {
            "candidate": sample_candidate,
            "job": sample_job,
            "answers": [{"question": "Q1", "answer": "A1",
                          "evaluation": {"score": 77, "level": "Good", "feedback": "OK",
                                         "technical": 80, "communication": 75,
                                         "confidence": 70, "problem_solving": 78,
                                         "grammar": 82, "improvements": []}}],
            "avg_score": 77.0,
            "verdict": "Good Effort 👍",
        }
        sid = save_report(report)
        loaded = load_session_by_id(sid)
        assert loaded["avg_score"] == pytest.approx(77.0)


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 6 — Voice Screening
# ══════════════════════════════════════════════════════════════════════════

class TestStage6VoiceScreening:

    def test_voice_answer_saved_and_linked(self, tmp_path, patch_db_settings,
                                            sample_candidate, sample_job, sample_session):
        from milestone4.voice_screening import (
            _init_voice_table, _save_audio_file, _save_answer, _backfill_session_id,
        )
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        audio = make_wav_bytes()

        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            audio_path = _save_audio_file(audio, cid, 0)

        ev = {"score": 70, "level": "Good", "feedback": "OK",
              "technical": 70, "communication": 68, "confidence": 72,
              "problem_solving": 65, "grammar": 75, "improvements": []}
        _save_answer(cid, jid, 0, "Q1", audio_path, "My answer", ev)
        _backfill_session_id(cid, jid, sample_session)

        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM voice_screening_answers WHERE candidate_id=%s", (cid,)
            )
            rows = cur.fetchall()
            cur.close()
        assert len(rows) == 1
        assert rows[0]["session_id"] == sample_session
        assert rows[0]["transcript"] == "My answer"

    def test_transcription_failure_graceful(self, patch_db_settings):
        """If transcription fails, the workflow continues with empty transcript."""
        import speech_recognition as sr
        from milestone4.voice_screening import _transcribe
        with patch("speech_recognition.Recognizer.recognize_google",
                   side_effect=sr.RequestError("network")):
            result = _transcribe(make_wav_bytes())
        assert result == ""


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 7 — Candidate status update after evaluation
# ══════════════════════════════════════════════════════════════════════════

class TestStage7StatusUpdate:

    def test_stage_progresses_through_pipeline(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _stage_only
        cid = sample_candidate["candidate_id"]
        for stage in ["Applied", "Screening", "Interview", "Selected"]:
            _stage_only(cid, stage)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT stage FROM ats_candidates WHERE candidate_id=%s AND job_id IS NULL",
                (cid,),
            )
            row = cur.fetchone()
            cur.close()
        assert row[0] == "Selected"

    def test_rejected_status_stored(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _stage_only
        cid = sample_candidate["candidate_id"]
        _stage_only(cid, "Rejected")
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT stage FROM ats_candidates WHERE candidate_id=%s AND job_id IS NULL",
                (cid,),
            )
            row = cur.fetchone()
            cur.close()
        assert row[0] == "Rejected"


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 8 — Dashboard analytics reflect full pipeline
# ══════════════════════════════════════════════════════════════════════════

class TestStage8DashboardAnalytics:

    def test_summary_reflects_full_pipeline(self, patch_db_settings,
                                              sample_candidate, sample_session):
        from milestone3.ats_management_page import _ats_upsert
        from milestone4.recruitment_analytics import _load_summary
        cid = sample_candidate["candidate_id"]
        _ats_upsert(cid, "Selected", "rec@test.com", 85.0)
        summary = _load_summary("")
        assert summary["total"] >= 1
        assert summary["selected"] >= 1
        assert summary["sessions"] >= 1

    def test_stage_distribution_includes_selected(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        from milestone4.recruitment_analytics import _q_stage_distribution
        cid = sample_candidate["candidate_id"]
        _ats_upsert(cid, "Selected", "rec@test.com", 90.0)
        rows = _q_stage_distribution("")
        assert any(r["stage"] == "Selected" for r in rows)

    def test_interview_performance_includes_session(self, patch_db_settings, sample_session):
        from milestone4.recruitment_analytics import _q_interview_performance
        rows = _q_interview_performance("")
        assert len(rows) >= 1
        assert any(r["avg_score"] > 0 for r in rows)


# ══════════════════════════════════════════════════════════════════════════
#  EDGE CASES — across the full workflow
# ══════════════════════════════════════════════════════════════════════════

class TestWorkflowEdgeCases:

    def test_workflow_with_no_skills_match(self, patch_db_settings):
        """Candidate with no matching skills still gets a valid score (0%)."""
        from matching_engine import normalize_skills, compare_skills, calculate_overall_score
        rs = normalize_skills("cobol, fortran")
        js = normalize_skills("python, django, react")
        sr = compare_skills(rs, js)
        score = calculate_overall_score(sr["match_percentage"], False, False, False)
        assert score["overall_score"] == 0.0
        assert score["grade"] == "D"

    def test_workflow_candidate_not_found_graceful(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.get_candidate_by_id(999999)
        assert result is None

    def test_workflow_job_not_found_graceful(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.get_job_by_id(999999)
        assert result is None

    def test_workflow_empty_answer_evaluation(self):
        from milestone3.interview_simulator import _evaluate
        result = _evaluate("What is Python?", "", "Python Developer")
        assert result["score"] == 0
        assert result["level"] == "No Answer"

    def test_workflow_voice_transcription_failure_continues(self):
        """Voice transcription failure must not break the workflow."""
        import speech_recognition as sr
        from milestone4.voice_screening import _transcribe
        with patch("speech_recognition.Recognizer.recognize_google",
                   side_effect=Exception("unexpected error")):
            result = _transcribe(make_wav_bytes())
        assert result == ""

    def test_workflow_report_with_empty_answers(self, patch_db_settings):
        from milestone3.interview_db import init_db, save_report, load_session_by_id
        init_db()
        report = {
            "candidate": {"candidate_id": 0, "name": "Ghost"},
            "job": {"job_id": 0, "job_title": "Unknown"},
            "answers": [],
            "avg_score": 0.0,
            "verdict": "Needs More Preparation 📚",
        }
        sid = save_report(report)
        loaded = load_session_by_id(sid)
        assert loaded["answers"] == []

    def test_workflow_ats_schema_ready_before_operations(self, patch_db_settings):
        """ATS schema must be initialised before any ATS operation."""
        import database.ats_schema as ats_mod
        ats_mod._schema_initialized = False
        ats_mod.init_ats_schema()
        assert ats_mod._schema_initialized is True

    def test_workflow_multiple_candidates_same_job(self, patch_db_settings, sample_job):
        """Multiple candidates can be matched to the same job without conflict."""
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        emails = [f"cand{i}@test.com" for i in range(3)]
        cids = []
        for email in emails:
            cid = db.create_candidate({
                "name": f"Cand {email}", "email": email, "phone": "",
                "education": "B.Tech", "skills": "python", "experience": "2 years",
                "projects": "", "certifications": "", "resume_path": "",
                "recruiter_email": "r@r.com",
            })
            cids.append(cid)
        assert len(set(cids)) == 3   # all unique IDs
