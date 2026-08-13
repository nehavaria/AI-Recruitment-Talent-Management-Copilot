"""
Milestone 3 — Interview Report Generator
Generates a comprehensive interview report from simulator results
and ATS pipeline data. Supports PDF and CSV download.
Uses existing candidate and job database.
"""

import html
import io
from datetime import datetime
import streamlit as st

from services.candidate_service import CandidateService
from ui.components import page_header, empty_state
from milestone3.interview_db import init_db, load_latest_report, load_all_sessions, load_session_by_id, delete_session


# ══════════════════════════════════════════════
#  GRADE HELPERS
# ══════════════════════════════════════════════

def _grade(score: float) -> tuple[str, str, str]:
    if score >= 85: return "A+", "#10b981", "Excellent"
    if score >= 70: return "A",  "#34d399", "Strong"
    if score >= 55: return "B",  "#f59e0b", "Good"
    if score >= 40: return "C",  "#fb923c", "Average"
    return              "D",  "#ef4444",  "Needs Improvement"


def _recommendation(score: float) -> tuple[str, str]:
    if score >= 85: return "🟢 Strongly Recommend", "Top performer — proceed to offer stage immediately."
    if score >= 70: return "🟢 Recommend",          "Strong candidate — proceed to next round."
    if score >= 55: return "🟡 Consider",            "Good candidate — may need minor upskilling."
    if score >= 40: return "🟠 Borderline",          "Average performance — consider only if no better options."
    return                 "🔴 Not Recommended",     "Significant gaps — does not meet requirements."


# ══════════════════════════════════════════════
#  REPORT BUILDERS
# ══════════════════════════════════════════════

def _build_text_report(report: dict) -> str:
    """Build a plain-text interview report."""
    cand   = report["candidate"]
    job    = report["job"]
    answers = report.get("answers", [])
    avg    = report.get("avg_score", 0)
    grade, _, verdict = _grade(avg)
    rec_title, rec_desc = _recommendation(avg)
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "=" * 65,
        "         AI RECRUITMENT COPILOT — INTERVIEW REPORT",
        "=" * 65,
        f"Generated : {now}",
        f"Candidate : {(cand.get('name') or 'Unknown').splitlines()[0]}",
        f"Email     : {cand.get('email') or '—'}",
        f"Job Role  : {job.get('job_title') or '—'}",
        f"Department: {job.get('department') or '—'}",
        "",
        "-" * 65,
        "OVERALL PERFORMANCE",
        "-" * 65,
        f"Score     : {avg}%",
        f"Grade     : {grade} — {verdict}",
        f"Decision  : {rec_title}",
        f"Remarks   : {rec_desc}",
        "",
        "-" * 65,
        "QUESTION-BY-QUESTION BREAKDOWN",
        "-" * 65,
    ]

    for i, ans in enumerate(answers, 1):
        ev = ans.get("evaluation", {})
        lines += [
            f"",
            f"Q{i}. [{ans.get('skill','General')}] {ans['question']}",
            f"   Answer  : {ans.get('answer','(no answer)') or '(skipped)'}",
            f"   Score   : {ev.get('score', 0)}% — {ev.get('level','')}",
            f"   Feedback: {ev.get('feedback','')}",
            f"   Ideal   : {ans.get('ideal','')}",
        ]

    lines += [
        "",
        "-" * 65,
        "SKILLS ANALYSIS",
        "-" * 65,
        f"Candidate Skills : {cand.get('skills') or '—'}",
        f"Required Skills  : {job.get('skills_required') or '—'}",
        "",
        "=" * 65,
        "END OF REPORT",
        "=" * 65,
    ]
    return "\n".join(lines)


