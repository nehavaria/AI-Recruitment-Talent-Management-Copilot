# Milestone 3 — Documentation

## Overview

Milestone 3 adds a full recruitment pipeline on top of the existing MySQL-backed system.
All modules live in `milestone3/`. No existing files (`db_manager.py`, `db_service.py`,
`candidate_service.py`) are modified. All storage uses MySQL exclusively.

---

## Module Reference

### 1. `ats_management_page.py` — ATS Management Page

**Purpose:** Candidate-centric ATS view. Loads every candidate from the `candidates` table
and lets recruiters update pipeline stage, recruiter name, resume score, and interview date.
Stage changes save to MySQL instantly on dropdown change.

**Key Functions:**

| Function | Description |
|---|---|
| `render(service)` | Main entry point. Initialises schema once per session, loads candidates, renders metric cards, filters, and per-candidate cards using `@st.fragment` to prevent full-page blink. |
| `_load_candidates()` | JOINs `candidates` + `ats_candidates` (WHERE `job_id IS NULL`) + `interview_schedule`. Returns one row per candidate. |
| `_stage_only(candidate_id, stage)` | UPDATE-first / INSERT-if-zero-rowcount. Called by the status dropdown `on_change`. |
| `_ats_upsert(candidate_id, stage, recruiter, resume_score)` | Full upsert returning `ats_id`. Used by the Save Details button. |
| `_save_schedule(ats_id, interview_date)` | Updates existing `interview_schedule` row or inserts a new one. |

**MySQL tables used:** `candidates` (read), `ats_candidates` (read/write), `interview_schedule` (read/write)

**Important design note:** `job_id IS NULL` is used as the identifier for management-page rows
because MySQL treats `NULL != NULL` in unique indexes — `ON DUPLICATE KEY UPDATE` never fires
for NULL keys. The UPDATE-first pattern is used instead.

---

### 2. `ats_management.py` — ATS Dashboard

**Purpose:** Job-linked ATS pipeline with Kanban board, Add/Edit form, Pipeline Table, and Stats.
Each candidate is tracked per job (`candidate_id + job_id` unique key).

**Tabs:**

| Tab | Description |
|---|---|
| 📋 Kanban Board | 5-column board (Applied → Rejected). Stage change via selectbox triggers `_update_stage()` + `st.rerun()`. |
| ➕ Add / Edit | Select job + candidate, set stage/recruiter/interview date/notes/feedback, save via `_upsert()`. |
| 📊 Pipeline Table | Filterable/sortable table of all pipeline records with inline stage change. |
| 📈 Stats | Total/Active/Selected/Rejected metrics + stage breakdown bar chart + top 5 by score. |

**Key Functions:**

| Function | Description |
|---|---|
| `_upsert(r)` | `ON DUPLICATE KEY UPDATE` insert/update for `ats_candidates`. Also writes to `recruiter_notes`, `interview_schedule`, `interview_feedback`. |
| `_get_all()` | Full JOIN across all 4 ATS tables, returns latest note/schedule/feedback per entry. |
| `_get_one(candidate_id, job_id)` | Same JOIN filtered to one candidate+job pair. |
| `_update_stage(candidate_id, job_id, stage)` | Single-field UPDATE for stage. |
| `_skill_score(candidate, job)` | Computes skill overlap % between candidate skills and job required skills. |

**MySQL tables used:** `ats_candidates`, `recruiter_notes`, `interview_schedule`, `interview_feedback`

---

### 3. `ats_dashboard.py` — ATS Dashboard (Session-State Kanban)

**Purpose:** Alternative ATS dashboard backed by a separate `ats_pipeline` table.
Uses `st.session_state` seeding to avoid DB reads on every rerun — no page blink.

**Tabs:**

| Tab | Description |
|---|---|
| 📋 Kanban Board | Groups candidates by live session_state stage value. Stage change writes to DB via `_update_stage()`. |
| 📊 Pipeline Table | Filterable table with inline stage change and recruiter notes save. |
| ✏️ Edit / Add | Add candidates to pipeline with job assignment. Edit stage, recruiter, score, interview date, notes, feedback. |
| 📈 Stats | Stage breakdown + top 5 by score. |

