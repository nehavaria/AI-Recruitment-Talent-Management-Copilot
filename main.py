# ─────────────────────────────────────────────
#  FastAPI — Full CRUD API
#  Run with: uvicorn main:app --reload
# ─────────────────────────────────────────────

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Any
from fastapi.responses import JSONResponse
from fastapi import HTTPException, status

from database.db_manager import DatabaseManager

# ── App instance ──────────────────────────────
app = FastAPI(title="Recruitment API", version="1.0.0")

# ── Database service dependency ───────────────
# Use the existing DatabaseManager for all DB operations
db_manager = DatabaseManager()


# ══════════════════════════════════════════════
#  PYDANTIC MODELS
# ══════════════════════════════════════════════

class Job(BaseModel):
    job_title:        str
    certification:    str
    department:       str           = ""
    location:         str           = ""
    job_type:         str           = "Full-Time"
    experience_level: str           = "Mid-Level"
    salary_min:       Optional[float] = None
    salary_max:       Optional[float] = None
    description:      str           = ""
    requirements:     str           = ""
    responsibilities: str           = ""
    skills_required:  str           = ""
    benefits:         str           = ""
    status:           str           = "Open"
    openings:         int           = 1
    posted_by:        str           = ""
    deadline:         str           = ""


class Candidate(BaseModel):
    name:           str
    email:          str
    phone:          str           = ""
    education:      str           = ""
    skills:         str           = ""
    experience:     str           = ""
    projects:       str           = ""
    certifications: str           = ""
    resume_path:    str           = ""


# ══════════════════════════════════════════════
#  JOBS CRUD
# ══════════════════════════════════════════════

# ── CREATE job ────────────────────────────────
@app.post("/jobs")
def create_job(job: Job):
    """Insert a new job into the database."""
    try:
        job_id = db_manager.create_job(job.model_dump())
        return {
            "status":  "success",
            "message": "Job created successfully",
            "job_id":  job_id
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── READ all jobs ─────────────────────────────
@app.get("/jobs")
def get_all_jobs():
    """Get all jobs from the database."""
    try:
        jobs = db_manager.get_all_jobs()
        return {
            "status": "success",
            "total":  len(jobs),
            "jobs":   jobs
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── READ single job by ID ─────────────────────
@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    """Get one job by its ID."""
    try:
        job = db_manager.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job ID {job_id} not found")
        return {"status": "success", "job": job}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── UPDATE job ────────────────────────────────
@app.put("/jobs/{job_id}")
def update_job(job_id: int, job: Job):
    """Update an existing job by its ID."""
    try:
        updated = db_manager.update_job(job_id, job.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job ID {job_id} not found")
        return {"status": "success", "message": f"Job ID {job_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── REPLACE job (new functionality) ───────────
@app.put("/jobs/{job_id}/replace")
def replace_job(job_id: int, job: Job):
    """
    Replace an existing job's data entirely or insert if it doesn't exist.
    This uses the `REPLACE INTO` SQL command.
    """
    try:
        data = job.model_dump()
        data["job_id"] = job_id
        new_job_id = db_manager.replace_job(data)
        return {"status": "success",
                "message": f"Job ID {job_id} replaced successfully. New ID is {new_job_id}",
                "job_id": new_job_id}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── DELETE job ────────────────────────────────
@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    """Delete a job by its ID."""
    try:
        deleted = db_manager.delete_job(job_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job ID {job_id} not found")
        return {"status": "success", "message": f"Job ID {job_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ══════════════════════════════════════════════
#  CANDIDATES CRUD
# ══════════════════════════════════════════════

# ── CREATE candidate ──────────────────────────
@app.post("/candidates")
def create_candidate(candidate: Candidate):
    """Insert a new candidate into the database."""
    try:
        candidate_id = db_manager.create_candidate(candidate.model_dump())
        return {
            "status":       "success",
            "message":      "Candidate created successfully",
            "candidate_id": candidate_id
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── READ all candidates ───────────────────────
@app.get("/candidates")
def get_all_candidates():
    """Get all candidates from the database."""
    try:
        candidates = db_manager.get_all_candidates()
        return {
            "status":     "success",
            "total":      len(candidates),
            "candidates": candidates
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── READ single candidate by ID ───────────────
@app.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    """Get one candidate by their ID."""
    try:
        candidate = db_manager.get_candidate_by_id(candidate_id)
        if not candidate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Candidate ID {candidate_id} not found")
        return {"status": "success", "candidate": candidate}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── UPDATE candidate ──────────────────────────
@app.put("/candidates/{candidate_id}")
def update_candidate(candidate_id: int, candidate: Candidate):
    """Update an existing candidate by their ID."""
    try:
        updated = db_manager.update_candidate(candidate_id, candidate.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Candidate ID {candidate_id} not found")
        return {"status": "success", "message": f"Candidate ID {candidate_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── REPLACE candidate (new functionality) ─────
@app.put("/candidates/{candidate_id}/replace")
def replace_candidate(candidate_id: int, candidate: Candidate):
    """
    Replace an existing candidate's data entirely or insert if it doesn't exist.
    This uses the `REPLACE INTO` SQL command.
    """
    try:
        data = candidate.model_dump()
        data["candidate_id"] = candidate_id
        new_candidate_id = db_manager.replace_candidate(data)
        return {"status": "success",
                "message": f"Candidate ID {candidate_id} replaced successfully. New ID is {new_candidate_id}",
                "candidate_id": new_candidate_id}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# ── DELETE candidate ──────────────────────────
@app.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int):
    """Delete a candidate by their ID."""
    try:
        deleted = db_manager.delete_candidate(candidate_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Candidate ID {candidate_id} not found")
        return {"status": "success", "message": f"Candidate ID {candidate_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
