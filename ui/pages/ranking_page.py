"""Candidate Ranking page — rank all candidates against a selected job."""

import html
import pandas as pd
import streamlit as st

from services.candidate_service import CandidateService
from ui.components import empty_state, page_header


# ══════════════════════════════════════════════
#  SCORING LOGIC (same as hiring_score_page)
# ══════════════════════════════════════════════

def _normalize(raw: str) -> set[str]:
    return {s.strip().lower() for s in (raw or "").split(",") if s.strip()}


def _skill_score(candidate_skills: str, job_skills: str) -> tuple[float, int, int]:
    resume  = _normalize(candidate_skills)
    jd      = _normalize(job_skills)
    if not jd:
        return 100.0, 0, 0
    matched = resume & jd
    return round((len(matched) / len(jd)) * 100, 1), len(matched), len(jd)


def _experience_score(candidate_exp: str, job_exp_level: str) -> float:
    level_map = {"fresher": 0, "junior": 1, "mid-level": 2,
                 "senior": 3, "lead": 4, "manager": 5}
    jd_rank        = level_map.get((job_exp_level or "").lower().strip(), -1)
    exp_lower      = (candidate_exp or "").lower()
    candidate_rank = -1
    for level, rank in level_map.items():
        if level in exp_lower:
            candidate_rank = max(candidate_rank, rank)
    if jd_rank == -1:        return 100.0
    if candidate_rank == -1: return 50.0
    if candidate_rank >= jd_rank: return 100.0
    return round(max(0, (candidate_rank / jd_rank) * 100), 1)


def _certification_score(candidate_certs: str, job_certification: str) -> float:
    if not job_certification or not job_certification.strip():
        return 50.0
    certs_lower = (candidate_certs or "").lower()
    jd_words    = set(job_certification.lower().replace(",", " ").split())
    matched     = any(w in certs_lower for w in jd_words if len(w) > 2)
    return 100.0 if matched else 0.0


def _overall_score(skill: float, exp: float, cert: float) -> float:
    return round(skill * 0.70 + exp * 0.20 + cert * 0.10, 1)


def _grade(score: float) -> tuple[str, str, str]:
    if score >= 85: return "A+", "#10b981", "Excellent"
    if score >= 70: return "A",  "#34d399", "Strong"
    if score >= 55: return "B",  "#f59e0b", "Good"
    if score >= 40: return "C",  "#fb923c", "Average"
    return              "D",  "#ef4444", "Weak"


# ══════════════════════════════════════════════
#  RANK ALL CANDIDATES
# ══════════════════════════════════════════════

def _rank_all(candidates: list[dict], job: dict) -> list[dict]:
    """Score every candidate against the job and return sorted list."""
    ranked = []
    for c in candidates:
        s_score, matched, total_jd = _skill_score(
            c.get("skills", ""), job.get("skills_required", "")
        )
        e_score = _experience_score(
            c.get("experience", ""), job.get("experience_level", "")
        )
        c_score = _certification_score(
            c.get("certifications", ""), job.get("certification", "")
        )
        o_score = _overall_score(s_score, e_score, c_score)
        grade, color, verdict = _grade(o_score)

        ranked.append({
            "candidate_id": c.get("candidate_id"),
            "name":         (c.get("name") or "Unknown").splitlines()[0],
            "email":        c.get("email") or "—",
            "overall":      o_score,
            "skill":        s_score,
            "experience":   e_score,
            "cert":         c_score,
            "matched":      matched,
            "total_jd":     total_jd,
            "grade":        grade,
            "color":        color,
            "verdict":      verdict,
        })

    # Sort descending by overall score
    ranked.sort(key=lambda x: x["overall"], reverse=True)

    # Assign rank
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    return ranked


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

_MEDAL_STYLES = {
    1: ("linear-gradient(135deg,#f59e0b,#fbbf24)", "rgba(245,158,11,0.2)", "#fcd34d"),
    2: ("linear-gradient(135deg,#94a3b8,#cbd5e1)", "rgba(148,163,184,0.2)", "#e2e8f0"),
    3: ("linear-gradient(135deg,#fb923c,#f97316)", "rgba(251,146,60,0.2)",  "#fed7aa"),
}


