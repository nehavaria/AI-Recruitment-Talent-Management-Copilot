# TalentAI — Milestone 2 Documentation

**Project:** AI Recruitment & Talent Management Copilot  
**Stack:** Streamlit · MySQL · Plotly · fpdf2  
**Database:** `myrecruitment` (MySQL, localhost:3306)

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [How to Run](#2-how-to-run)
3. [Scoring Formula](#3-scoring-formula)
4. [Page 1 — Recruiter Dashboard](#4-page-1--recruiter-dashboard)
5. [Page 2 — Candidate Matching](#5-page-2--candidate-matching)
6. [Page 3 — Hiring Score](#6-page-3--hiring-score)
7. [Page 4 — Candidate Ranking](#7-page-4--candidate-ranking)
8. [Page 5 — Skill Gap Analysis](#8-page-5--skill-gap-analysis)
9. [Visual Summaries (Charts)](#9-visual-summaries-charts)
10. [Download Reports](#10-download-reports)
11. [Database Tables](#11-database-tables)
12. [Dependencies](#12-dependencies)
13. [Grade System](#13-grade-system)
14. [Common Errors & Fixes](#14-common-errors--fixes)

---

## 1. Project Structure

```
infosyspro/
├── app.py                          ← Streamlit entry point, sidebar, CSS
├── main.py                         ← FastAPI backend (CRUD endpoints)
├── requirements.txt
│
├── config/
│   └── settings.py                 ← MySQL config, paths, skill taxonomy
│
├── database/
│   ├── db_manager.py               ← All MySQL CRUD (candidates + jobs)
│   └── db_service.py               ← Save/upsert pipeline
│
├── services/
│   ├── candidate_service.py        ← Resume pipeline + candidate CRUD facade
│   └── job_service.py              ← Job posting CRUD + validation
│
├── parsers/
│   ├── resume_parser.py            ← PDF/DOCX text extractor
│   └── profile_extractor.py        ← NLP field extractor (spaCy)
│
├── reports/
│   └── report_generator.py         ← CSV + PDF builders for all 3 reports
│
└── ui/
    ├── components.py               ← Reusable UI components
    └── pages/
        ├── recruiter_dashboard_page.py   ← Dashboard + 5 Plotly charts
        ├── matching_page.py              ← Candidate vs Job matching
        ├── hiring_score_page.py          ← Weighted scoring engine
        ├── ranking_page.py               ← Leaderboard for all candidates
        ├── skill_gap_page.py             ← Gap analysis + course recommendations
        ├── upload_page.py                ← Resume upload + parsing
        ├── dashboard_page.py             ← Candidate profile browser
        ├── jobs_page.py                  ← Job postings CRUD
        └── settings_page.py             ← Theme toggle
```

---

## 2. How to Run

**Prerequisites:** Python 3.11+, MySQL running on localhost:3306

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

**MySQL config** is in `config/settings.py`:
```python
MYSQL_HOST     = "localhost"
MYSQL_PORT     = 3306
MYSQL_DATABASE = "myrecruitment"
MYSQL_USER     = "root"
MYSQL_PASSWORD = "your_password"
```

The app auto-creates the `candidates` and `jobs` tables on first run.

---

## 3. Scoring Formula

All scoring pages use the **same weighted formula**:

```
Overall Score = (Skill Score × 70%) + (Experience Score × 20%) + (Cert Score × 10%)
```

### Skill Score
- Compares candidate skills (comma-separated) against job `skills_required`
- Uses set intersection: `matched / total_jd_skills × 100`
- If job has no skills listed → 100%

### Experience Score
- Maps level keywords to ranks: `fresher=0, junior=1, mid-level=2, senior=3, lead=4, manager=5`
- Candidate meets or exceeds JD level → 100%
- Candidate below JD level → proportional score
- Level not specified in JD → 100%
- Level not found in resume → 50%

### Certification Score
- Job requires cert and candidate has it → 100%
- Job has no cert requirement → 50% (neutral)
- Job requires cert but candidate missing it → 0%

---

## 4. Page 1 — Recruiter Dashboard

**File:** `ui/pages/recruiter_dashboard_page.py`  
**Sidebar:** 📋 Recruiter Dashboard

### What it does
Gives the recruiter a complete at-a-glance overview of all candidates, jobs, and scores — no selection needed. Automatically uses the first Open job as the reference job for scoring.

### Layout

| Row | Content |
|-----|---------|
| Row 1 | 5 gradient stat cards |
| Row 2 | 4 `st.metric()` boxes |
| Row 3 | Top candidate card + Job status panel |
| Row 4 | Skill Share pie chart + Missing Skills bar chart |
| Row 5 | Score Distribution histogram + Top Missing Skills bar chart |
| Row 6 | Full-width Candidate Ranking bar chart |

### Stat Cards (Row 1)
| Card | Value |
|------|-------|
| 👥 Total Candidates | Count from DB |
| 💼 Total Jobs | Count from DB |
| 🎯 Avg Hiring Score | Average of all candidate scores |
| ✅ Strong Matches | Candidates with score ≥ 70% |
| ⚠️ Weak Matches | Candidates with score < 40% |

### Key Functions

```python
_compute(candidates, jobs) → dict
```
Scores every candidate against the reference job. Returns:
- `total_candidates`, `total_jobs`, `open_jobs`, `closed_jobs`
- `avg_score`, `top_score`, `top_candidate`
- `missing_skills` — Counter of most missing skills (top 10)
- `top_skills` — Most common skills across all candidates (top 8)
- `all_scores` — List of all overall scores (used for histogram)
- `ranked` — Sorted list of `{name, score}` for ranking chart

---

## 5. Page 2 — Candidate Matching

**File:** `ui/pages/matching_page.py`  
**Sidebar:** 🎯 Candidate Matching

### What it does
Compares one candidate against one job description across 4 dimensions: skills, experience, education, and certifications.

### How to use
1. Select a Job from the dropdown
2. Select a Candidate from the dropdown
3. Click **🔍 Analyze Match**
4. Results are saved in `st.session_state.match_result` and persist until you run a new analysis

### Output Sections

**Metrics row:**
- 🎯 Match Score (skill match %)
- ✅ Matched Skills count
- ❌ Missing Skills count
- ➕ Additional Skills count

**Skill Analysis (3 columns):**
- Green pills → skills candidate has that job requires
- Red pills → skills job requires that candidate is missing
- Blue pills → extra skills candidate has beyond JD

**Profile Comparison (3 expanders):**
- 💼 Experience Comparison — JD level vs candidate level
- 🎓 Education Comparison — keyword match against JD requirements
- 🏅 Certification Comparison — word-level match

**Summary Verdict:**
- 🟢 Strong Match → score ≥ 75%
- 🟡 Moderate Match → score ≥ 50%
- 🔴 Weak Match → score < 50%

**Download section** appears at the bottom after analysis runs.

### Key Functions

```python
_match_skills(candidate_skills, job_skills) → dict
# Returns: matched, missing, additional lists + score %

_match_experience(candidate_exp, job_exp_level) → dict
# Returns: jd_level, candidate_level, status string

_match_education(candidate_edu, job_requirements) → dict
# Returns: jd_requires, candidate_has, status string

_match_certifications(candidate_certs, job_certification) → dict
# Returns: jd_requires, candidate_has, status, match bool
```

---

## 6. Page 3 — Hiring Score

**File:** `ui/pages/hiring_score_page.py`  
**Sidebar:** 🏆 Hiring Score

### What it does
Calculates the full weighted hiring score for one candidate against one job, with a detailed breakdown and hiring recommendation.

### How to use
1. Select a Job
2. Select a Candidate
3. Click **⚡ Calculate Hiring Score**

### Output Sections

**Big score card** — shows overall % with grade and verdict

**4 metrics:**
- 🎯 Overall Score
- 🛠 Skill Score
- 💼 Experience Score
- 🏅 Certification Score

**3 score cards** (with progress bars):
- Skill Match — weight 70%
- Experience — weight 20%
- Certification — weight 10%

**Score Breakdown Formula expander:**
```
Overall = (Skill × 70%) + (Experience × 20%) + (Certification × 10%)
        = (75% × 0.70) + (100% × 0.20) + (50% × 0.10)
        = 52.5 + 20.0 + 5.0
        = 77.5%
```

**Hiring Recommendation card:**
| Grade | Recommendation |
|-------|---------------|
| A+ | Strongly Recommend Hiring |
| A  | Recommend Hiring |
| B  | Consider with Conditions |
| C  | Borderline |
| D  | Not Recommended |

**Download section** appears at the bottom after calculation.

---

## 7. Page 4 — Candidate Ranking

**File:** `ui/pages/ranking_page.py`  
**Sidebar:** 📊 Candidate Ranking

### What it does
Scores ALL candidates against a selected job and ranks them from best to worst fit.

### How to use
1. Select a Job from the dropdown
2. Click **📊 Rank All**

### Output Sections

**4 summary metrics:**
- 👥 Total Candidates ranked
- 🏆 Top Score
- 📊 Average Score
- ✅ Strong Matches (score ≥ 70%)

**Top 3 Podium** — medal cards for 🥇 🥈 🥉 with:
- Name, email, overall score
- Grade badge
- Skill / Experience / Cert breakdown
- Progress bar

**Full Leaderboard** (rank 4 onwards) — row cards with:
- Rank number
- Name + email
- Overall, Skill, Experience metrics
- Grade badge
- Progress bar

**Full Rankings Table** (expander) — sortable dataframe with ProgressColumn for all score columns.

### Key Function

```python
_rank_all(candidates, job) → list[dict]
```
Returns sorted list of candidate dicts, each with:
`rank, name, email, overall, skill, experience, cert, matched, total_jd, grade, color, verdict`

---

## 8. Page 5 — Skill Gap Analysis

**File:** `ui/pages/skill_gap_page.py`  
**Sidebar:** 🔍 Skill Gap Analysis

### What it does
Shows exactly which skills a candidate is missing for a job, how big the gap is, and recommends specific courses to close each gap.

### How to use
1. Select a Job
2. Select a Candidate
3. Click **🔍 Analyze Skill Gap**

### Output Sections

**4 metrics:**
- ✅ Matched Skills
- ❌ Missing Skills
- ➕ Additional Skills
- 📉 Skill Gap %

**Gap Bar** — stacked green/red progress bar showing match % vs gap %

**3 skill columns:**
- Green pills → matched skills
- Red pills → missing skills
- Blue pills → extra skills

**Learning Recommendations** — grouped by level:
- 🟢 Beginner Level
- 🟡 Intermediate Level
- 🔴 Advanced Level
- 📌 Other Skills (not in recommendations database)

Each skill has an expandable card showing:
- Course name
- Platform (Coursera, Udemy, AWS Training, etc.)
- Difficulty level
- **Learn Now →** link

**40+ skills** are mapped in the recommendations database including: AWS, Azure, Docker, Kubernetes, Python, Java, React, SQL, TensorFlow, and more.

**Download section** appears at the bottom after analysis runs.

---

## 9. Visual Summaries (Charts)

All charts are in `recruiter_dashboard_page.py` using **Plotly** (`plotly.graph_objects`).

All charts share a transparent background so they blend into the dark card theme.

### Chart 1 — 🛠 Skill Share (Donut Pie)
- Shows the most common skills across all candidates
- Top 8 skills, each slice color-coded
- Hover shows skill name + candidate count

### Chart 2 — ❌ Missing Skills (Horizontal Bar)
- Shows which skills are most commonly missing across all candidates
- Bars colored by frequency (amber → red → pink gradient)
- Labels show % of candidates missing each skill

### Chart 3 — 📊 Score Distribution (Histogram)
- X-axis: score 0–100
- Y-axis: number of candidates
- Bars colored red → amber → green based on score range
- Shows how candidates are distributed across score ranges

### Chart 4 — 🔝 Top Missing Skills (Vertical Bar)
- Top 8 missing skills ranked by frequency
- Each bar a different color
- Labels show exact count above each bar

### Chart 5 — 🏆 Candidate Ranking (Horizontal Bar)
- Top 10 candidates ranked by overall score
- Bar color matches grade: green (A+), teal (A), amber (B), orange (C), red (D)
- Labels show score % next to each bar

### Chart Config
```python
_base_layout(**kwargs) → dict
# Returns shared layout: transparent bg, Inter font, no toolbar
```
All charts rendered with:
```python
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
```

---

## 10. Download Reports

**File:** `reports/report_generator.py`

Available on 3 pages after running an analysis:

| Page | CSV Function | PDF Function | Filename Pattern |
|------|-------------|-------------|-----------------|
| 🎯 Candidate Matching | `matching_csv(result)` | `matching_pdf(result)` | `matching_john_software_engineer.csv` |
| 🏆 Hiring Score | `hiring_score_csv(result)` | `hiring_score_pdf(result)` | `hiring_score_john_software_engineer.pdf` |
| 🔍 Skill Gap Analysis | `skill_gap_csv(result)` | `skill_gap_pdf(result)` | `skill_gap_john_data_analyst.pdf` |

### How to Download
1. Go to any of the 3 pages above
2. Select Job + Candidate and run the analysis
3. Scroll to the bottom
4. Click **⬇️ Download CSV** or **⬇️ Download PDF**

### CSV Contents
Each CSV includes:
- Report title + timestamp
- Candidate name + email
- Job title + department
- All scores and analysis results
- Skill Gap report also includes a full learning recommendations table

### PDF Contents
Each PDF includes:
- Branded header: "TalentAI · Recruitment Copilot" + timestamp
- Page numbers in footer
- Big score display with grade
- Color-coded progress bars for each score
- Skill lists (matched, missing, additional)
- Hiring recommendation text
- Skill Gap PDF includes a formatted recommendations table with alternating row shading

### PDF Class: `_BasePDF`
Built on `fpdf2`. Key methods:

```python
header()              # Dark header with brand name + timestamp
footer()              # Page number footer
section_title(text)   # Purple section heading with fill
kv_row(key, value)    # Label: Value row
score_bar(label, score, color)  # Visual progress bar in PDF
pill_row(label, skills, color)  # Comma-separated skill list
big_score(score, grade, verdict, color)  # Large centered score display
```

> **Note:** All text passed to PDF must be latin-1 safe. The `_safe()` helper strips non-latin-1 characters automatically.

---

## 11. Database Tables

### `candidates` table
| Column | Type | Description |
|--------|------|-------------|
| candidate_id | INT PK AUTO | Unique ID |
| name | VARCHAR(255) | Full name |
| email | VARCHAR(255) UNIQUE | Email address |
| phone | VARCHAR(50) | Phone number |
| education | TEXT | Education details |
| skills | TEXT | Comma-separated skills |
| experience | TEXT | Experience description |
| projects | TEXT | Projects list |
| certifications | TEXT | Certifications |
| resume_path | VARCHAR(500) | Path to uploaded file |
| created_date | DATETIME | Auto timestamp |
| updated_date | DATETIME | Auto on update |

### `jobs` table
| Column | Type | Description |
|--------|------|-------------|
| job_id | INT PK AUTO | Unique ID |
| job_title | VARCHAR(255) | Job title |
| department | VARCHAR(150) | Department |
| location | VARCHAR(150) | Location |
| job_type | VARCHAR(50) | Full-Time / Part-Time etc. |
| experience_level | VARCHAR(50) | Fresher / Junior / Senior etc. |
| salary_min | DECIMAL(12,2) | Minimum salary |
| salary_max | DECIMAL(12,2) | Maximum salary |
| description | TEXT | Job description |
| requirements | TEXT | Requirements text |
| responsibilities | TEXT | Responsibilities |
| skills_required | TEXT | Comma-separated required skills |
| benefits | TEXT | Benefits |
| status | VARCHAR(20) | Open / Closed / On Hold / Draft |
| openings | INT | Number of openings |
| posted_by | VARCHAR(255) | Recruiter name |
| deadline | DATE | Application deadline |
| certification | VARCHAR(255) | Required certification |
| created_date | DATETIME | Auto timestamp |
| updated_date | DATETIME | Auto on update |

---

## 12. Dependencies

```
streamlit>=1.35.0       # UI framework
PyMuPDF>=1.24.0         # PDF resume parsing
python-docx>=1.1.0      # DOCX resume parsing
spacy>=3.7.0            # NLP for profile extraction
pandas>=2.2.0           # Dataframes
mysql-connector-python>=8.4.0  # MySQL connection
plotly>=5.18.0          # Interactive charts
fpdf2>=2.7.0            # PDF report generation
```

Install all:
```bash
pip install -r requirements.txt
```

---

## 13. Grade System

Used consistently across all scoring pages and reports:

| Grade | Score Range | Color | Label |
|-------|------------|-------|-------|
| A+ | ≥ 85% | 🟢 Green `#10b981` | Excellent |
| A  | ≥ 70% | 🟢 Teal `#34d399` | Strong |
| B  | ≥ 55% | 🟡 Amber `#f59e0b` | Good |
| C  | ≥ 40% | 🟠 Orange `#fb923c` | Average |
| D  | < 40% | 🔴 Red `#ef4444` | Weak |

---

## 14. Common Errors & Fixes

### Download buttons not showing
**Cause:** PDF generation crashed silently due to non-latin-1 characters (em-dash `—`, `×`) in fpdf2 Helvetica font.  
**Fix:** Already fixed in `report_generator.py` — `_safe()` strips non-latin-1 chars, all hardcoded strings use ASCII.

### "Not enough horizontal space" error in PDF
**Cause:** `multi_cell(0, ...)` called after a label cell left 0 width remaining.  
**Fix:** Changed to `multi_cell(self.epw - 55, ...)` to use remaining effective page width.

### Charts not showing
**Cause:** No candidates or jobs in the database.  
**Fix:** Upload at least one resume and create at least one job posting first.

### Session state stale data
**Cause:** Navigating away and back keeps old `st.session_state` results.  
**Behavior:** This is intentional — results persist until you click the analyze button again with a new selection.

### MySQL connection error
**Cause:** Wrong credentials or MySQL not running.  
**Fix:** Check `config/settings.py` and ensure MySQL service is started.

### `certification` column missing
**Cause:** Old jobs table created before the column was added.  
**Fix:** Run in MySQL Workbench:
```sql
ALTER TABLE jobs ADD COLUMN certification VARCHAR(255) NOT NULL DEFAULT '';
```