def _build_csv_report(report: dict) -> str:
    """Build a CSV interview report."""
    cand    = report["candidate"]
    job     = report["job"]
    answers = report.get("answers", [])
    avg     = report.get("avg_score", 0)
    grade, _, verdict = _grade(avg)

    rows = [
        "Question No,Skill,Question,Answer,Score,Level,Feedback"
    ]
    for i, ans in enumerate(answers, 1):
        ev = ans.get("evaluation", {})
        q  = ans["question"].replace('"', "'")
        a  = (ans.get("answer") or "").replace('"', "'")
        fb = ev.get("feedback", "").replace('"', "'")
        rows.append(
            f'{i},"{ans.get("skill","General")}","{q}","{a}",'
            f'{ev.get("score",0)},"{ev.get("level","")}","{fb}"'
        )

    header = [
        f"Candidate,{(cand.get('name') or '').splitlines()[0]}",
        f"Email,{cand.get('email') or ''}",
        f"Job Role,{job.get('job_title') or ''}",
        f"Overall Score,{avg}%",
        f"Grade,{grade} - {verdict}",
        f"Date,{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    return "\n".join(header + rows)


# ══════════════════════════════════════════════
#  MANUAL REPORT BUILDER (without simulator)
# ══════════════════════════════════════════════

def _manual_report_section(candidates: list, jobs: list) -> None:
    """Build a report manually by entering scores."""
    st.markdown(
        "<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:12px'>"
        "📝 Manual Interview Report</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            job_opts = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
            sel_job_key = st.selectbox("💼 Job", list(job_opts.keys()), key="rep_job")
            sel_job = job_opts[sel_job_key]
        with col2:
            cand_opts = {
                f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                for c in candidates
            }
            sel_cand_key = st.selectbox("👤 Candidate", list(cand_opts.keys()), key="rep_cand")
            sel_cand = cand_opts[sel_cand_key]

        st.divider()
        st.markdown(
            "<div style='font-size:0.75rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px'>"
            "Round Scores (0–100)</div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1: tech_score  = st.number_input("Technical",  0, 100, 70, key="rep_tech")
        with c2: comm_score  = st.number_input("Communication", 0, 100, 70, key="rep_comm")
        with c3: prob_score  = st.number_input("Problem Solving", 0, 100, 70, key="rep_prob")
        with c4: cult_score  = st.number_input("Culture Fit", 0, 100, 70, key="rep_cult")

        overall = round((tech_score * 0.40 + comm_score * 0.20 + prob_score * 0.30 + cult_score * 0.10), 1)
        interviewer = st.text_input("Interviewer Name", placeholder="e.g. Priya Sharma", key="rep_interviewer")
        notes = st.text_area("Interview Notes", placeholder="Key observations, strengths, concerns...",
                             height=100, key="rep_notes")

        if st.button("📄 Generate Report", type="primary", use_container_width=True):
            st.session_state.manual_report = {
                "candidate":   sel_cand,
                "job":         sel_job,
                "tech_score":  tech_score,
                "comm_score":  comm_score,
                "prob_score":  prob_score,
                "cult_score":  cult_score,
                "overall":     overall,
                "interviewer": interviewer,
                "notes":       notes,
                "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

    if "manual_report" not in st.session_state:
        return

    r         = st.session_state.manual_report
    overall   = r["overall"]
    grade, clr, verdict = _grade(overall)
    rec_title, rec_desc = _recommendation(overall)
    cand_name = (r["candidate"].get("name") or "Unknown").splitlines()[0]
    job_title = r["job"].get("job_title") or "—"

    st.divider()

    # Overall score card
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));
                    border-radius:20px;padding:28px 32px;border:1px solid {clr}40;
                    text-align:center;margin-bottom:20px">
            <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px">
                🏆 Overall Interview Score</div>
            <div style="font-size:4rem;font-weight:900;color:{clr};letter-spacing:-3px">{overall}%</div>
            <div style="font-size:1.2rem;font-weight:700;color:{clr};margin-top:6px">
                {grade} — {verdict}</div>
            <div style="font-size:0.82rem;color:#94a3b8;margin-top:6px">
                {html.escape(cand_name)} &nbsp;·&nbsp; {html.escape(job_title)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Score breakdown
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🛠 Technical (40%)",      f"{r['tech_score']}%")
    m2.metric("🗣 Communication (20%)",  f"{r['comm_score']}%")
    m3.metric("🧩 Problem Solving (30%)", f"{r['prob_score']}%")
    m4.metric("🤝 Culture Fit (10%)",    f"{r['cult_score']}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # Recommendation
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,0.04);border-radius:14px;
                    padding:20px 24px;border:1px solid {clr}30;
                    border-left:4px solid {clr};margin-bottom:16px">
            <div style="font-size:1rem;font-weight:800;color:{clr}">{rec_title}</div>
            <div style="font-size:0.85rem;color:#94a3b8;margin-top:4px">{rec_desc}</div>
            {f'<div style="font-size:0.82rem;color:#cbd5e1;margin-top:10px"><b>Notes:</b> {html.escape(r["notes"])}</div>' if r["notes"] else ''}
            {f'<div style="font-size:0.75rem;color:#64748b;margin-top:6px">Interviewer: {html.escape(r["interviewer"])}</div>' if r["interviewer"] else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Download
    text_report = "\n".join([
        "=" * 60,
        "AI RECRUITMENT COPILOT — INTERVIEW REPORT",
        "=" * 60,
        f"Date        : {r['date']}",
        f"Candidate   : {cand_name}",
        f"Email       : {r['candidate'].get('email') or '—'}",
        f"Job Role    : {job_title}",
        f"Interviewer : {r['interviewer'] or '—'}",
        "",
        "-" * 60,
        "SCORES",
        "-" * 60,
        f"Technical (40%)      : {r['tech_score']}%",
        f"Communication (20%)  : {r['comm_score']}%",
        f"Problem Solving (30%): {r['prob_score']}%",
        f"Culture Fit (10%)    : {r['cult_score']}%",
        f"Overall Score        : {overall}%",
        f"Grade                : {grade} — {verdict}",
        f"Recommendation       : {rec_title}",
        f"Remarks              : {rec_desc}",
        "",
        "-" * 60,
        "NOTES",
        "-" * 60,
        r["notes"] or "(none)",
        "",
        "=" * 60,
    ])

    slug = cand_name.replace(" ", "_").lower()
    st.download_button(
        "⬇️ Download Report (.txt)",
        data=text_report,
        file_name=f"interview_report_{slug}.txt",
        mime="text/plain",
        use_container_width=True,
    )


# ══════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "📄 Interview Report",
        "Generate and download comprehensive interview reports from simulator results or manual scores.",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    tab_sim, tab_manual = st.tabs([
        "🎤 From Simulator",
        "📝 Manual Entry",
    ])

    # ══════════════════════════════════════════
    #  TAB 1 — From Simulator
    # ══════════════════════════════════════════
    with tab_sim:
        # ── Init DB and try to restore report from SQLite if session_state is empty ──
        try:
            init_db()
        except Exception:
            pass

        # Restore latest report into session_state if missing (e.g. after restart)
        if "sim_last_report" not in st.session_state:
            try:
                _restored = load_latest_report()
                if _restored:
                    st.session_state.sim_last_report = _restored
            except Exception:
                pass

        # ── Session history picker ──────────────────────────────────────────────────────
        try:
            all_sessions = load_all_sessions()
        except Exception:
            all_sessions = []

        if all_sessions:
            with st.expander(f"📂 Saved Sessions ({len(all_sessions)} total) — click to load a past report", expanded=False):
                for s in all_sessions:
                    sc   = s["avg_score"]
                    clr  = "#10b981" if sc >= 70 else "#f59e0b" if sc >= 40 else "#ef4444"
                    ts   = str(s["created_at"])[:16]
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.markdown(
                            f"<div style='padding:6px 0'>"
                            f"<span style='font-size:0.88rem;font-weight:700;color:#f1f5f9'>{s['candidate_name']}</span>"
                            f" &nbsp;·&nbsp; <span style='font-size:0.8rem;color:#a78bfa'>{s['job_title']}</span>"
                            f" &nbsp;·&nbsp; <span style='font-size:0.8rem;font-weight:800;color:{clr}'>{sc}%</span>"
                            f"<div style='font-size:0.68rem;color:#64748b'>{ts}</div></div>",
                            unsafe_allow_html=True,
                        )
                    with col2:
                        if st.button("Load", key=f"load_sess_{s['session_id']}"):
                            try:
                                _r = load_session_by_id(s["session_id"])
                                if _r:
                                    st.session_state.sim_last_report = _r
                                    st.rerun()
                            except Exception as _e:
                                st.error(str(_e))
                    with col3:
                        if st.button("🗑", key=f"del_sess_{s['session_id']}", help="Delete this session"):
                            try:
                                delete_session(s["session_id"])
                                if st.session_state.get("sim_last_report", {}).get("candidate", {}).get("candidate_id") == s["candidate_id"]:
                                    del st.session_state["sim_last_report"]
                                st.rerun()
                            except Exception as _e:
                                st.error(str(_e))

        if "sim_last_report" not in st.session_state:
            st.info(
                "No simulator session found. "
                "Go to **🎤 Interview Simulator**, complete a session, then come back here."
            )
        else:
            report    = st.session_state.sim_last_report
            answers   = report.get("answers", [])
            avg       = report.get("avg_score", 0)
            grade, clr, verdict = _grade(avg)
            rec_title, rec_desc = _recommendation(avg)
            cand      = report["candidate"]
            job       = report["job"]
            cand_name = (cand.get("name") or "Unknown").splitlines()[0]
            job_title = job.get("job_title") or "—"

            # Header card
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));
                            border-radius:20px;padding:28px 32px;border:1px solid {clr}40;
                            text-align:center;margin-bottom:20px">
                    <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;
                                text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px">
                        🏆 Simulator Interview Report</div>
                    <div style="font-size:4rem;font-weight:900;color:{clr};letter-spacing:-3px">{avg}%</div>
                    <div style="font-size:1.2rem;font-weight:700;color:{clr};margin-top:6px">
                        {grade} — {verdict}</div>
                    <div style="font-size:0.82rem;color:#94a3b8;margin-top:6px">
                        {html.escape(cand_name)} &nbsp;·&nbsp; {html.escape(job_title)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Metrics
            scores = [a["evaluation"]["score"] for a in answers]
            if scores:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("📋 Questions",    len(answers))
                m2.metric("🏆 Avg Score",    f"{avg}%")
                m3.metric("✅ Best Score",   f"{max(scores)}%")
                m4.metric("⚠️ Lowest Score", f"{min(scores)}%")

            st.markdown("<br>", unsafe_allow_html=True)

            # Recommendation
            st.markdown(
                f"""
                <div style="background:rgba(255,255,255,0.04);border-radius:14px;
                            padding:20px 24px;border:1px solid {clr}30;
                            border-left:4px solid {clr};margin-bottom:20px">
                    <div style="font-size:1rem;font-weight:800;color:{clr}">{rec_title}</div>
                    <div style="font-size:0.85rem;color:#94a3b8;margin-top:4px">{rec_desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Per-question summary table
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:12px'>"
                "📋 Question Breakdown</div>",
                unsafe_allow_html=True,
            )
            for i, ans in enumerate(answers, 1):
                ev  = ans.get("evaluation", {})
                sc  = ev.get("score", 0)
                g, c, _ = _grade(sc)
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                                background:rgba(255,255,255,0.03);border-radius:10px;
                                border:1px solid rgba(255,255,255,0.06);margin-bottom:6px">
                        <span style="background:{c}20;color:{c};font-weight:800;
                                     font-size:0.75rem;padding:3px 10px;border-radius:20px;
                                     min-width:28px;text-align:center">{g}</span>
                        <div style="flex:1;font-size:0.82rem;color:#f1f5f9">
                            {html.escape(ans['question'][:70])}{'...' if len(ans['question'])>70 else ''}</div>
                        <span style="font-size:0.8rem;font-weight:700;color:{c}">{sc}%</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.divider()

            # Downloads
            slug = cand_name.replace(" ", "_").lower()
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "⬇️ Download Text Report",
                    data=_build_text_report(report),
                    file_name=f"interview_report_{slug}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    "⬇️ Download CSV Report",
                    data=_build_csv_report(report),
                    file_name=f"interview_report_{slug}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ══════════════════════════════════════════
    #  TAB 2 — Manual Entry
    # ══════════════════════════════════════════
    with tab_manual:
        _manual_report_section(candidates, jobs)
