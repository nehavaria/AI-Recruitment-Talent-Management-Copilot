# ─────────────────────────────────────────────────────────────
#  Candidate-Job Matching Engine
#  Add to FastAPI by including this router in main.py:
#  from matching_engine import router as match_router
#  app.include_router(match_router)
# ─────────────────────────────────────────────────────────────

from fastapi import APIRouter
import mysql.connector
from mysql.connector import Error

router = APIRouter(prefix="/match", tags=["Matching Engine"])

# ── MySQL connection config ───────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "database": "myrecruitment",
    "user":     "root",
    "password": "Nu<2406>"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


# ══════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════

def normalize_skills(skills_str: str) -> set:
    """
    Normalize skills string:
    - Split by comma
    - Convert to lowercase
    - Trim spaces
    - Remove duplicates (set does this automatically)
    """
    if not skills_str:
        return set()
    return {skill.strip().lower() for skill in skills_str.split(",") if skill.strip()}


def compare_skills(resume_skills: set, jd_skills: set) -> dict:
    """
    Compare candidate skills with job required skills.
    matched_skills   = resume_skills ∩ jd_skills
    missing_skills   = jd_skills - resume_skills
    additional_skills = resume_skills - jd_skills
    """
    matched    = resume_skills & jd_skills          # intersection
    missing    = jd_skills - resume_skills          # in JD but not in resume
    additional = resume_skills - jd_skills          # in resume but not in JD

    # Calculate match percentage
    match_pct = round((len(matched) / len(jd_skills)) * 100, 1) if jd_skills else 0.0

    return {
        "matched_skills":    sorted(matched),
        "missing_skills":    sorted(missing),
        "additional_skills": sorted(additional),
        "match_percentage":  match_pct,
        "matched_count":     len(matched),
        "missing_count":     len(missing),
        "additional_count":  len(additional),
    }


def compare_experience(candidate_exp: str, jd_exp_level: str) -> dict:
    """
    Compare candidate experience text with JD experience level.
    Maps JD level to minimum expected years.
    """
    # Map experience level to minimum years
    level_map = {
        "fresher":   0,
        "junior":    1,
        "mid-level": 3,
        "senior":    5,
        "lead":      7,
        "manager":   8,
    }

    required_years = level_map.get(jd_exp_level.lower(), 0)

    # Try to extract years from candidate experience text
    import re
    years_found = re.findall(r"(\d+)\s*(?:year|yr)", candidate_exp.lower())
    candidate_years = max([int(y) for y in years_found], default=0)

    meets_requirement = candidate_years >= required_years

    return {
        "jd_experience_level":    jd_exp_level,
        "jd_required_min_years":  required_years,
        "candidate_years_found":  candidate_years,
        "meets_experience":       meets_requirement,
        "experience_remark":      "✅ Meets requirement" if meets_requirement else f"❌ Needs {required_years}+ years"
    }


def compare_education(candidate_edu: str, jd_requirements: str) -> dict:
    """
    Check if candidate education matches JD education requirements.
    Looks for keywords like B.Tech, MBA, B.Sc etc.
    """
    edu_keywords = ["b.tech", "m.tech", "bsc", "msc", "mba", "bca", "mca",
                    "bachelor", "master", "phd", "diploma", "degree"]

    candidate_edu_lower  = candidate_edu.lower()
    jd_requirements_lower = jd_requirements.lower()

    # Find what education JD mentions
    jd_edu_found = [kw for kw in edu_keywords if kw in jd_requirements_lower]

    # Find what education candidate has
    candidate_edu_found = [kw for kw in edu_keywords if kw in candidate_edu_lower]

    # Check if any JD education keyword exists in candidate education
    matched_edu = [kw for kw in jd_edu_found if kw in candidate_edu_lower]
    meets_edu   = len(matched_edu) > 0 if jd_edu_found else True  # if JD has no edu req, pass

    return {
        "jd_education_required":  jd_edu_found,
        "candidate_education_has": candidate_edu_found,
        "education_matched":      matched_edu,
        "meets_education":        meets_edu,
        "education_remark":       "✅ Meets requirement" if meets_edu else "❌ Education requirement not met"
    }


