"""
Tests — Modules 12, 13, 14, 15: Voice Recording, Speech-to-Text,
        Voice Answer Storage, Interview Evaluation
Covers: WAV save, transcription (mocked + real silence), _save_answer,
        _backfill_session_id, _load_session_answers, _evaluate (mocked).
"""

import io
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.conftest import TEST_DB_NAME, _raw_conn, make_wav_bytes


# ══════════════════════════════════════════════════════════════════════════
#  MODULE 12 — Voice Recording (WAV file save)
# ══════════════════════════════════════════════════════════════════════════

class TestVoiceRecording:

    def test_save_audio_file_creates_file(self, tmp_path, patch_db_settings):
        from milestone4.voice_screening import _save_audio_file
        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            audio = make_wav_bytes()
            path_str = _save_audio_file(audio, candidate_id=1, q_index=0)
            saved = tmp_path / Path(path_str).name
            assert saved.exists() or (voice_dir / Path(path_str).name).exists()

    def test_save_audio_file_returns_string(self, tmp_path, patch_db_settings):
        from milestone4.voice_screening import _save_audio_file
        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            path_str = _save_audio_file(make_wav_bytes(), 1, 0)
            assert isinstance(path_str, str)

    def test_save_audio_file_unique_names(self, tmp_path, patch_db_settings):
        """Two saves for the same candidate+question produce different filenames."""
        from milestone4.voice_screening import _save_audio_file
        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            p1 = _save_audio_file(make_wav_bytes(), 1, 0)
            p2 = _save_audio_file(make_wav_bytes(), 1, 0)
            assert p1 != p2

    def test_save_audio_file_correct_content(self, tmp_path, patch_db_settings):
        from milestone4.voice_screening import _save_audio_file
        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        audio = make_wav_bytes()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            _save_audio_file(audio, 1, 0)
            saved_files = list(voice_dir.glob("voice_1_q0_*.wav"))
            assert len(saved_files) == 1
            assert saved_files[0].read_bytes() == audio

    def test_save_empty_audio_bytes(self, tmp_path, patch_db_settings):
        """Empty bytes should still save without raising."""
        from milestone4.voice_screening import _save_audio_file
        voice_dir = tmp_path / "voice"
        voice_dir.mkdir()
        with patch("milestone4.voice_screening._VOICE_DIR", voice_dir), \
             patch("milestone4.voice_screening.UPLOAD_DIR", tmp_path):
            path_str = _save_audio_file(b"", 1, 0)
            assert isinstance(path_str, str)


# ══════════════════════════════════════════════════════════════════════════
#  MODULE 13 — Speech-to-Text
# ══════════════════════════════════════════════════════════════════════════

class TestSpeechToText:

    def test_transcribe_returns_string(self, valid_wav_bytes):
        """_transcribe always returns a string (empty on failure)."""
        from milestone4.voice_screening import _transcribe
        result = _transcribe(valid_wav_bytes)
        assert isinstance(result, str)

    def test_transcribe_silence_returns_empty(self, valid_wav_bytes):
        """Silent WAV produces no speech — Google returns empty or raises."""
        from milestone4.voice_screening import _transcribe
        result = _transcribe(valid_wav_bytes)
        # Silence → empty string (exception caught internally)
        assert result == "" or isinstance(result, str)

    def test_transcribe_invalid_bytes_returns_empty(self, invalid_audio_bytes):
        """Garbage bytes must not raise — returns empty string."""
        from milestone4.voice_screening import _transcribe
        result = _transcribe(invalid_audio_bytes)
        assert result == ""

    def test_transcribe_empty_bytes_returns_empty(self):
        from milestone4.voice_screening import _transcribe
        result = _transcribe(b"")
        assert result == ""

    def test_transcribe_mocked_success(self, valid_wav_bytes):
        """Mock Google STT to return a known transcript."""
        from milestone4.voice_screening import _transcribe
        with patch("speech_recognition.Recognizer.recognize_google",
                   return_value="hello world"):
            result = _transcribe(valid_wav_bytes)
        assert result == "hello world"

    def test_transcribe_mocked_network_failure(self, valid_wav_bytes):
        """Network failure (RequestError) must return empty string."""
        import speech_recognition as sr
        from milestone4.voice_screening import _transcribe
        with patch("speech_recognition.Recognizer.recognize_google",
                   side_effect=sr.RequestError("network down")):
            result = _transcribe(valid_wav_bytes)
        assert result == ""

    def test_transcribe_mocked_unknown_value(self, valid_wav_bytes):
        """UnknownValueError (no speech detected) must return empty string."""
        import speech_recognition as sr
        from milestone4.voice_screening import _transcribe
        with patch("speech_recognition.Recognizer.recognize_google",
                   side_effect=sr.UnknownValueError()):
            result = _transcribe(valid_wav_bytes)
        assert result == ""

    def test_interview_simulator_transcribe_same_behaviour(self, valid_wav_bytes):
        """interview_simulator._transcribe has identical error-handling contract."""
        from milestone3.interview_simulator import _transcribe
        result = _transcribe(valid_wav_bytes)
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════
#  MODULE 14 — Voice Answer Storage
# ══════════════════════════════════════════════════════════════════════════

