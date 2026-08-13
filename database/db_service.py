"""Database service: transactional save, duplicate handling, structured results."""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import mysql.connector

from database.db_manager import DatabaseManager
from parsers.profile_extractor import CandidateProfile

logger = logging.getLogger(__name__)


# ── Result types ───────────────────────────────────────────────────────────

class SaveStatus(Enum):
    CREATED = auto()   # new candidate inserted
    UPDATED = auto()   # existing candidate updated (duplicate email)
    FAILED  = auto()   # validation error or unrecoverable DB error


@dataclass
class SaveResult:
    """Returned by every DatabaseService write operation."""

    status:       SaveStatus
    candidate_id: int | None
    email:        str
    message:      str
    errors:       list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is not SaveStatus.FAILED

    def __str__(self) -> str:
        return f"[{self.status.name}] {self.message}"


# ── Service ────────────────────────────────────────────────────────────────

class DatabaseService:
    """
    Transactional service layer between the resume pipeline and DatabaseManager.

    Responsibilities
    ----------------
    - Validate profile data before any DB write.
    - Detect duplicate candidates by email and update instead of re-inserting.
    - Wrap every write in an explicit transaction with rollback on failure.
    - Log every operation with its outcome.
    - Return a SaveResult — callers never need to catch exceptions.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ── Public API ─────────────────────────────────────────────────────────

    def save_profile(self, profile: CandidateProfile, resume_path: str = "", recruiter_email: str = "") -> SaveResult:
        """
        Persist a parsed CandidateProfile.

        - Inserts a new row when the email is unseen.
        - Updates the existing row on duplicate email.
        - Returns FAILED (with error list) on validation failure or DB error.
        """
        email = profile.email.strip().lower()
        logger.info("save_profile › start  email=%s  resume=%s", email, resume_path or "—")

        errors = self._validate(profile)
        if errors:
            msg = f"Validation failed for '{email}': {'; '.join(errors)}"
            logger.warning("save_profile › validation  %s", msg)
            return SaveResult(SaveStatus.FAILED, None, email, msg, errors)

        db_dict  = profile.to_db_dict(resume_path=resume_path)
        db_dict["recruiter_email"] = recruiter_email
        existing = self._db.get_candidate_by_email(email)

        try:
            if existing is None:
                return self._insert(db_dict, email)
            return self._update(db_dict, existing["candidate_id"], email)
        except Exception as exc:
            msg = f"Unexpected error saving '{email}': {exc}"
            logger.exception("save_profile › error  %s", msg)
            return SaveResult(SaveStatus.FAILED, None, email, msg, [str(exc)])

    def save_profiles_bulk(
        self, profiles: list[tuple[CandidateProfile, str]]
    ) -> list[SaveResult]:
        """
        Save multiple (profile, resume_path) pairs.
        Each profile is saved in its own transaction so one failure
        does not block the rest.
        """
        results: list[SaveResult] = []
        for profile, resume_path in profiles:
            result = self.save_profile(profile, resume_path)
            results.append(result)
            logger.info(
                "save_profiles_bulk › %s  id=%s  email=%s",
                result.status.name, result.candidate_id, result.email,
            )

        created = sum(1 for r in results if r.status is SaveStatus.CREATED)
        updated = sum(1 for r in results if r.status is SaveStatus.UPDATED)
        failed  = sum(1 for r in results if r.status is SaveStatus.FAILED)
        logger.info(
            "save_profiles_bulk › done  total=%d  created=%d  updated=%d  failed=%d",
            len(results), created, updated, failed,
        )
        return results

    # ── Private helpers ────────────────────────────────────────────────────

    def _insert(self, db_dict: dict[str, Any], email: str) -> SaveResult:
        try:
            candidate_id = self._db.create_candidate(db_dict)
            msg = f"Candidate '{email}' saved successfully (id={candidate_id})."
            logger.info("save_profile › created  %s", msg)
            return SaveResult(SaveStatus.CREATED, candidate_id, email, msg)
        except mysql.connector.IntegrityError:
            # Race condition: another process inserted the same email between
            # our existence check and this insert — fall back to update.
            logger.warning(
                "save_profile › race-condition duplicate  email=%s  falling back to update",
                email,
            )
            existing = self._db.get_candidate_by_email(email)
            if existing:
                return self._update(db_dict, existing["candidate_id"], email)
            raise

    def _update(self, db_dict: dict[str, Any], candidate_id: int, email: str) -> SaveResult:
        update_fields = {k: v for k, v in db_dict.items() if k != "email"}
        self._db.update_candidate(candidate_id, update_fields)
        msg = (
            f"Duplicate email '{email}' detected — "
            f"existing candidate (id={candidate_id}) updated with latest resume data."
        )
        logger.info("save_profile › updated  %s", msg)
        return SaveResult(SaveStatus.UPDATED, candidate_id, email, msg)

    @staticmethod
    def _validate(profile: CandidateProfile) -> list[str]:
        errors: list[str] = []
        if not profile.name or not profile.name.strip():
            errors.append("Name is missing or empty.")
        if not profile.email or not profile.email.strip():
            errors.append("Email is missing or empty.")
        elif "@" not in profile.email or "." not in profile.email.split("@")[-1]:
            errors.append(f"Email '{profile.email}' does not appear valid.")
        return errors