def compare_certifications(candidate_certs: str, jd_certification: str) -> dict:
    """
    Compare candidate certifications with JD certification requirement.
    This is optional — if JD has no cert requirement, it passes automatically.
    """
    if not jd_certification or jd_certification.strip() == "":
        return {
            "jd_certification_required": None,
            "candidate_has_cert":        candidate_certs,
            "certification_matched":     True,
            "cert_remark":               "✅ No certification required"
        }

    jd_cert_lower        = jd_certification.lower()
    candidate_cert_lower = candidate_certs.lower()

    matched = jd_cert_lower in candidate_cert_lower

    return {
        "jd_certification_required": jd_certification,
        "candidate_has_cert":        candidate_certs,
        "certification_matched":     matched,
        "cert_remark":               "✅ Certification matched" if matched else "❌ Certification not found in resume"
    }


def calculate_overall_score(skill_pct: float, meets_exp: bool, meets_edu: bool, cert_matched: bool) -> dict:
    """
    Calculate overall match score out of 100.
    Skills      = 60% weight
    Experience  = 20% weight
    Education   = 15% weight
    Certification = 5% weight
    """
    score = (
        (skill_pct * 0.60) +
        (20 if meets_exp  else 0) +
        (15 if meets_edu  else 0) +
        (5  if cert_matched else 0)
    )
    score = round(score, 1)

    # Grade based on score
    if score >= 80:
        grade   = "A"
        verdict = "🟢 Highly Recommended"
    elif score >= 60:
        grade   = "B"
        verdict = "🟡 Good Match"
    elif score >= 40:
        grade   = "C"
        verdict = "🟠 Partial Match"
    else:
        grade   = "D"
        verdict = "🔴 Not Recommended"

    return {
        "overall_score": score,
        "grade":         grade,
        "verdict":       verdict
    }


# ══════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════

# ── 1. Match one candidate with one job ───────
@router.get("/candidate/{candidate_id}/job/{job_id}")
def match_candidate_to_job(candidate_id: int, job_id: int):
    """
    Match a single candidate against a single job.
    Returns full skill, experience, education, certification comparison.
    """
    connection = None
    cursor     = None
    try:
        connection = get_connection()
        cursor     = connection.cursor(dictionary=True)

        # Step 1: Fetch candidate from DB
        cursor.execute("SELECT * FROM candidates WHERE candidate_id = %s", (candidate_id,))
        candidate = cursor.fetchone()
        if not candidate:
            return {"status": "error", "message": f"Candidate ID {candidate_id} not found"}

        # Step 2: Fetch job from DB
        cursor.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
        job = cursor.fetchone()
        if not job:
            return {"status": "error", "message": f"Job ID {job_id} not found"}

        # Step 3: Normalize skills
        resume_skills = normalize_skills(candidate.get("skills", ""))
        jd_skills     = normalize_skills(job.get("skills_required", ""))

        # Step 4: Compare all sections
        skill_result = compare_skills(resume_skills, jd_skills)
        exp_result   = compare_experience(candidate.get("experience", ""), job.get("experience_level", ""))
        edu_result   = compare_education(candidate.get("education", ""), job.get("requirements", ""))
        cert_result  = compare_certifications(candidate.get("certifications", ""), job.get("certification", ""))

        # Step 5: Overall score
        score_result = calculate_overall_score(
            skill_pct     = skill_result["match_percentage"],
            meets_exp     = exp_result["meets_experience"],
            meets_edu     = edu_result["meets_education"],
            cert_matched  = cert_result["certification_matched"]
        )

        # Step 6: Return dashboard-friendly JSON
        return {
            "status": "success",
            "candidate": {
                "candidate_id": candidate["candidate_id"],
                "name":         candidate["name"],
                "email":        candidate["email"],
            },
            "job": {
                "job_id":    job["job_id"],
                "job_title": job["job_title"],
                "department": job.get("department", ""),
            },
            "skills_analysis":        skill_result,
            "experience_analysis":    exp_result,
            "education_analysis":     edu_result,
            "certification_analysis": cert_result,
            "overall":                score_result,
        }

    except Error as e:
        return {"status": "error", "message": str(e)}

    finally:
        if cursor:     cursor.close()
        if connection and connection.is_connected(): connection.close()