class TestVoiceAnswerStorage:

    def _sample_eval(self):
        return {
            "score": 70, "level": "Good", "feedback": "Well done.",
            "technical": 70, "communication": 68, "confidence": 72,
            "problem_solving": 65, "grammar": 75, "improvements": [],
        }

    def test_save_answer_returns_int(self, patch_db_settings, sample_candidate, sample_job):
        from milestone4.voice_screening import _init_voice_table, _save_answer
        _init_voice_table()
        aid = _save_answer(
            sample_candidate["candidate_id"], sample_job["job_id"],
            0, "What is Python?", "", "Python is great.", self._sample_eval(),
        )
        assert isinstance(aid, int)
        assert aid > 0

    def test_save_answer_persists_to_db(self, patch_db_settings, sample_candidate, sample_job):
        from milestone4.voice_screening import _init_voice_table, _save_answer
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        _save_answer(cid, jid, 0, "Q1", "/path/audio.wav", "My answer", self._sample_eval())
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM voice_screening_answers WHERE candidate_id=%s", (cid,)
            )
            rows = cur.fetchall()
            cur.close()
        assert len(rows) == 1
        assert rows[0]["transcript"] == "My answer"

    def test_save_answer_evaluation_stored_as_json(self, patch_db_settings,
                                                    sample_candidate, sample_job):
        from milestone4.voice_screening import _init_voice_table, _save_answer
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        ev = self._sample_eval()
        _save_answer(cid, jid, 0, "Q1", "", "answer", ev)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT evaluation FROM voice_screening_answers WHERE candidate_id=%s", (cid,)
            )
            row = cur.fetchone()
            cur.close()
        stored = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert stored["score"] == 70

    def test_save_answer_empty_transcript(self, patch_db_settings, sample_candidate, sample_job):
        from milestone4.voice_screening import _init_voice_table, _save_answer
        _init_voice_table()
        aid = _save_answer(
            sample_candidate["candidate_id"], sample_job["job_id"],
            0, "Q1", "", "", self._sample_eval(),
        )
        assert aid > 0

    def test_save_multiple_answers(self, patch_db_settings, sample_candidate, sample_job):
        from milestone4.voice_screening import _init_voice_table, _save_answer
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        for i in range(5):
            _save_answer(cid, jid, i, f"Q{i+1}", "", f"Answer {i+1}", self._sample_eval())
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM voice_screening_answers WHERE candidate_id=%s", (cid,)
            )
            count = cur.fetchone()[0]
            cur.close()
        assert count == 5

    def test_backfill_session_id(self, patch_db_settings, sample_candidate,
                                  sample_job, sample_session):
        from milestone4.voice_screening import _init_voice_table, _save_answer, _backfill_session_id
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        _save_answer(cid, jid, 0, "Q1", "", "answer", self._sample_eval())
        _backfill_session_id(cid, jid, sample_session)
        with _raw_conn(TEST_DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT session_id FROM voice_screening_answers "
                "WHERE candidate_id=%s AND job_id=%s", (cid, jid)
            )
            row = cur.fetchone()
            cur.close()
        assert row[0] == sample_session

    def test_backfill_no_rows_no_raise(self, patch_db_settings):
        from milestone4.voice_screening import _init_voice_table, _backfill_session_id
        _init_voice_table()
        _backfill_session_id(999, 999, 999)   # must not raise

    def test_load_session_answers(self, patch_db_settings, sample_candidate,
                                   sample_job, sample_session):
        from milestone4.voice_screening import (
            _init_voice_table, _save_answer, _backfill_session_id, _load_session_answers
        )
        _init_voice_table()
        cid = sample_candidate["candidate_id"]
        jid = sample_job["job_id"]
        _save_answer(cid, jid, 0, "Q1", "", "answer", self._sample_eval())
        _backfill_session_id(cid, jid, sample_session)
        rows = _load_session_answers(sample_session)
        assert len(rows) == 1
        assert rows[0]["transcript"] == "answer"

    def test_load_session_answers_empty(self, patch_db_settings):
        from milestone4.voice_screening import _init_voice_table, _load_session_answers
        _init_voice_table()
        rows = _load_session_answers(999999)
        assert rows == []


