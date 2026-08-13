"""Orchestrates the full resume processing pipeline: parse → extract → store."""

import logging
import re
from pathlib import Path
from typing import Any

from config.settings import SUPPORTED_EXTENSIONS, UPLOAD_DIR
from database.db_manager import DatabaseManager
from database.db_service import DatabaseService, SaveResult
from parsers.profile_extractor import CandidateProfile, ProfileExtractor
from parsers.resume_parser import ResumeParser
from services.job_service import JobService

logger = logging.getLogger(__name__)


class CandidateService:
    """
    High-level facade consumed by the UI layer.

    Owns one DatabaseManager instance that is shared with DatabaseService,
    so all reads and writes go through the same connection pool.
    """

    def __init__(self) -> None:
        self._db        = DatabaseManager()
        self._db_svc    = DatabaseService(self._db)   # shared instance
        self._parser    = ResumeParser()
        self._extractor = ProfileExtractor()
        self.jobs       = JobService(self._db)         # job operations

    # ── Resume pipeline ────────────────────────────────────────────────────

    def process_resume(self, file_path: Path, recruiter_email: str = "") -> tuple[CandidateProfile, SaveResult]:
        """
        Full pipeline: extract text → build profile → persist.
        """
        logger.info("process_resume › start  file=%s", file_path.name)

        raw_text = self._parser.parse(file_path)
        profile  = self._extractor.extract(raw_text)

        try:
            resume_path = str(file_path.relative_to(file_path.parent.parent))
        except ValueError:
            resume_path = file_path.name

        result = self._db_svc.save_profile(profile, resume_path, recruiter_email)
        logger.info(
            "process_resume › done  file=%s  status=%s  id=%s",
            file_path.name, result.status.name, result.candidate_id,
        )
        return profile, result

    def save_upload(self, file_bytes: bytes, file_name: str) -> Path:
        """Persist raw upload bytes to the uploads directory.

        Sanitizes the filename to prevent path traversal (CWE-22):
        - Strips all directory separators and null bytes.
        - Allows only alphanumerics, dots, hyphens, and underscores.
        - Rejects extensions outside the supported set.
        """
        safe_name = re.sub(r"[^\w.\-]", "_", Path(file_name).name)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: '{suffix}'")
        dest = UPLOAD_DIR / safe_name
        # Confirm resolved path stays inside UPLOAD_DIR (belt-and-suspenders)
        if not dest.resolve().is_relative_to(UPLOAD_DIR.resolve()):
            raise ValueError(f"Unsafe upload path rejected: {file_name}")
        dest.write_bytes(file_bytes)
        logger.debug("save_upload › saved  file=%s  bytes=%d", safe_name, len(file_bytes))
        return dest

    # ── Read ───────────────────────────────────────────────────────────────

    def get_all_candidates(self, recruiter_email: str = "") -> list[dict[str, Any]]:
        return self._db.get_all_candidates(recruiter_email)

    def get_candidate(self, candidate_id: int) -> dict[str, Any] | None:
        return self._db.get_candidate_by_id(candidate_id)

    def get_candidate_by_email(self, email: str) -> dict[str, Any] | None:
        return self._db.get_candidate_by_email(email)

    def search_candidates(self, keyword: str) -> list[dict[str, Any]]:
        return self._db.search_candidates(keyword)

    # ── Write ──────────────────────────────────────────────────────────────

    def update_candidate(self, candidate_id: int, data: dict[str, Any]) -> bool:
        return self._db.update_candidate(candidate_id, data)

    def delete_candidate(self, candidate_id: int) -> None:
        """Delete candidate record and remove the associated resume file."""
        candidate = self._db.get_candidate_by_id(candidate_id)
        if candidate and candidate.get("resume_path"):
            # Prevent path traversal attacks by ensuring the path is relative
            # and resolving it safely within the UPLOAD_DIR.
            resume_path = Path(candidate["resume_path"])
            # Disallow absolute paths or paths that try to go up directories.
            if resume_path.is_absolute() or ".." in resume_path.parts:
                logger.warning("delete_candidate › unsafe path rejected  path=%s", resume_path)
                return

            upload_file = (UPLOAD_DIR / resume_path).resolve()
            try:
                if upload_file.is_relative_to(UPLOAD_DIR.resolve()) and upload_file.exists():
                    upload_file.unlink()
                    logger.info("delete_candidate › removed file  path=%s", upload_file)
            except Exception as e:
                logger.error("delete_candidate › failed to remove file %s: %s", upload_file, e)

        self._db.delete_candidate(candidate_id)
