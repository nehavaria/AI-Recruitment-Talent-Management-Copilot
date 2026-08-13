-- ============================================================
--  AI Recruitment Copilot — MySQL Setup Script
--  Run this in MySQL Workbench or MySQL CLI
-- ============================================================

-- Step 1: Create and select the database
CREATE DATABASE IF NOT EXISTS recruitment_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE recruitment_db;

-- ============================================================
--  TABLE 1: candidates
-- ============================================================
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id   INT           PRIMARY KEY AUTO_INCREMENT,
    name           VARCHAR(255)  NOT NULL,
    email          VARCHAR(255)  NOT NULL UNIQUE,
    phone          VARCHAR(50),
    education      TEXT,
    skills         TEXT,
    experience     TEXT,
    projects       TEXT,
    certifications TEXT,
    resume_path    VARCHAR(500),
    created_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);

-- ============================================================
--  TABLE 2: jobs
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id           INT           PRIMARY KEY AUTO_INCREMENT,
    job_title        VARCHAR(255)  NOT NULL,
    department       VARCHAR(150),
    location         VARCHAR(150),
    job_type         VARCHAR(50)   DEFAULT 'Full-Time',
    experience_level VARCHAR(50)   DEFAULT 'Mid-Level',
    salary_min       DECIMAL(12,2),
    salary_max       DECIMAL(12,2),
    description      TEXT,
    requirements     TEXT,
    responsibilities TEXT,
    skills_required  TEXT,
    benefits         TEXT,
    status           VARCHAR(20)   DEFAULT 'Open',
    openings         INT           DEFAULT 1,
    posted_by        VARCHAR(255),
    deadline         DATE,
    created_date     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_date     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_title     ON jobs(job_title);
CREATE INDEX IF NOT EXISTS idx_jobs_dept      ON jobs(department);

-- ============================================================
--  Verify
-- ============================================================
SHOW TABLES;
DESCRIBE candidates;
DESCRIBE jobs;
