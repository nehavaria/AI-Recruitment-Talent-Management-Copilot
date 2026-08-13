"""
Milestone 3 — Advanced Candidate Search
SQLite-backed search index built from MySQL candidates + ATS pipeline data.
Filters: Skill, Experience, Location, Education, Resume Score, Application Status.
Keyword search across name / email / skills / experience / education.
Does NOT modify any existing module.
"""

import html
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from services.candidate_service import CandidateService
from ui.components import page_header

# ── SQLite search index path (same data/ folder as ats.db) ────────────────
_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "search_index.db"

# ── ATS db path (read pipeline stage from it) ─────────────────────────────
_ATS_PATH = Path(__file__).resolve().parent.parent / "data" / "ats.db"

_STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

_STAGE_STYLE = {
    "Applied":   ("#3b82f6", "rgba(59,130,246,0.12)",  "rgba(59,130,246,0.3)"),
    "Screening": ("#8b5cf6", "rgba(139,92,246,0.12)",  "rgba(139,92,246,0.3)"),
    "Interview": ("#f59e0b", "rgba(245,158,11,0.12)",  "rgba(245,158,11,0.3)"),
    "Selected":  ("#10b981", "rgba(16,185,129,0.12)",  "rgba(16,185,129,0.3)"),
    "Rejected":  ("#ef4444", "rgba(239,68,68,0.12)",   "rgba(239,68,68,0.3)"),
}
_STAGE_ICONS = {
    "Applied": "📥", "Screening": "🔍", "Interview": "🎤",
    "Selected": "✅", "Rejected": "❌",
}


# ── SQLite helpers ─────────────────────────────────────────────────────────

