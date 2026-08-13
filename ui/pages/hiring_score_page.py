"""Hiring Score page — weighted scoring engine for candidate vs job."""

import html
import streamlit as st

from reports.report_generator import hiring_score_csv, hiring_score_pdf

from services.candidate_service import CandidateService
from ui.components import empty_state, page_header


# ══════════════════════════════════════════════
#  SCORING LOGIC
# ══════════════════════════════════════════════

def _normalize(raw: str) -> set[str]:
    return {s.strip().lower() for s in (raw or "").split(",") if s.strip()}


def _skill_score(candidate_skills: str, job_skills: str) -> tuple[float, int, int]:
    """Returns (score 0-100, matched_count, total_jd_count)."""
    resume = _normalize(candidate_skills)
    jd     = _normalize(job_skills)
    if not jd:
        return 100.0, 0, 0
    matched = resume & jd
    return round((len(matched) / len(jd)) * 100, 1), len(matched), len(jd)


def _experience_score(candidate_exp: str, job_exp_level: str) -> float:
    """Returns score 0-100 based on experience level match."""
    level_map = {
        "fresher": 0, "junior": 1, "mid-level": 2,
        "senior": 3, "lead": 4, "manager": 5,
    }
    jd_rank   = level_map.get((job_exp_level or "").lower().strip(), -1)
    exp_lower = (candidate_exp or "").lower()

    candidate_rank = -1
    for level, rank in level_map.items():
        if level in exp_lower:
            candidate_rank = max(candidate_rank, rank)

    # If JD has no level specified → full score
    if jd_rank == -1:
        return 100.0
    # If candidate level unknown → partial score
    if candidate_rank == -1:
        return 50.0
    # Meets or exceeds → full score; below → proportional
    if candidate_rank >= jd_rank:
        return 100.0
    return round(max(0, (candidate_rank / jd_rank) * 100), 1)


def _certification_score(candidate_certs: str, job_certification: str) -> float:
    """Returns 100 if cert matched, 50 if no cert required, 0 if missing."""
    if not job_certification or not job_certification.strip():
        return 50.0   # not required → neutral
    certs_lower = (candidate_certs or "").lower()
    jd_words    = set(job_certification.lower().replace(",", " ").split())
    matched     = any(w in certs_lower for w in jd_words if len(w) > 2)
    return 100.0 if matched else 0.0


def _overall_score(skill: float, exp: float, cert: float) -> float:
    """70% skills + 20% experience + 10% certifications."""
    return round(skill * 0.70 + exp * 0.20 + cert * 0.10, 1)


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════

def _grade(score: float) -> tuple[str, str, str]:
    """Returns (grade letter, color, label)."""
    if score >= 85:
        return "A+", "#10b981", "Excellent"
    if score >= 70:
        return "A",  "#34d399", "Strong"
    if score >= 55:
        return "B",  "#f59e0b", "Good"
    if score >= 40:
        return "C",  "#fb923c", "Average"
    return     "D",  "#ef4444", "Weak"


