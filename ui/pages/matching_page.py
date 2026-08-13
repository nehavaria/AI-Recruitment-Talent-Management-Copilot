"""Candidate Matching page — skill & profile analysis against job descriptions."""

import html
import streamlit as st

from reports.report_generator import matching_csv, matching_pdf

from services.candidate_service import CandidateService
from ui.components import empty_state, page_header, skill_badges


# ── Skill normalization ────────────────────────────────────────────────────

def _normalize(raw: str) -> set[str]:
    """Lowercase, trim, deduplicate skills from a comma-separated string."""
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


# ── Match logic ────────────────────────────────────────────────────────────

def _match_skills(candidate_skills: str, job_skills: str) -> dict:
    resume = _normalize(candidate_skills)
    jd     = _normalize(job_skills)

    matched    = sorted(resume & jd)           # resume ∩ jd
    missing    = sorted(jd - resume)           # jd - resume
    additional = sorted(resume - jd)           # resume - jd

    total_jd   = len(jd) or 1
    score      = round((len(matched) / total_jd) * 100, 1)

    return {
        "matched":    matched,
        "missing":    missing,
        "additional": additional,
        "score":      score,
        "total_jd":   len(jd),
        "total_resume": len(resume),
    }


def _match_experience(candidate_exp: str, job_exp_level: str) -> dict:
    """Simple keyword-based experience comparison."""
    level_map = {
        "fresher":   0, "junior": 1, "mid-level": 2,
        "senior": 3, "lead": 4, "manager": 5,
    }
    jd_level  = job_exp_level.lower().strip()
    jd_rank   = level_map.get(jd_level, -1)

    # Check if candidate experience text mentions any level keyword
    exp_lower = (candidate_exp or "").lower()
    candidate_rank = -1
    for level, rank in level_map.items():
        if level in exp_lower:
            candidate_rank = max(candidate_rank, rank)

    if jd_rank == -1:
        status = "⚠️ Not specified in JD"
    elif candidate_rank == -1:
        status = "⚠️ Cannot determine from resume"
    elif candidate_rank >= jd_rank:
        status = "✅ Meets requirement"
    else:
        status = "❌ Below requirement"

    return {
        "jd_level":        job_exp_level or "Not specified",
        "candidate_level": exp_lower[:120] + "…" if len(exp_lower) > 120 else (exp_lower or "Not specified"),
        "status":          status,
    }


def _match_education(candidate_edu: str, job_requirements: str) -> dict:
    """Check if candidate education matches common JD education keywords."""
    edu_keywords = ["b.tech", "btech", "b.e", "mtech", "m.tech", "mba",
                    "bsc", "msc", "phd", "bachelor", "master", "degree",
                    "graduate", "postgraduate", "diploma"]

    edu_lower  = (candidate_edu or "").lower()
    req_lower  = (job_requirements or "").lower()

    # Find what JD requires
    jd_edu = [kw for kw in edu_keywords if kw in req_lower]
    # Find what candidate has
    cand_edu = [kw for kw in edu_keywords if kw in edu_lower]

    if not jd_edu:
        status = "⚠️ No education requirement in JD"
    elif any(kw in edu_lower for kw in jd_edu):
        status = "✅ Meets requirement"
    else:
        status = "❌ May not meet requirement"

    return {
        "jd_requires":  ", ".join(jd_edu).upper() if jd_edu else "Not specified",
        "candidate_has": (candidate_edu or "").splitlines()[0][:100] if candidate_edu else "Not specified",
        "status":        status,
    }


def _match_certifications(candidate_certs: str, job_certification: str) -> dict:
    """Optional certification match."""
    if not job_certification or not job_certification.strip():
        return {"status": "⚠️ No certification required", "match": False}

    certs_lower = (candidate_certs or "").lower()
    jd_cert     = job_certification.lower().strip()

    # Check word by word
    jd_words = set(jd_cert.replace(",", " ").split())
    matched  = any(word in certs_lower for word in jd_words if len(word) > 2)

    return {
        "jd_requires":   job_certification,
        "candidate_has": (candidate_certs or "Not specified")[:120],
        "status":        "✅ Certification found" if matched else "❌ Certification missing",
        "match":         matched,
    }


# ── Badge helpers ──────────────────────────────────────────────────────────