@contextmanager
def _db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_index() -> None:
    with _db(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_candidates (
                candidate_id  INTEGER PRIMARY KEY,
                name          TEXT,
                email         TEXT,
                phone         TEXT,
                skills        TEXT,
                experience    TEXT,
                education     TEXT,
                location      TEXT,
                resume_score  REAL DEFAULT 0,
                keyword_blob  TEXT
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts
            USING fts5(candidate_id UNINDEXED, keyword_blob, content='search_candidates',
                       content_rowid='candidate_id')
        """)


def _rebuild_index(candidates: list[dict]) -> None:
    """Sync MySQL candidates into the SQLite search index."""
    with _db(_DB_PATH) as conn:
        conn.execute("DELETE FROM search_candidates")
        conn.execute("DELETE FROM search_fts")
        rows = []
        for c in candidates:
            score = _compute_score(c)
            blob  = " ".join(filter(None, [
                c.get("name") or "",
                c.get("email") or "",
                c.get("skills") or "",
                c.get("experience") or "",
                c.get("education") or "",
                c.get("phone") or "",
            ])).lower()
            rows.append((
                c["candidate_id"],
                (c.get("name") or "").splitlines()[0].strip(),
                c.get("email") or "",
                c.get("phone") or "",
                c.get("skills") or "",
                c.get("experience") or "",
                c.get("education") or "",
                _extract_location(c),
                score,
                blob,
            ))
        conn.executemany("""
            INSERT INTO search_candidates
                (candidate_id, name, email, phone, skills, experience,
                 education, location, resume_score, keyword_blob)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.executemany(
            "INSERT INTO search_fts(candidate_id, keyword_blob) VALUES (?,?)",
            [(r[0], r[9]) for r in rows]
        )


def _get_ats_stages() -> dict[int, str]:
    """Return {candidate_id: latest_stage} from ats.db if it exists."""
    if not _ATS_PATH.exists():
        return {}
    try:
        with _db(_ATS_PATH) as conn:
            rows = conn.execute(
                "SELECT candidate_id, stage FROM ats_pipeline"
            ).fetchall()
        # If a candidate has multiple jobs, take the most recent stage
        result: dict[int, str] = {}
        for r in rows:
            result[r["candidate_id"]] = r["stage"]
        return result
    except Exception:
        return {}


def _compute_score(c: dict) -> float:
    """Simple completeness score based on filled fields."""
    fields = ["name", "email", "phone", "skills", "experience", "education"]
    filled = sum(1 for f in fields if (c.get(f) or "").strip())
    skill_count = len([s for s in (c.get("skills") or "").split(",") if s.strip()])
    base = round(filled / len(fields) * 60, 1)
    skill_bonus = min(40.0, skill_count * 4.0)
    return min(100.0, base + skill_bonus)


def _extract_location(c: dict) -> str:
    """Try to extract location from experience or education text."""
    for field in ["experience", "education"]:
        text = c.get(field) or ""
        for line in text.splitlines():
            line = line.strip()
            if any(kw in line.lower() for kw in [
                "bangalore", "mumbai", "delhi", "hyderabad", "chennai", "pune",
                "kolkata", "remote", "india", "usa", "uk", "london", "new york",
                "singapore", "dubai", "canada", "australia",
            ]):
                return line[:60]
    return ""


def _search(
    keyword: str,
    skills: list[str],
    min_score: float,
    max_score: float,
    education_kw: str,
    experience_kw: str,
    location_kw: str,
    status_filter: str,
    ats_stages: dict[int, str],
) -> list[dict]:
    with _db(_DB_PATH) as conn:
        if keyword.strip():
            # FTS search
            safe_kw = keyword.strip().replace('"', '""')
            fts_ids = {
                r["candidate_id"]
                for r in conn.execute(
                    "SELECT candidate_id FROM search_fts WHERE keyword_blob MATCH ?",
                    (safe_kw,)
                ).fetchall()
            }
            if not fts_ids:
                return []
            placeholders = ",".join("?" * len(fts_ids))
            rows = conn.execute(
                f"SELECT * FROM search_candidates WHERE candidate_id IN ({placeholders})",
                list(fts_ids)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM search_candidates").fetchall()

    results = [dict(r) for r in rows]

    # Attach ATS stage
    for r in results:
        r["ats_stage"] = ats_stages.get(r["candidate_id"], "")

    # Apply filters
    if skills:
        def has_skills(r):
            cand_skills = {s.strip().lower() for s in (r.get("skills") or "").split(",") if s.strip()}
            return all(s.lower() in cand_skills for s in skills)
        results = [r for r in results if has_skills(r)]

    results = [r for r in results if min_score <= r.get("resume_score", 0) <= max_score]

    if education_kw.strip():
        q = education_kw.lower()
        results = [r for r in results if q in (r.get("education") or "").lower()]

    if experience_kw.strip():
        q = experience_kw.lower()
        results = [r for r in results if q in (r.get("experience") or "").lower()]

    if location_kw.strip():
        q = location_kw.lower()
        results = [r for r in results if q in (r.get("location") or "").lower()
                   or q in (r.get("experience") or "").lower()
                   or q in (r.get("education") or "").lower()]

    if status_filter and status_filter != "All":
        results = [r for r in results if r.get("ats_stage") == status_filter]

    return sorted(results, key=lambda r: r.get("resume_score", 0), reverse=True)


# ── UI helpers ─────────────────────────────────────────────────────────────

def _stage_badge(stage: str) -> str:
    if not stage:
        return "<span style='color:#475569;font-size:0.7rem'>Not in ATS</span>"
    clr, bg, border = _STAGE_STYLE.get(stage, ("#94a3b8", "rgba(148,163,184,0.12)", "rgba(148,163,184,0.3)"))
    icon = _STAGE_ICONS.get(stage, "")
    return (
        f"<span style='background:{bg};color:{clr};border:1px solid {border};"
        f"padding:2px 10px;border-radius:20px;font-size:0.68rem;font-weight:700'>"
        f"{icon} {html.escape(stage)}</span>"
    )


def _skill_pills(skills_str: str, highlight: list[str]) -> str:
    hl = {s.lower() for s in highlight}
    pills = []
    for s in (skills_str or "").split(","):
        s = s.strip()
        if not s:
            continue
        if s.lower() in hl:
            pills.append(
                f"<span style='background:rgba(139,92,246,0.25);color:#c4b5fd;"
                f"border:1px solid rgba(139,92,246,0.5);padding:2px 10px;"
                f"border-radius:20px;font-size:0.68rem;font-weight:700;margin:2px'>{html.escape(s)}</span>"
            )
        else:
            pills.append(
                f"<span style='background:rgba(255,255,255,0.06);color:#94a3b8;"
                f"border:1px solid rgba(255,255,255,0.1);padding:2px 10px;"
                f"border-radius:20px;font-size:0.68rem;margin:2px'>{html.escape(s)}</span>"
            )
    return "".join(pills) or "<span style='color:#475569;font-size:0.72rem'>—</span>"


def _result_card(r: dict, highlight_skills: list[str], keyword: str) -> None:
    score     = r.get("resume_score", 0)
    score_clr = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    name      = html.escape(r.get("name") or "Unknown")
    email     = html.escape(r.get("email") or "—")
    phone     = html.escape(r.get("phone") or "—")
    location  = html.escape(r.get("location") or "—")
    stage_html = _stage_badge(r.get("ats_stage", ""))

    with st.container(border=True):
        h1, h2, h3 = st.columns([4, 3, 1])
        with h1:
            st.markdown(
                f"<div style='font-size:0.95rem;font-weight:800;color:#f1f5f9'>{name}</div>"
                f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:3px'>"
                f"📧 {email} &nbsp;·&nbsp; 📞 {phone} &nbsp;·&nbsp; 📍 {location}</div>",
                unsafe_allow_html=True,
            )
        with h2:
            st.markdown(
                f"<div style='padding-top:4px'>{stage_html}</div>",
                unsafe_allow_html=True,
            )
        with h3:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:1.2rem;font-weight:900;color:{score_clr}'>{score}%</div>"
                f"<div style='font-size:0.6rem;color:#64748b'>Score</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            f"<div style='margin-top:8px;line-height:2'>"
            f"{_skill_pills(r.get('skills',''), highlight_skills)}</div>",
            unsafe_allow_html=True,
        )

        with st.expander("📄 Details"):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Education**")
                st.caption(r.get("education") or "—")
            with d2:
                st.markdown("**Experience**")
                exp_lines = (r.get("experience") or "—").splitlines()
                st.caption("\n".join(exp_lines[:6]))


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "🔎 Advanced Candidate Search",
        "Search and filter candidates by skill, experience, location, education, score, and ATS status.",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    if not candidates:
        st.info("No candidates found — upload resumes first.")
        return

    # Build / refresh index
    _init_index()

    # Rebuild button + auto-rebuild if index is empty
    with _db(_DB_PATH) as conn:
        count = conn.execute("SELECT COUNT(*) FROM search_candidates").fetchone()[0]

    col_info, col_btn = st.columns([5, 1])
    with col_info:
        st.markdown(
            f"<div style='font-size:0.78rem;color:#94a3b8;padding-top:8px'>"
            f"🗂 Index: <b style='color:#f1f5f9'>{count}</b> candidates &nbsp;·&nbsp; "
            f"MySQL source: <b style='color:#f1f5f9'>{len(candidates)}</b> total</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🔄 Sync Index", use_container_width=True) or count == 0:
            _rebuild_index(candidates)
            st.rerun()

    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.75rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:14px'>"
            "🔍 Search & Filters</div>",
            unsafe_allow_html=True,
        )

        keyword = st.text_input(
            "🔑 Keyword Search",
            placeholder="Search name, email, skills, experience, education...",
            key="cs_keyword",
        )

        f1, f2, f3 = st.columns(3)
        with f1:
            # Collect all unique skills from index
            with _db(_DB_PATH) as conn:
                all_skills_raw = conn.execute(
                    "SELECT skills FROM search_candidates WHERE skills != ''"
                ).fetchall()
            skill_set = sorted({
                s.strip().title()
                for row in all_skills_raw
                for s in (row["skills"] or "").split(",")
                if s.strip()
            })
            sel_skills = st.multiselect("🛠 Skills", skill_set, key="cs_skills")

        with f2:
            experience_kw = st.text_input(
                "💼 Experience contains",
                placeholder="e.g. Python developer, 3 years...",
                key="cs_exp",
            )
            location_kw = st.text_input(
                "📍 Location contains",
                placeholder="e.g. Bangalore, Remote...",
                key="cs_loc",
            )

        with f3:
            education_kw = st.text_input(
                "🎓 Education contains",
                placeholder="e.g. B.Tech, Computer Science...",
                key="cs_edu",
            )
            status_filter = st.selectbox(
                "📌 Application Status",
                ["All"] + _STAGES,
                key="cs_status",
            )

        score_min, score_max = st.slider(
            "🎯 Resume Score Range (%)",
            0, 100, (0, 100),
            key="cs_score",
        )

        c_reset, c_count = st.columns([1, 4])
        with c_reset:
            if st.button("🗑 Clear Filters", use_container_width=True):
                for k in ["cs_keyword", "cs_skills", "cs_exp", "cs_loc",
                          "cs_edu", "cs_status", "cs_score"]:
                    st.session_state.pop(k, None)
                st.rerun()

    # ── Run search ─────────────────────────────────────────────────────────
    ats_stages = _get_ats_stages()

    results = _search(
        keyword        = keyword,
        skills         = sel_skills,
        min_score      = score_min,
        max_score      = score_max,
        education_kw   = education_kw,
        experience_kw  = experience_kw,
        location_kw    = location_kw,
        status_filter  = status_filter,
        ats_stages     = ats_stages,
    )

    # ── Results header ─────────────────────────────────────────────────────
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin:16px 0 12px'>"
        f"<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0'>Search Results</div>"
        f"<div style='background:rgba(139,92,246,0.2);color:#c4b5fd;border:1px solid rgba(139,92,246,0.4);"
        f"padding:2px 12px;border-radius:20px;font-size:0.75rem;font-weight:700'>"
        f"{len(results)} found</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not results:
        st.info("No candidates match your filters. Try adjusting the search criteria.")
        return

    # ── Sort bar ───────────────────────────────────────────────────────────
    sb1, sb2 = st.columns([3, 1])
    with sb2:
        sort_by = st.selectbox(
            "Sort",
            ["Score ↓", "Score ↑", "Name A→Z", "Name Z→A"],
            key="cs_sort",
            label_visibility="collapsed",
        )

    if sort_by == "Score ↑":
        results = sorted(results, key=lambda r: r.get("resume_score", 0))
    elif sort_by == "Name A→Z":
        results = sorted(results, key=lambda r: (r.get("name") or "").lower())
    elif sort_by == "Name Z→A":
        results = sorted(results, key=lambda r: (r.get("name") or "").lower(), reverse=True)

    # ── Result cards ───────────────────────────────────────────────────────
    for r in results:
        _result_card(r, sel_skills, keyword)
