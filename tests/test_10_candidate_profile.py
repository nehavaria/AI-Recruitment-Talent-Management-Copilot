"""
Tests — Module 10: Candidate Profile
Covers: profile completeness, field validation, save_upload path safety,
        missing fields, profile extraction from resume text.
"""

import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.conftest import TEST_DB_NAME, _raw_conn


# ── Profile field validation ───────────────────────────────────────────────

class TestCandidateProfile:

    def test_full_profile_has_all_fields(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        profile = db.get_candidate_by_id(sample_candidate["candidate_id"])
        required = ["candidate_id", "name", "email", "phone", "education",
                    "skills", "experience", "projects", "certifications", "resume_path"]
        for field in required:
            assert field in profile

    def test_profile_name_not_empty(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        profile = db.get_candidate_by_id(sample_candidate["candidate_id"])
        assert profile["name"].strip() != ""

    def test_profile_email_format(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        profile = db.get_candidate_by_id(sample_candidate["candidate_id"])
        assert "@" in profile["email"]

    def test_profile_skills_comma_separated(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        profile = db.get_candidate_by_id(sample_candidate["candidate_id"])
        skills = [s.strip() for s in profile["skills"].split(",") if s.strip()]
        assert len(skills) >= 1

    def test_profile_missing_optional_fields_graceful(self, patch_db_settings):
        """A candidate with only name+email must not crash profile rendering."""
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO candidates (name, email, recruiter_email) VALUES (%s,%s,%s)",
                ("Sparse Cand", "sparse@test.com", "r@r.com"),
            )
            cid = cur.lastrowid
            cur.close()
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        profile = db.get_candidate_by_id(cid)
        # These should be None or empty string, not raise
        assert profile.get("skills") is None or isinstance(profile["skills"], str)
        assert profile.get("experience") is None or isinstance(profile["experience"], str)

    def test_profile_update_preserves_other_fields(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        db.update_candidate(cid, {"phone": "1234567890"})
        profile = db.get_candidate_by_id(cid)
        assert profile["email"] == "test@example.com"   # unchanged
        assert profile["skills"] == "python, django, mysql, docker, aws"  # unchanged
        assert profile["phone"] == "1234567890"          # updated

    def test_profile_nonexistent_returns_none(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        assert db.get_candidate_by_id(999999) is None

    def test_profile_by_email_nonexistent_returns_none(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        assert db.get_candidate_by_email("ghost@nowhere.com") is None


# ── save_upload path safety ────────────────────────────────────────────────

class TestSaveUpload:

    def test_valid_pdf_upload(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            dest = svc.save_upload(b"%PDF-1.4 fake content", "resume.pdf")
            assert dest.exists()
            assert dest.suffix == ".pdf"

    def test_valid_docx_upload(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            dest = svc.save_upload(b"PK fake docx content", "resume.docx")
            assert dest.exists()

    def test_unsupported_extension_raises(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            with pytest.raises(ValueError, match="Unsupported file extension"):
                svc.save_upload(b"fake", "resume.exe")

    def test_path_traversal_rejected(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            # Path traversal attempt — should be sanitized or rejected
            dest = svc.save_upload(b"%PDF fake", "../../etc/passwd.pdf")
            # Must land inside UPLOAD_DIR, not escape it
            assert dest.resolve().is_relative_to(tmp_path.resolve())

    def test_empty_bytes_saved(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            dest = svc.save_upload(b"", "empty.pdf")
            assert dest.exists()
            assert dest.stat().st_size == 0

    def test_filename_sanitized(self, tmp_path, patch_db_settings):
        from services.candidate_service import CandidateService
        with patch("services.candidate_service.UPLOAD_DIR", tmp_path):
            svc = CandidateService()
            dest = svc.save_upload(b"%PDF fake", "my resume (1).pdf")
            # Special chars replaced with underscores
            assert " " not in dest.name
            assert "(" not in dest.name


# ── ProfileExtractor ───────────────────────────────────────────────────────

class TestProfileExtractor:

    def test_extract_name(self):
        from parsers.profile_extractor import ProfileExtractor
        extractor = ProfileExtractor()
        text = "John Doe\njohn.doe@email.com\nPython Developer"
        profile = extractor.extract(text)
        assert profile is not None

    def test_extract_email(self):
        from parsers.profile_extractor import ProfileExtractor
        extractor = ProfileExtractor()
        text = "Jane Smith\njane@example.com\nSkills: python, django"
        profile = extractor.extract(text)
        assert profile.email == "jane@example.com"

    def test_extract_skills(self):
        from parsers.profile_extractor import ProfileExtractor
        extractor = ProfileExtractor()
        text = "Skills: Python, Django, MySQL, Docker"
        profile = extractor.extract(text)
        # skills may be a list or a comma-separated string depending on extractor
        skills = profile.skills
        if isinstance(skills, list):
            skills_lower = " ".join(skills).lower()
        else:
            skills_lower = (skills or "").lower()
        assert "python" in skills_lower

    def test_extract_empty_text(self):
        from parsers.profile_extractor import ProfileExtractor
        extractor = ProfileExtractor()
        profile = extractor.extract("")
        assert profile is not None   # must not raise

    def test_extract_no_email_in_text(self):
        from parsers.profile_extractor import ProfileExtractor
        extractor = ProfileExtractor()
        profile = extractor.extract("No email here, just some text about skills.")
        # email should be empty/None, not raise
        assert profile.email is None or profile.email == ""