def _skill_pills(skills: list[str], color: str, border: str, text_color: str) -> None:
    if not skills:
        st.caption("None")
        return
    badges = "".join(
        f'<span style="background:{color};color:{text_color};border:1px solid {border};'
        f'padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;'
        f'margin:3px 3px;display:inline-block">{html.escape(s)}</span>'
        for s in skills
    )
    st.markdown(f'<div style="line-height:2.4">{badges}</div>', unsafe_allow_html=True)


# ── Score ring ─────────────────────────────────────────────────────────────

def _score_color(score: float) -> tuple[str, str]:
    if score >= 75:
        return "#10b981", "rgba(16,185,129,0.15)"   # green
    if score >= 50:
        return "#f59e0b", "rgba(245,158,11,0.15)"   # amber
    return "#ef4444", "rgba(239,68,68,0.15)"         # red


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header(
        "🎯 Candidate Matching",
        "Compare candidate profiles against job descriptions and get instant skill analysis.",
    )

    # ── Load data ──────────────────────────────────────────────────────────
    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    # ── Selection dropdowns ────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
                    "text-transform:uppercase;letter-spacing:0.08em;"
                    "margin-bottom:12px'>Select to Compare</div>",
                    unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            job_options = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
            selected_job_key = st.selectbox(
                "💼 Select Job Description",
                options=list(job_options.keys()),
                key="match_job"
            )
            selected_job = job_options[selected_job_key]

        with col2:
            cand_options = {
                f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                for c in candidates
            }
            selected_cand_key = st.selectbox(
                "👤 Select Candidate",
                options=list(cand_options.keys()),
                key="match_candidate"
            )
            selected_candidate = cand_options[selected_cand_key]

        analyze = st.button("🔍 Analyze Match", type="primary", use_container_width=True)

    if not analyze and "match_result" not in st.session_state:
        st.info("👆 Select a Job and a Candidate above, then click **Analyze Match**.")
        return

    # Run analysis on button click, cache in session state
    if analyze:
        st.session_state.match_result = {
            "job":       selected_job,
            "candidate": selected_candidate,
            "skills":    _match_skills(
                            selected_candidate.get("skills", ""),
                            selected_job.get("skills_required", "")
                         ),
            "experience": _match_experience(
                            selected_candidate.get("experience", ""),
                            selected_job.get("experience_level", "")
                          ),
            "education":  _match_education(
                            selected_candidate.get("education", ""),
                            selected_job.get("requirements", "")
                          ),
            "certs":      _match_certifications(
                            selected_candidate.get("certifications", ""),
                            selected_job.get("certification", "")
                          ),
        }

    result = st.session_state.match_result
    job    = result["job"]
    cand   = result["candidate"]
    skills = result["skills"]
    exp    = result["experience"]
    edu    = result["education"]
    certs  = result["certs"]

    st.divider()

    # ── Header: who vs what ────────────────────────────────────────────────
    col_c, col_vs, col_j = st.columns([5, 1, 5])
    with col_c:
        name = (cand.get("name") or "Unknown").splitlines()[0]
        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),"
            f"rgba(37,99,235,0.1));border-radius:16px;padding:16px 20px;"
            f"border:1px solid rgba(124,58,237,0.2)'>"
            f"<div style='font-size:0.7rem;color:#94a3b8;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:0.08em'>Candidate</div>"
            f"<div style='font-size:1.1rem;font-weight:800;color:#f1f5f9;margin-top:4px'>"
            f"{html.escape(name)}</div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:2px'>"
            f"✉ {html.escape(cand.get('email') or '—')}</div></div>",
            unsafe_allow_html=True
        )
    with col_vs:
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:center;"
            "height:100%;font-size:1.5rem;padding-top:16px'>⚡</div>",
            unsafe_allow_html=True
        )
    with col_j:
        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba(37,99,235,0.15),"
            f"rgba(6,182,212,0.1));border-radius:16px;padding:16px 20px;"
            f"border:1px solid rgba(37,99,235,0.2)'>"
            f"<div style='font-size:0.7rem;color:#94a3b8;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:0.08em'>Job Description</div>"
            f"<div style='font-size:1.1rem;font-weight:800;color:#f1f5f9;margin-top:4px'>"
            f"{html.escape(job.get('job_title') or '—')}</div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:2px'>"
            f"🏢 {html.escape(job.get('department') or '—')} · "
            f"📍 {html.escape(job.get('location') or '—')}</div></div>",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Score + top metrics ────────────────────────────────────────────────
    score      = skills["score"]
    clr, bg    = _score_color(score)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Match Score",      f"{score}%")
    m2.metric("✅ Matched Skills",   skills["matched"].__len__())
    m3.metric("❌ Missing Skills",   skills["missing"].__len__())
    m4.metric("➕ Additional Skills", skills["additional"].__len__())

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Skill analysis cards ───────────────────────────────────────────────
    st.markdown("<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
                "margin-bottom:12px'>🛠 Skill Analysis</div>",
                unsafe_allow_html=True)

    col_a, col_b, col_c2 = st.columns(3)

    with col_a:
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#10b981;"
                "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px'>"
                "✅ Matched Skills</div>",
                unsafe_allow_html=True
            )
            _skill_pills(
                skills["matched"],
                "rgba(16,185,129,0.15)", "rgba(16,185,129,0.4)", "#6ee7b7"
            )

    with col_b:
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#ef4444;"
                "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px'>"
                "❌ Missing Skills</div>",
                unsafe_allow_html=True
            )
            _skill_pills(
                skills["missing"],
                "rgba(239,68,68,0.15)", "rgba(239,68,68,0.4)", "#fca5a5"
            )

    with col_c2:
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#60a5fa;"
                "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px'>"
                "➕ Additional Skills</div>",
                unsafe_allow_html=True
            )
            _skill_pills(
                skills["additional"],
                "rgba(59,130,246,0.15)", "rgba(59,130,246,0.4)", "#93c5fd"
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Experience / Education / Certification ─────────────────────────────
    st.markdown("<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
                "margin-bottom:12px'>📋 Profile Comparison</div>",
                unsafe_allow_html=True)

    with st.expander("💼 Experience Comparison", expanded=True):
        e1, e2, e3 = st.columns(3)
        e1.metric("JD Requires",     exp["jd_level"])
        e2.metric("Candidate Level", exp["candidate_level"][:30] + "…"
                  if len(exp["candidate_level"]) > 30 else exp["candidate_level"])
        e3.metric("Status",          exp["status"])

    with st.expander("🎓 Education Comparison", expanded=True):
        d1, d2, d3 = st.columns(3)
        d1.metric("JD Requires",     edu["jd_requires"])
        d2.metric("Candidate Has",   edu["candidate_has"][:40] + "…"
                  if len(edu["candidate_has"]) > 40 else edu["candidate_has"])
        d3.metric("Status",          edu["status"])

    with st.expander("🏅 Certification Comparison", expanded=True):
        if "jd_requires" in certs:
            c1, c2, c3 = st.columns(3)
            c1.metric("JD Requires",     certs["jd_requires"])
            c2.metric("Candidate Has",   certs["candidate_has"][:40] + "…"
                      if len(certs["candidate_has"]) > 40 else certs["candidate_has"])
            c3.metric("Status",          certs["status"])
        else:
            st.info(certs["status"])

    st.divider()

    # ── Summary verdict ────────────────────────────────────────────────────
    if score >= 75:
        verdict = "🟢 Strong Match — Highly recommended for this role!"
        v_color = "#10b981"
    elif score >= 50:
        verdict = "🟡 Moderate Match — Candidate meets some requirements."
        v_color = "#f59e0b"
    else:
        verdict = "🔴 Weak Match — Significant skill gaps found."
        v_color = "#ef4444"

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:16px;"
        f"padding:20px 24px;border:1px solid {v_color}40;text-align:center'>"
        f"<div style='font-size:1.1rem;font-weight:800;color:{v_color}'>{verdict}</div>"
        f"<div style='font-size:0.82rem;color:#94a3b8;margin-top:6px'>"
        f"Skill match score: <b style='color:{v_color}'>{score}%</b> "
        f"({len(skills['matched'])} of {skills['total_jd']} required skills matched)"
        f"</div></div>",
        unsafe_allow_html=True
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
        cand_name = (result["candidate"].get("name") or "candidate").split()[0].lower()
        job_slug  = (result["job"].get("job_title") or "job").replace(" ", "_").lower()
        stem      = f"matching_{cand_name}_{job_slug}"

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                label="⬇️ Download CSV",
                data=matching_csv(result),
                file_name=f"{stem}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                label="⬇️ Download PDF",
                data=matching_pdf(result),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
