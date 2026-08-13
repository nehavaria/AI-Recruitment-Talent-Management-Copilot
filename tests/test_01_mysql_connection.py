"""
Tests — Module 1: MySQL Connection
Covers: valid connection, wrong credentials, wrong host, wrong database,
        connection context-manager commit/rollback, schema initialisation.
"""

import pytest
import mysql.connector
from unittest.mock import patch, MagicMock

from tests.conftest import TEST_DB_CFG, TEST_DB_NAME, _raw_conn


# ── 1. Valid connection ────────────────────────────────────────────────────

class TestMySQLConnection:

    def test_connect_valid_credentials(self, test_db):
        """A connection with correct credentials succeeds and is usable."""
        with _raw_conn(TEST_DB_NAME) as conn:
            assert conn.is_connected()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            row = cur.fetchone()
            cur.close()
        assert row == (1,)

    def test_connect_wrong_password_raises(self, test_db):
        """Wrong password raises mysql.connector.Error."""
        cfg = dict(TEST_DB_CFG, database=TEST_DB_NAME, password="WRONG_PASSWORD")
        with pytest.raises(mysql.connector.Error):
            mysql.connector.connect(**cfg)

    def test_connect_wrong_host_raises(self, test_db):
        """Unreachable host raises mysql.connector.Error."""
        cfg = dict(TEST_DB_CFG, database=TEST_DB_NAME, host="192.0.2.1", connect_timeout=2)
        with pytest.raises(mysql.connector.Error):
            mysql.connector.connect(**cfg)

    def test_connect_wrong_database_raises(self, test_db):
        """Non-existent database raises mysql.connector.Error."""
        cfg = dict(TEST_DB_CFG, database="db_does_not_exist_xyz")
        with pytest.raises(mysql.connector.Error):
            mysql.connector.connect(**cfg)

    def test_context_manager_commits_on_success(self, clean_db):
        """_raw_conn commits when no exception is raised."""
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO candidates (name, email, recruiter_email) VALUES (%s,%s,%s)",
                ("CM Test", "cm@test.com", "r@r.com"),
            )
            cur.close()

        # Verify row persisted
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM candidates WHERE email='cm@test.com'")
            count = cur.fetchone()[0]
            cur.close()
        assert count == 1

    def test_context_manager_rolls_back_on_exception(self, clean_db):
        """_raw_conn rolls back when an exception is raised inside the block."""
        try:
            with _raw_conn(TEST_DB_NAME) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO candidates (name, email, recruiter_email) VALUES (%s,%s,%s)",
                    ("Rollback Test", "rb@test.com", "r@r.com"),
                )
                cur.close()
                raise RuntimeError("forced rollback")
        except RuntimeError:
            pass

        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM candidates WHERE email='rb@test.com'")
            count = cur.fetchone()[0]
            cur.close()
        assert count == 0

    def test_db_manager_init_schema(self, patch_db_settings):
        """DatabaseManager.__init__ creates candidates and jobs tables without error."""
        from database.db_manager import DatabaseManager
        dm = DatabaseManager()
        assert dm is not None

    def test_ats_schema_init(self, patch_db_settings):
        """init_ats_schema() creates all 4 ATS tables without error."""
        import database.ats_schema as ats_mod
        ats_mod._schema_initialized = False   # reset guard for test isolation
        ats_mod.init_ats_schema()
        assert ats_mod._schema_initialized is True

    def test_ats_schema_init_idempotent(self, patch_db_settings):
        """Calling init_ats_schema() twice does not raise."""
        import database.ats_schema as ats_mod
        ats_mod._schema_initialized = False
        ats_mod.init_ats_schema()
        ats_mod.init_ats_schema()   # second call — must be a no-op
        assert ats_mod._schema_initialized is True

    def test_interview_db_init(self, patch_db_settings):
        """init_db() creates interview_sessions table without error."""
        from milestone3.interview_db import init_db
        init_db()   # should not raise

    def test_voice_table_init(self, patch_db_settings):
        """_init_voice_table() creates voice_screening_answers without error."""
        from milestone4.voice_screening import _init_voice_table
        _init_voice_table()   # should not raise