**Key Functions:**

| Function | Description |
|---|---|
| `_init_db()` | Creates `ats_pipeline` table if not exists. |
| `_load_all()` | Returns `{candidate_id: row}` dict from `ats_pipeline`. |
| `_add_to_pipeline(cid, job_id)` | `INSERT IGNORE` into `ats_pipeline`. |
| `_save_full(cid, ...)` | Full UPDATE of all fields for a pipeline row. |
| `_update_stage(cid, stage)` | Single-field stage UPDATE. |
| `_save_recruiter_notes(cid, notes)` | Updates recruiter_notes field. |
| `_seed(key, value)` | Writes to session_state only if key not already present — prevents overwriting live user changes. |

**MySQL tables used:** `ats_pipeline` (own table, separate from `ats_candidates`)

---

### 4. `candidate_search.py` — Advanced Candidate Search

**Purpose:** Full-text + multi-filter candidate search. Builds a SQLite FTS5 index from MySQL
candidates for fast keyword search. ATS stage is read from `ats.db` (SQLite).

**Filters available:** Keyword, Skills (multi-select), Experience contains, Location contains,
Education contains, Application Status, Resume Score range.

**Key Functions:**

| Function | Description |
|---|---|
| `_init_index()` | Creates `search_candidates` table + FTS5 virtual table in SQLite. |
| `_rebuild_index(candidates)` | Syncs all MySQL candidates into SQLite search index. |
| `_search(...)` | Runs FTS5 keyword search + applies all filters. Returns sorted results. |
| `_compute_score(c)` | Completeness score: 60% from filled fields + up to 40% from skill count. |
| `_get_ats_stages()` | Reads `{candidate_id: stage}` from `ats.db` SQLite file. |

**Storage:** SQLite `data/search_index.db` (search index only — not primary storage)

---

### 5. `candidate_timeline.py` — Candidate Activity Timeline

**Purpose:** Vertical timeline showing the full recruitment journey for a selected candidate —
from resume upload through ATS pipeline stages to final decision.

**Event types:** `resume_uploaded`, `resume_parsed`, `shortlisted`, `interview_scheduled`,
`interview_completed`, `feedback_added`, `selected`, `rejected`

**Key Functions:**

| Function | Description |
|---|---|
| `_fetch_events(candidate_id, candidate)` | Builds chronological event list from `candidates`, `ats_pipeline`, and `recruiter_feedback` tables. |
| `_render_timeline(events)` | Renders vertical timeline with icon, label, timestamp, and detail for each event. |
| `_candidate_header(c, event_count)` | Renders candidate avatar card with skills and event count. |

**MySQL tables read:** `candidates`, `ats_pipeline`, `recruiter_feedback`

---

### 6. `interview_scheduling.py` — Interview Scheduling

**Purpose:** Schedule interviews with candidate, interviewer, date, time, mode (Online/Offline),
meeting link, and notes. View upcoming and all past interviews.

**Tabs:**

| Tab | Description |
|---|---|
| ➕ Schedule Interview | Form to create a new interview record. |
| 📅 Upcoming Interviews | All interviews with date >= today, sorted by date/time. Delete button per row. |
| 📋 All Interviews | Full history with search + mode filter. Past interviews tagged. |

**Key Functions:**

| Function | Description |
|---|---|
| `_init_db()` | Creates `recruiter_interviews` table if not exists. |
| `_save_schedule(...)` | Inserts a new interview record. |
| `_load_upcoming()` | Fetches interviews with `interview_date >= today`. |
| `_load_all_schedules()` | Fetches all interviews ordered by date DESC. |
| `_delete_schedule(id)` | Deletes a single interview record. |

**MySQL tables used:** `recruiter_interviews`

---