def _score_card(label: str, score: float, icon: str,
                color: str, weight: str) -> None:
    """Render a single score card with progress bar."""
    grade, clr, verdict = _grade(score)
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,0.04);border-radius:18px;
                    padding:22px 24px;border:1px solid {clr}30;
                    box-shadow:0 4px 20px {clr}15;margin-bottom:4px">
            <div style="display:flex;justify-content:space-between;
                        align-items:flex-start;margin-bottom:14px">
                <div>
                    <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;
                                text-transform:uppercase;letter-spacing:0.1em">
                        {icon} {label}</div>
                    <div style="font-size:0.72rem;color:#64748b;margin-top:3px">
                        Weight: {weight}</div>
                </div>
                <div style="background:linear-gradient(135deg,{clr},{clr}99);
                            color:#fff;font-weight:900;font-size:1rem;
                            padding:6px 14px;border-radius:12px;
                            box-shadow:0 2px 10px {clr}40">{grade}</div>
            </div>
            <div style="font-size:2.4rem;font-weight:900;
                        background:linear-gradient(135deg,{clr},#a78bfa);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        letter-spacing:-2px;line-height:1;margin-bottom:12px">
                {score}%</div>
            <div style="font-size:0.78rem;color:{clr};font-weight:600;
                        margin-bottom:8px">{verdict}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(int(score) / 100)


def _overall_card(score: float, name: str, job_title: str) -> None:
    """Big overall score card."""
    grade, clr, verdict = _grade(score)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(124,58,237,0.15),
                    rgba(37,99,235,0.1));border-radius:24px;padding:32px 36px;
                    border:1px solid {clr}40;
                    box-shadow:0 8px 40px {clr}20;text-align:center;margin-bottom:8px">
            <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px">
                🏆 Overall Hiring Score
            </div>
            <div style="font-size:5rem;font-weight:900;
                        background:linear-gradient(135deg,{clr},#a78bfa);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        letter-spacing:-4px;line-height:1">{score}%</div>
            <div style="font-size:1.8rem;font-weight:900;color:{clr};
                        margin:8px 0 4px">{grade} — {verdict}</div>
            <div style="font-size:0.85rem;color:#94a3b8;margin-top:6px">
                {html.escape(name)} &nbsp;⚡&nbsp; {html.escape(job_title)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(int(score) / 100)


# ══════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "🏆 Hiring Score",
        "Weighted scoring engine — Skills 70% · Experience 20% · Certifications 10%",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    # ── Selection ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;"
            "margin-bottom:12px'>Select Candidate & Job</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            job_options = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
            sel_job_key = st.selectbox("💼 Job Description",
                                       list(job_options.keys()), key="hs_job")
            sel_job = job_options[sel_job_key]
        with col2:
            cand_options = {
                f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                for c in candidates
            }
            sel_cand_key = st.selectbox("👤 Candidate",
                                        list(cand_options.keys()), key="hs_cand")
            sel_cand = cand_options[sel_cand_key]

        calc = st.button("⚡ Calculate Hiring Score", type="primary",
                         use_container_width=True)

    if not calc and "hs_result" not in st.session_state:
        st.info("👆 Select a Job and Candidate above, then click **Calculate Hiring Score**.")
        return

    # ── Calculate ──────────────────────────────────────────────────────────
    if calc:
        s_score, matched, total_jd = _skill_score(
            sel_cand.get("skills", ""),
            sel_job.get("skills_required", "")
        )
        e_score = _experience_score(
            sel_cand.get("experience", ""),
            sel_job.get("experience_level", "")
        )
        c_score = _certification_score(
            sel_cand.get("certifications", ""),
            sel_job.get("certification", "")
        )
        o_score = _overall_score(s_score, e_score, c_score)

        st.session_state.hs_result = {
            "candidate":  sel_cand,
            "job":        sel_job,
            "skill":      s_score,
            "experience": e_score,
            "cert":       c_score,
            "overall":    o_score,
            "matched":    matched,
            "total_jd":   total_jd,
        }

    r    = st.session_state.hs_result
    name = (r["candidate"].get("name") or "Unknown").splitlines()[0]
    job_title = r["job"].get("job_title") or "—"

    st.divider()

    # ── Overall score (big card) ───────────────────────────────────────────
    _overall_card(r["overall"], name, job_title)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── 4 metrics row ─────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Overall Score",      f"{r['overall']}%")
    m2.metric("🛠 Skill Score",        f"{r['skill']}%")
    m3.metric("💼 Experience Score",   f"{r['experience']}%")
    m4.metric("🏅 Certification Score", f"{r['cert']}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 3 score cards ─────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        _score_card("Skill Match",    r["skill"],      "🛠", "#8b5cf6", "70%")
    with c2:
        _score_card("Experience",     r["experience"], "💼", "#3b82f6", "20%")
    with c3:
        _score_card("Certification",  r["cert"],       "🏅", "#10b981", "10%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Score breakdown expander ───────────────────────────────────────────
    with st.expander("📊 Score Breakdown Formula", expanded=False):
        st.markdown(
            f"""
            <div style="font-family:monospace;font-size:0.88rem;
                        background:rgba(255,255,255,0.04);border-radius:12px;
                        padding:16px 20px;border:1px solid rgba(255,255,255,0.08)">
                <div style="color:#a78bfa;margin-bottom:8px;font-weight:700">
                    Overall = (Skill × 70%) + (Experience × 20%) + (Certification × 10%)
                </div>
                <div style="color:#94a3b8">
                    = ({r['skill']}% × 0.70) + ({r['experience']}% × 0.20) + ({r['cert']}% × 0.10)
                </div>
                <div style="color:#94a3b8">
                    = {round(r['skill']*0.70,1)} + {round(r['experience']*0.20,1)} + {round(r['cert']*0.10,1)}
                </div>
                <div style="color:#60a5fa;font-weight:700;margin-top:8px;font-size:1rem">
                    = {r['overall']}%
                </div>
                <div style="color:#64748b;margin-top:12px;font-size:0.78rem">
                    Skills matched: {r['matched']} of {r['total_jd']} required
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Hiring recommendation ──────────────────────────────────────────────
    st.divider()
    grade, clr, verdict = _grade(r["overall"])

    recommendations = {
        "A+": ("🟢 Strongly Recommend Hiring",   "Top candidate — schedule interview immediately."),
        "A":  ("🟢 Recommend Hiring",             "Strong candidate — proceed to next round."),
        "B":  ("🟡 Consider with Conditions",     "Good candidate — may need minor upskilling."),
        "C":  ("🟠 Borderline",                   "Average fit — consider only if no better options."),
        "D":  ("🔴 Not Recommended",              "Significant gaps — does not meet requirements."),
    }
    rec_title, rec_desc = recommendations.get(grade, ("—", "—"))

    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,0.04);border-radius:16px;
                    padding:24px 28px;border:1px solid {clr}40;
                    display:flex;align-items:center;gap:20px">
            <div style="font-size:3rem;font-weight:900;color:{clr};
                        background:rgba(255,255,255,0.05);border-radius:16px;
                        width:72px;height:72px;display:flex;align-items:center;
                        justify-content:center;flex-shrink:0">{grade}</div>
            <div>
                <div style="font-size:1.05rem;font-weight:800;color:{clr}">
                    {rec_title}</div>
                <div style="font-size:0.85rem;color:#94a3b8;margin-top:4px">
                    {rec_desc}</div>
                <div style="font-size:0.78rem;color:#64748b;margin-top:6px">
                    Candidate: <b style="color:#e2e8f0">{html.escape(name)}</b> &nbsp;·&nbsp;
                    Role: <b style="color:#e2e8f0">{html.escape(job_title)}</b> &nbsp;·&nbsp;
                    Score: <b style="color:{clr}">{r['overall']}%</b>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Download Reports ───────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px'>"
            "📥 Download Report</div>",
            unsafe_allow_html=True,
        )
        cand_name = (r["candidate"].get("name") or "candidate").split()[0].lower()
        job_slug  = (r["job"].get("job_title") or "job").replace(" ", "_").lower()
        stem      = f"hiring_score_{cand_name}_{job_slug}"

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                label="⬇️ Download CSV",
                data=hiring_score_csv(r),
                file_name=f"{stem}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                label="⬇️ Download PDF",
                data=hiring_score_pdf(r),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