def _podium_card(r: dict) -> None:
    """Top-3 medal card."""
    rank   = r["rank"]
    medal  = _MEDALS[rank]
    grad, bg, text = _MEDAL_STYLES[rank]
    clr    = r["color"]

    st.markdown(
        f"""
        <div style="background:{bg};border-radius:20px;padding:24px 20px;
                    border:1px solid {text}40;text-align:center;
                    box-shadow:0 6px 28px {text}20;height:100%">
            <div style="font-size:2.8rem;margin-bottom:6px">{medal}</div>
            <div style="font-size:0.65rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;letter-spacing:0.1em">Rank #{rank}</div>
            <div style="font-size:1rem;font-weight:800;color:#f1f5f9;
                        margin:8px 0 4px;white-space:nowrap;overflow:hidden;
                        text-overflow:ellipsis">{html.escape(r['name'])}</div>
            <div style="font-size:0.72rem;color:#94a3b8;margin-bottom:14px;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                ✉ {html.escape(r['email'])}</div>
            <div style="font-size:2.2rem;font-weight:900;
                        background:{grad};
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        letter-spacing:-2px;line-height:1">{r['overall']}%</div>
            <div style="font-size:0.75rem;font-weight:700;color:{clr};margin-top:6px">
                {r['grade']} — {r['verdict']}</div>
            <div style="margin-top:12px">
                <div style="background:rgba(255,255,255,0.08);border-radius:8px;
                            height:6px;overflow:hidden">
                    <div style="background:{grad};height:100%;
                                width:{r['overall']}%;border-radius:8px"></div>
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;
                        margin-top:12px;font-size:0.7rem;color:#64748b">
                <span>🛠 {r['skill']}%</span>
                <span>💼 {r['experience']}%</span>
                <span>🏅 {r['cert']}%</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _rank_row(r: dict) -> None:
    """Single leaderboard row card for rank 4+."""
    clr   = r["color"]
    rank  = r["rank"]

    with st.container(border=True):
        c1, c2, c3, c4, c5, c6 = st.columns([1, 4, 2, 2, 2, 2])

        with c1:
            st.markdown(
                f"<div style='font-size:1.3rem;font-weight:900;color:#64748b;"
                f"text-align:center;padding-top:8px'>#{rank}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div style='padding-top:4px'>"
                f"<div style='font-weight:700;font-size:0.92rem;color:#f1f5f9'>"
                f"{html.escape(r['name'])}</div>"
                f"<div style='font-size:0.72rem;color:#64748b;margin-top:2px'>"
                f"✉ {html.escape(r['email'])}</div></div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.metric("Overall", f"{r['overall']}%")
        with c4:
            st.metric("🛠 Skill", f"{r['skill']}%")
        with c5:
            st.metric("💼 Exp", f"{r['experience']}%")
        with c6:
            grade_badge = f"<span style='background:{clr}20;color:{clr};" \
                          f"padding:3px 10px;border-radius:20px;font-size:0.75rem;" \
                          f"font-weight:700;border:1px solid {clr}40'>" \
                          f"{r['grade']} {r['verdict']}</span>"
            st.markdown(
                f"<div style='padding-top:10px'>{grade_badge}</div>",
                unsafe_allow_html=True,
            )
        # Progress bar for overall score
        st.progress(int(r["overall"]) / 100)


# ══════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "📊 Candidate Ranking",
        "All candidates scored and ranked against a job — best fit at the top.",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    # ── Job selector ───────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;"
            "margin-bottom:12px'>Select Job to Rank Against</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([4, 1])
        with col1:
            job_options = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
            sel_job_key = st.selectbox(
                "💼 Job Description",
                list(job_options.keys()),
                key="rank_job",
                label_visibility="collapsed",
            )
            sel_job = job_options[sel_job_key]
        with col2:
            rank_btn = st.button("📊 Rank All", type="primary",
                                 use_container_width=True)

    if not rank_btn and "rank_result" not in st.session_state:
        st.info("👆 Select a Job above and click **Rank All** to score every candidate.")
        return

    if rank_btn:
        st.session_state.rank_result = {
            "job":    sel_job,
            "ranked": _rank_all(candidates, sel_job),
        }

    ranked    = st.session_state.rank_result["ranked"]
    job       = st.session_state.rank_result["job"]
    job_title = job.get("job_title") or "—"
    total     = len(ranked)

    st.divider()

    # ── Summary metrics ────────────────────────────────────────────────────
    avg_score  = round(sum(r["overall"] for r in ranked) / total, 1) if total else 0
    top_score  = ranked[0]["overall"] if ranked else 0
    strong     = sum(1 for r in ranked if r["overall"] >= 70)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👥 Total Candidates", total)
    m2.metric("🏆 Top Score",        f"{top_score}%")
    m3.metric("📊 Average Score",    f"{avg_score}%")
    m4.metric("✅ Strong Matches",   strong)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Top 3 podium ───────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
        "margin-bottom:16px'>🏅 Top 3 Candidates</div>",
        unsafe_allow_html=True,
    )

    top3 = ranked[:3]
    cols = st.columns(len(top3))
    for col, r in zip(cols, top3):
        with col:
            _podium_card(r)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Full leaderboard (rank 4+) ─────────────────────────────────────────
    if total > 3:
        st.markdown(
            "<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
            "margin-bottom:12px'>📋 Full Leaderboard</div>",
            unsafe_allow_html=True,
        )
        for r in ranked[3:]:
            _rank_row(r)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Dataframe table ────────────────────────────────────────────────────
    with st.expander("📄 Full Rankings Table", expanded=False):
        df = pd.DataFrame([
            {
                "Rank":         r["rank"],
                "Name":         r["name"],
                "Email":        r["email"],
                "Overall %":    r["overall"],
                "Skill %":      r["skill"],
                "Experience %": r["experience"],
                "Cert %":       r["cert"],
                "Grade":        r["grade"],
                "Verdict":      r["verdict"],
                "Matched":      f"{r['matched']}/{r['total_jd']} skills",
            }
            for r in ranked
        ])
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank":         st.column_config.NumberColumn(width="small"),
                "Overall %":    st.column_config.ProgressColumn(
                                    "Overall %", min_value=0, max_value=100, format="%d%%"),
                "Skill %":      st.column_config.ProgressColumn(
                                    "Skill %",   min_value=0, max_value=100, format="%d%%"),
                "Experience %": st.column_config.ProgressColumn(
                                    "Exp %",     min_value=0, max_value=100, format="%d%%"),
                "Cert %":       st.column_config.ProgressColumn(
                                    "Cert %",    min_value=0, max_value=100, format="%d%%"),
            },
        )
