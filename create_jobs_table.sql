-- ─────────────────────────────────────────────
--  SQL: Create the 'jobs' table
--  Run this in MySQL Workbench or MySQL CLI
-- ─────────────────────────────────────────────

-- Step 1: Select your database
USE myrecruitment;

-- Step 2: Create the jobs table
CREATE TABLE IF NOT EXISTS jobs (
    job_id        INT          PRIMARY KEY AUTO_INCREMENT,  -- unique ID, auto increases
    job_title     VARCHAR(255) NOT NULL,                    -- e.g. "Python Developer"
    certification VARCHAR(255) NOT NULL,                    -- e.g. "AWS Certified"
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP    -- auto-filled timestamp
);

-- Step 3: Verify the table was created
DESCRIBE jobs;