### 7. `interview_questions.py` — Interview Questions Generator

**Purpose:** Generates role-specific interview questions using Groq AI (LLaMA 3.3 70B)
based on job description and candidate profile. Questions are categorised as Technical,
Behavioral, and Situational, each with Easy/Medium/Hard difficulty.

**Key Functions:**

| Function | Description |
|---|---|
| `_generate_via_groq(...)` | Calls Groq API with structured prompt. Falls back through 3 models on rate limit. Returns JSON with `technical`, `behavioral`, `situational` arrays. |
| `_render_by_difficulty(items, accent, empty_msg)` | Groups questions by difficulty, shows time estimate per group. |
| `_build_pdf(...)` | Generates downloadable PDF using `fpdf`. |
| `_build_docx(...)` | Generates downloadable DOCX using `python-docx`. |

**AI:** Groq API — models tried in order: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`

---

### 8. `interview_simulator.py` — AI Interview Simulator

**Purpose:** Conducts a 10-question AI interview with voice or text input. Each answer is
evaluated across 6 dimensions by Gemini (primary) or Groq (fallback). Full transcript
downloadable. Results persisted to MySQL via `interview_db.py`.

**Evaluation dimensions:** Technical, Communication, Confidence, Problem Solving, Grammar, Overall

**Key Functions:**

| Function | Description |
|---|---|
| `_generate_question(candidate, job, history, q_num)` | Generates next interview question via Groq, avoiding repeats. |
| `_evaluate(question, answer, job_title)` | Evaluates answer across 6 dimensions. Uses Gemini if key present, else Groq. Returns structured dict. |
| `_transcribe(audio_bytes)` | Transcribes WAV audio using Google Speech Recognition. |
| `_transcript_panel(history)` | Renders download button for full interview transcript. |

**AI:** Gemini 2.0 Flash (primary) / Groq LLaMA 3.3 70B (fallback)
**MySQL tables used:** `interview_sessions` (via `interview_db.py`)

---

### 9. `interview_report.py` — Interview Report Generator

**Purpose:** Generates comprehensive interview reports from simulator results or manual score
entry. Supports text and CSV download. Loads past sessions from MySQL.

**Tabs:**

| Tab | Description |
|---|---|
| 🎤 From Simulator | Loads latest simulator session from MySQL. Shows grade, recommendation, per-question breakdown. Download as TXT or CSV. |
| 📝 Manual Entry | Enter Technical/Communication/Problem Solving/Culture Fit scores manually. Weighted overall score. Download as TXT. |

**Grade scale:** A+ (≥85%), A (≥70%), B (≥55%), C (≥40%), D (<40%)

**Key Functions:**

| Function | Description |
|---|---|
| `_grade(score)` | Returns (grade_letter, color, verdict) tuple. |
| `_recommendation(score)` | Returns (title, description) hiring recommendation. |
| `_build_text_report(report)` | Builds plain-text report string. |
| `_build_csv_report(report)` | Builds CSV report string. |

**MySQL tables read:** `interview_sessions` (via `interview_db.py`)

---

### 10. `interview_db.py` — Interview Session Persistence

**Purpose:** MySQL persistence layer for simulator reports. Stores full session JSON so
reports survive Streamlit restarts.

**Key Functions:**

| Function | Description |
|---|---|
| `init_db()` | Creates `interview_sessions` table if not exists. |
| `save_report(report)` | Inserts full report JSON. Returns new `session_id`. |
| `load_latest_report(candidate_id)` | Loads most recent report, optionally filtered by candidate. |
| `load_all_sessions()` | Returns summary rows for all sessions (no full JSON). |
| `load_session_by_id(session_id)` | Loads full report by session ID. |
| `delete_session(session_id)` | Deletes a session record. |

**MySQL tables used:** `interview_sessions`

---

### 11. `recruiter_feedback.py` — Recruiter Feedback

**Purpose:** Star-rating feedback system. Recruiters submit 1–5 star ratings with comments
per candidate per pipeline stage. View per-candidate history and all feedback with filters.

**Tabs:**

| Tab | Description |
|---|---|
| 📝 Submit Feedback | Select candidate, enter recruiter name, pick stage, choose star rating, add comment. |
| 📋 Candidate History | View all feedback for a selected candidate with avg rating summary. |
| 🗂️ All Feedback | All feedback across all candidates with search + rating + stage filters. |

**Key Functions:**

| Function | Description |
|---|---|
| `_init_db()` | Creates `recruiter_feedback` table if not exists. |
| `_save_feedback(...)` | Inserts a new feedback record. |
| `_load_feedback(candidate_id)` | Loads all feedback for one candidate, newest first. |
| `_load_all_feedback()` | Loads all feedback JOINed with candidate name. |
| `_star_selector(key)` | Renders styled 1–5 star radio selector. Returns int. |

**MySQL tables used:** `recruiter_feedback`

---

## Database Schema — ATS Tables (`database/ats_schema.py`)

| Table | Purpose |
|---|---|
| `ats_candidates` | Pipeline entry per candidate. `job_id` nullable (NULL = management page row). Unique key on `(candidate_id, job_id)`. FK to `candidates`. |
| `recruiter_notes` | Notes per ATS entry. FK to `ats_candidates`. |
| `interview_schedule` | Interview dates per ATS entry. FK to `ats_candidates`. |
| `interview_feedback` | Interview feedback per ATS entry. FK to `ats_candidates` + `interview_schedule`. |

**Other tables created by milestone 3 modules:**

| Table | Created by | Purpose |
|---|---|---|
| `ats_pipeline` | `ats_dashboard.py` | Job-linked pipeline for the dashboard view |
| `recruiter_interviews` | `interview_scheduling.py` | Scheduled interview records |
| `recruiter_feedback` | `recruiter_feedback.py` | Star-rating feedback records |
| `interview_sessions` | `interview_db.py` | Simulator session JSON storage |

---

## Key Design Decisions

**MySQL NULL uniqueness**
`UNIQUE KEY (candidate_id, job_id)` with `NULL job_id` — MySQL treats each NULL as distinct,
so `ON DUPLICATE KEY UPDATE` never fires. The UPDATE-first / INSERT-if-zero-rowcount pattern
is used in `_stage_only()` and `_ats_upsert()`.

**No page blink on dropdown change**
`@st.fragment` wraps each candidate card in `ats_management_page.py` so only that card reruns
on stage change — the rest of the page stays still.

**Schema init guard**
`init_ats_schema()` is guarded by `st.session_state["ats_schema_ready"]` so it runs only once
per browser session, not on every rerun.

**No SQLite for primary data**
All candidate, job, and ATS data is stored in MySQL. SQLite is used only for the search index
(`candidate_search.py`) and simulator session cache (`interview_db.py` previously used SQLite
but was migrated to MySQL).

**No existing modules modified**
`db_manager.py`, `db_service.py`, `candidate_service.py` are never touched.
`app.py` receives only new menu entry additions.

---

## App Registration (`app.py`)

All milestone 3 pages are registered in `app.py` under the sidebar menu:

```python
"📌 ATS Dashboard"          → milestone3.ats_management
"🗂️ ATS Dashboard (New)"   → milestone3.ats_dashboard
"🗂️ ATS Management Page"   → milestone3.ats_management_page
"🔎 Advanced Search"        → milestone3.candidate_search
"🕐 Candidate Timeline"     → milestone3.candidate_timeline
"📅 Interview Scheduling"   → milestone3.interview_scheduling
"❓ Interview Questions"    → milestone3.interview_questions
"🤖 Interview Simulator"    → milestone3.interview_simulator
"📄 Interview Report"       → milestone3.interview_report
"⭐ Recruiter Feedback"     → milestone3.recruiter_feedback
```

---

## Dependencies Added

```
mysql-connector-python
groq
google-genai
speechrecognition
fpdf2
python-docx
```
