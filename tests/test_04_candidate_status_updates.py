"""
Tests — Module 4: Candidate Status Updates
Covers: _stage_only, _ats_upsert, update_candidate, delete_candidate,
        invalid stage, missing candidate, DB error handling.
"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import TEST_DB_NAME, _raw_conn


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_ats_row(candidate_id: int) -> dict | None:
    with _raw_conn(TEST_DB_NAME) as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM ats_candidates WHERE candidate_id=%s AND job_id IS NULL",
            (candidate_id,),
        )
        row = cur.fetchone()
        cur.close()
    return row


# ── ATS stage helpers ──────────────────────────────────────────────────────

class TestStageOnly:

    def test_insert_when_no_row_exists(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _stage_only
        cid = sample_candidate["candidate_id"]
        _stage_only(cid, "Screening")
        row = _get_ats_row(cid)
        assert row is not None
        assert row["stage"] == "Screening"

    def test_update_existing_row(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _stage_only
        cid = sample_candidate["candidate_id"]
        _stage_only(cid, "Applied")
        _stage_only(cid, "Interview")
        row = _get_ats_row(cid)
        assert row["stage"] == "Interview"

    def test_all_valid_stages(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _stage_only, _STAGES
        cid = sample_candidate["candidate_id"]
        for stage in _STAGES:
            _stage_only(cid, stage)
            row = _get_ats_row(cid)
            assert row["stage"] == stage

    def test_nonexistent_candidate_raises(self, patch_db_settings):
        """FK constraint: inserting for a non-existent candidate_id must raise."""
        from milestone3.ats_management_page import _stage_only
        import mysql.connector
        with pytest.raises(mysql.connector.Error):
            _stage_only(999999, "Applied")


class TestAtsUpsert:

    def test_upsert_creates_row(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        ats_id = _ats_upsert(cid, "Applied", "rec@test.com", 75.0)
        assert ats_id > 0
        row = _get_ats_row(cid)
        assert row["resume_score"] == pytest.approx(75.0)
        assert row["recruiter"] == "rec@test.com"

    def test_upsert_updates_existing_row(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        _ats_upsert(cid, "Applied", "rec@test.com", 50.0)
        _ats_upsert(cid, "Selected", "rec@test.com", 90.0)
        row = _get_ats_row(cid)
        assert row["stage"] == "Selected"
        assert row["resume_score"] == pytest.approx(90.0)

    def test_upsert_returns_ats_id(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        ats_id = _ats_upsert(cid, "Applied")
        assert isinstance(ats_id, int)
        assert ats_id > 0

    def test_upsert_zero_score(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        ats_id = _ats_upsert(cid, "Applied", "", 0.0)
        assert ats_id > 0

    def test_upsert_max_score(self, patch_db_settings, sample_candidate):
        from milestone3.ats_management_page import _ats_upsert
        cid = sample_candidate["candidate_id"]
        ats_id = _ats_upsert(cid, "Selected", "rec@test.com", 100.0)
        row = _get_ats_row(cid)
        assert row["resume_score"] == pytest.approx(100.0)


# ── DatabaseManager.update_candidate ──────────────────────────────────────

class TestUpdateCandidate:

    def test_update_valid_field(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        result = db.update_candidate(cid, {"phone": "8888888888"})
        assert result is True
        updated = db.get_candidate_by_id(cid)
        assert updated["phone"] == "8888888888"

    def test_update_multiple_fields(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        result = db.update_candidate(cid, {"phone": "7777777777", "skills": "python, fastapi"})
        assert result is True
        updated = db.get_candidate_by_id(cid)
        assert updated["skills"] == "python, fastapi"

    def test_update_nonexistent_candidate(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.update_candidate(999999, {"phone": "1234567890"})
        assert result is False

    def test_update_disallowed_field_ignored(self, patch_db_settings, sample_candidate):
        """Fields not in the allowed set must be silently ignored."""
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        # candidate_id is not in the allowed set — should return False (no valid fields)
        result = db.update_candidate(cid, {"candidate_id": 9999})
        assert result is False

    def test_update_empty_dict(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.update_candidate(sample_candidate["candidate_id"], {})
        assert result is False


# ── DatabaseManager.delete_candidate ──────────────────────────────────────

class TestDeleteCandidate:

    def test_delete_existing_candidate(self, patch_db_settings, sample_candidate):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        result = db.delete_candidate(cid)
        assert result is True
        assert db.get_candidate_by_id(cid) is None

    def test_delete_nonexistent_candidate(self, patch_db_settings):
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        result = db.delete_candidate(999999)
        assert result is False

    def test_delete_cascades_ats_row(self, patch_db_settings, sample_candidate):
        """Deleting a candidate must cascade-delete their ats_candidates row."""
        from database.db_manager import DatabaseManager
        from milestone3.ats_management_page import _stage_only
        db = DatabaseManager()
        cid = sample_candidate["candidate_id"]
        _stage_only(cid, "Applied")
        db.delete_candidate(cid)
        row = _get_ats_row(cid)
        assert row is None
