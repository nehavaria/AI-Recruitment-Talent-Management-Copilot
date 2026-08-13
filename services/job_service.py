"""Job Service: business logic for job postings."""

import logging
from typing import Any

from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Constants for dropdowns, can be moved to settings
DEPARTMENTS = [
    "Engineering", "Product", "Design", "Marketing", "Sales",
    "Human Resources", "Finance", "Operations", "Support",
]
JOB_TYPES = ["Full-Time", "Part-Time", "Contract", "Internship"]
EXP_LEVELS = ["Fresher", "Junior", "Mid-Level", "Senior", "Lead", "Manager"]
JOB_STATUSES = ["Open", "Closed", "On Hold", "Draft"]


class JobService:
    """
    High-level service for managing job postings.

    This acts as a facade between the UI and the database, handling
    validation and business logic for job-related operations.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def get_all_jobs(self, recruiter_email: str = "") -> list[dict[str, Any]]:
        """Retrieve all job postings for this recruiter."""
        return self._db.get_all_jobs(recruiter_email)

    def post_job(self, data: dict[str, Any]) -> tuple[bool, str, int | None]:
        """
        Create a new job posting after validation.

        Returns:
            (success_bool, message_str, job_id_or_None)
        """
        if not data.get("job_title"):
            return False, "Job Title is a required field.", None
        if not data.get("description"):
            return False, "Job Description is a required field.", None

        try:
            job_id = self._db.create_job(data)
            msg = f"Job '{data['job_title']}' posted successfully (ID: {job_id})."
            logger.info("post_job › success  id=%s", job_id)
            return True, msg, job_id
        except Exception as e:
            msg = f"Failed to post job: {e}"
            logger.exception("post_job › failed  title=%s", data.get("job_title"))
            return False, msg, None

    def update_job(self, job_id: int, data: dict[str, Any]) -> tuple[bool, str]:
        """Update specific fields of an existing job."""
        if not data:
            return False, "No changes provided to update."
        try:
            updated = self._db.update_job(job_id, data)
            if updated:
                msg = f"Job ID {job_id} updated successfully."
                return True, msg
            return False, f"Job ID {job_id} not found or no changes made."
        except Exception as e:
            return False, f"Failed to update job: {e}"

    def replace_job(self, job_id: int, data: dict[str, Any]) -> tuple[bool, str]:
        """
        Completely replace a job's data using its ID.

        This calls the `REPLACE INTO` logic in the database manager.
        """
        try:
            data["job_id"] = job_id  # Ensure the job_id is in the payload
            new_job_id = self._db.replace_job(data)
            msg = f"Job ID {job_id} was replaced successfully. New ID is {new_job_id}."
            logger.info("replace_job › success old_id=%s new_id=%s", job_id, new_job_id)
            return True, msg
        except Exception as e:
            msg = f"Failed to replace job {job_id}: {e}"
            logger.exception("replace_job › failed id=%s", job_id)
            return False, msg

    def update_status(self, job_id: int, status: str) -> tuple[bool, str]:
        """Quickly update only the status of a job."""
        if status not in JOB_STATUSES:
            return False, f"Invalid status: {status}"
        return self.update_job(job_id, {"status": status})

    def delete_job(self, job_id: int) -> tuple[bool, str]:
        """Delete a job posting."""
        try:
            deleted = self._db.delete_job(job_id)
            if deleted:
                return True, f"Job ID {job_id} deleted successfully."
            return False, f"Job ID {job_id} not found."
        except Exception as e:
            return False, f"Failed to delete job: {e}"