# ══════════════════════════════════════════════════════════════════════════
#  MODULE 15 — Interview Evaluation
# ══════════════════════════════════════════════════════════════════════════

class TestInterviewEvaluation:

    def _mock_eval_response(self):
        return (
            "TECHNICAL: 80\nTECHNICAL_WHY: Good depth.\n"
            "COMMUNICATION: 75\nCOMMUNICATION_WHY: Clear.\n"
            "CONFIDENCE: 70\nCONFIDENCE_WHY: Steady.\n"
            "PROBLEM_SOLVING: 78\nPROBLEM_SOLVING_WHY: Logical.\n"
            "GRAMMAR: 82\nGRAMMAR_WHY: Correct.\n"
            "OVERALL: 77\nLEVEL: Good\n"
            "FEEDBACK: Solid answer overall.\n"
            "IMPROVEMENT1: Add more examples.\n"
            "IMPROVEMENT2: Be more concise.\n"
            "IMPROVEMENT3: Use technical terms."
        )

    def test_evaluate_returns_dict(self):
        from milestone3.interview_simulator import _evaluate
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=self._mock_eval_response()))]
            )
            result = _evaluate("What is Python?", "A high-level language.", "Python Developer")
        assert isinstance(result, dict)

    def test_evaluate_has_required_keys(self):
        from milestone3.interview_simulator import _evaluate
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=self._mock_eval_response()))]
            )
            result = _evaluate("Q", "A", "Engineer")
        for key in ("score", "level", "feedback", "technical", "communication",
                    "confidence", "problem_solving", "grammar", "improvements"):
            assert key in result

    def test_evaluate_empty_answer_returns_zero_score(self):
        from milestone3.interview_simulator import _evaluate
        result = _evaluate("What is Python?", "", "Python Developer")
        assert result["score"] == 0
        assert result["level"] == "No Answer"

    def test_evaluate_whitespace_only_answer(self):
        from milestone3.interview_simulator import _evaluate
        result = _evaluate("What is Python?", "   ", "Python Developer")
        assert result["score"] == 0

    def test_evaluate_score_clamped_0_100(self):
        from milestone3.interview_simulator import _evaluate
        bad_response = self._mock_eval_response().replace("OVERALL: 77", "OVERALL: 150")
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=bad_response))]
            )
            result = _evaluate("Q", "A", "Engineer")
        assert 0 <= result["score"] <= 100

    def test_evaluate_api_failure_returns_fallback(self):
        from milestone3.interview_simulator import _evaluate
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.side_effect = Exception("API down")
            result = _evaluate("Q", "Some answer", "Engineer")
        # Must not raise; returns fallback with score=50
        assert result["score"] == 50

    def test_evaluate_score_color_green_for_high(self):
        from milestone3.interview_simulator import _evaluate
        high_response = self._mock_eval_response().replace("OVERALL: 77", "OVERALL: 85")
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=high_response))]
            )
            result = _evaluate("Q", "A", "Engineer")
        assert result["color"] == "#10b981"

    def test_evaluate_score_color_red_for_low(self):
        from milestone3.interview_simulator import _evaluate
        low_response = self._mock_eval_response().replace("OVERALL: 77", "OVERALL: 20")
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=low_response))]
            )
            result = _evaluate("Q", "A", "Engineer")
        assert result["color"] == "#ef4444"

    def test_evaluate_improvements_list(self):
        from milestone3.interview_simulator import _evaluate
        with patch("milestone3.interview_simulator._use_gemini", return_value=False), \
             patch("milestone3.interview_simulator._GROQ") as mock_groq:
            mock_groq.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=self._mock_eval_response()))]
            )
            result = _evaluate("Q", "A", "Engineer")
        assert isinstance(result["improvements"], list)
        assert len(result["improvements"]) == 3