# ── 2. Match one candidate against ALL jobs ───
@router.get("/candidate/{candidate_id}/all-jobs")
def match_candidate_to_all_jobs(candidate_id: int):
    """
    Match a single candidate against all jobs in the database.
    Returns a ranked list of jobs sorted by overall score.
    """
    connection = None
    cursor     = None
    try:
        connection = get_connection()
        cursor     = connection.cursor(dictionary=True)

        # Fetch candidate
        cursor.execute("SELECT * FROM candidates WHERE candidate_id = %s", (candidate_id,))
        candidate = cursor.fetchone()
        if not candidate:
            return {"status": "error", "message": f"Candidate ID {candidate_id} not found"}

        # Fetch all jobs
        cursor.execute("SELECT * FROM jobs WHERE status = 'Open' ORDER BY job_id")
        jobs = cursor.fetchall()

        if not jobs:
            return {"status": "error", "message": "No open jobs found in database"}

        resume_skills = normalize_skills(candidate.get("skills", ""))
        results       = []

        for job in jobs:
            jd_skills    = normalize_skills(job.get("skills_required", ""))
            skill_result = compare_skills(resume_skills, jd_skills)
            exp_result   = compare_experience(candidate.get("experience", ""), job.get("experience_level", ""))
            edu_result   = compare_education(candidate.get("education", ""), job.get("requirements", ""))
            cert_result  = compare_certifications(candidate.get("certifications", ""), job.get("certification", ""))
            score_result = calculate_overall_score(
                skill_pct    = skill_result["match_percentage"],
                meets_exp    = exp_result["meets_experience"],
                meets_edu    = edu_result["meets_education"],
                cert_matched = cert_result["certification_matched"]
            )

            results.append({
                "job_id":            job["job_id"],
                "job_title":         job["job_title"],
                "department":        job.get("department", ""),
                "location":          job.get("location", ""),
                "matched_skills":    skill_result["matched_skills"],
                "missing_skills":    skill_result["missing_skills"],
                "match_percentage":  skill_result["match_percentage"],
                "overall_score":     score_result["overall_score"],
                "grade":             score_result["grade"],
                "verdict":           score_result["verdict"],
            })

        # Sort by overall score descending (best match first)
        results.sort(key=lambda x: x["overall_score"], reverse=True)

        return {
            "status":        "success",
            "candidate_id":  candidate_id,
            "candidate_name": candidate["name"],
            "total_jobs":    len(results),
            "ranked_jobs":   results
        }

    except Error as e:
        return {"status": "error", "message": str(e)}

    finally:
        if cursor:     cursor.close()
        if connection and connection.is_connected(): connection.close()


# ── 3. Match one job against ALL candidates ───
@router.get("/job/{job_id}/all-candidates")
def match_job_to_all_candidates(job_id: int):
    """
    Match a single job against all candidates in the database.
    Returns a ranked list of candidates sorted by overall score.
    """
    connection = None
    cursor     = None
    try:
        connection = get_connection()
        cursor     = connection.cursor(dictionary=True)

        # Fetch job
        cursor.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
        job = cursor.fetchone()
        if not job:
            return {"status": "error", "message": f"Job ID {job_id} not found"}

        # Fetch all candidates
        cursor.execute("SELECT * FROM candidates ORDER BY candidate_id")
        candidates = cursor.fetchall()

        if not candidates:
            return {"status": "error", "message": "No candidates found in database"}

        jd_skills = normalize_skills(job.get("skills_required", ""))
        results   = []

        for candidate in candidates:
            resume_skills = normalize_skills(candidate.get("skills", ""))
            skill_result  = compare_skills(resume_skills, jd_skills)
            exp_result    = compare_experience(candidate.get("experience", ""), job.get("experience_level", ""))
            edu_result    = compare_education(candidate.get("education", ""), job.get("requirements", ""))
            cert_result   = compare_certifications(candidate.get("certifications", ""), job.get("certification", ""))
            score_result  = calculate_overall_score(
                skill_pct    = skill_result["match_percentage"],
                meets_exp    = exp_result["meets_experience"],
                meets_edu    = edu_result["meets_education"],
                cert_matched = cert_result["certification_matched"]
            )

            results.append({
                "candidate_id":      candidate["candidate_id"],
                "name":              candidate["name"],
                "email":             candidate["email"],
                "matched_skills":    skill_result["matched_skills"],
                "missing_skills":    skill_result["missing_skills"],
                "match_percentage":  skill_result["match_percentage"],
                "overall_score":     score_result["overall_score"],
                "grade":             score_result["grade"],
                "verdict":           score_result["verdict"],
            })

        # Sort by overall score descending (best candidate first)
        results.sort(key=lambda x: x["overall_score"], reverse=True)

        return {
            "status":           "success",
            "job_id":           job_id,
            "job_title":        job["job_title"],
            "total_candidates": len(results),
            "ranked_candidates": results
        }

    except Error as e:
        return {"status": "error", "message": str(e)}

    finally:
        if cursor:     cursor.close()
        if connection and connection.is_connected(): connection.close()
