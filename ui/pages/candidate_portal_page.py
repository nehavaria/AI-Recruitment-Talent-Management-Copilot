"""Candidate Portal — profile, pipeline status, scheduled interviews, AI interview."""

import html
import io
import json
import time

import mysql.connector
import streamlit as st

from config.settings import MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
from services.candidate_service import CandidateService
from ui.components import info_row, page_header, skill_badges
from milestone3.interview_simulator import _generate_question, _evaluate, _use_gemini
from milestone3.interview_db import init_db, save_report
from milestone4.voice_screening import (
    _init_voice_table, _save_answer, _backfill_session_id,
    _save_audio_file, _transcribe, _progress, _q_bubble, _a_bubble,
    _eval_card, _TOTAL as _VS_TOTAL,
)

_TOTAL = 10

_STAGE_CFG = {
    "Applied":   {"color": "#3b82f6", "bg": "rgba(59,130,246,0.12)",  "icon": "📥", "step": 1},
    "Screening": {"color": "#8b5cf6", "bg": "rgba(139,92,246,0.12)",  "icon": "🔍", "step": 2},
    "Interview": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.12)",  "icon": "🎤", "step": 3},
    "Selected":  {"color": "#10b981", "bg": "rgba(16,185,129,0.12)",  "icon": "✅", "step": 4},
    "Rejected":  {"color": "#ef4444", "bg": "rgba(239,68,68,0.12)",   "icon": "❌", "step": 4},
}
_STAGE_ORDER = ["Applied", "Screening", "Interview", "Selected"]


def _db():
    return mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
        user=MYSQL_USER, password=MYSQL_PASSWORD, charset="utf8mb4",
    )


def render(service: CandidateService) -> None:
    email        = st.session_state.get("candidate_email", "")
    display_name = st.session_state.get("candidate_name", "Candidate")

    page_header(f"👋 Welcome, {display_name}", "Your profile, application status & AI interview.")

    candidate = service.get_candidate_by_email(email)
    if not candidate:
        st.error("Profile not found. Please contact your recruiter.")
        return

    _render_header(candidate)
    st.divider()

    _cand_jobs = _get_candidate_jobs(candidate["candidate_id"])

    tab_profile, tab_status, tab_schedule, tab_voice, tab_ai = st.tabs([
        "📋 My Profile", "📌 My Status", "📅 Scheduled Interviews",
        "🎙️ Voice Screening", "🤖 AI Interview"
    ])

    with tab_profile:
        _render_profile(candidate)

    with tab_status:
        _render_status(candidate)

    with tab_schedule:
        _render_scheduled(candidate)

    with tab_voice:
        _render_voice_screening(candidate, service, _cand_jobs)

    with tab_ai:
        _render_ai_interview(candidate, service, _cand_jobs)


# ── Fetch scheduled jobs once per render ────────────────────────────────────

def _get_candidate_jobs(cid: int) -> list[dict]:
    """Return distinct job rows from recruiter_interviews for this candidate."""
    try:
        conn = _db()
        cur  = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT DISTINCT ri.job_title, COALESCE(j.job_id, 0) AS job_id
            FROM recruiter_interviews ri
            LEFT JOIN jobs j ON j.job_title = ri.job_title
            WHERE ri.candidate_id = %s
        """, (cid,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except Exception:
        return []


# ── Header ──────────────────────────────────────────────────────────────────

def _render_header(c: dict) -> None:
    name     = (c.get("name") or "Unknown").splitlines()[0].strip()
    email    = c.get("email") or "—"
    phone    = c.get("phone") or "—"
    initials = "".join(w[0].upper() for w in name.split()[:2]) or "?"
    skills   = [s.strip() for s in c.get("skills", "").split(",") if s.strip()]
    col_av, col_info, col_count = st.columns([1, 5, 2])
    with col_av:
        st.markdown(
            f'<div style="width:64px;height:64px;border-radius:18px;'
            f'background:linear-gradient(135deg,#7c3aed,#2563eb);'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-weight:900;font-size:1.4rem;margin-top:6px;'
            f'box-shadow:0 4px 20px rgba(124,58,237,0.5)">'
            f'{html.escape(initials)}</div>', unsafe_allow_html=True,
        )
    with col_info:
        st.markdown(f"### {html.escape(name)}")
        st.caption(f"✉ {email}  ·  📞 {phone}")
    with col_count:
        st.metric("Skills", len(skills))


# ── Profile tab ─────────────────────────────────────────────────────────────

def _render_profile(c: dict) -> None:
    t1, t2, t3, t4, t5 = st.tabs(["📋 Info", "🛠 Skills", "💼 Experience", "🎓 Education", "📁 Projects & Certs"])
    with t1:
        info_row("Name",  c.get("name", ""))
        info_row("Email", c.get("email", ""))
        info_row("Phone", c.get("phone", ""))
        info_row("Profile Since", str(c.get("created_date") or "—"))
    with t2:
        skills = [s.strip() for s in c.get("skills", "").split(",") if s.strip()]
        if skills:
            skill_badges(skills, max_show=50)
        else:
            st.caption("No skills detected.")
    with t3:
        _lines(c.get("experience"), "No experience data.")
    with t4:
        _lines(c.get("education"), "No education data.")
    with t5:
        _lines(c.get("projects"), "")
        _lines(c.get("certifications"), "No projects or certifications.")


# ── Status tab ──────────────────────────────────────────────────────────────

def _render_status(c: dict) -> None:
    cid = c["candidate_id"]
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT p.stage, p.resume_score, p.recruiter_email, p.interview_date,
                   p.notes, p.feedback, p.recruiter_notes, j.job_title
            FROM ats_pipeline p
            LEFT JOIN jobs j ON j.job_id = p.job_id
            WHERE p.candidate_id = %s
            ORDER BY p.interview_date DESC
        """, (cid,))
        pipeline = cur.fetchall()

        cur.execute("""
            SELECT job_title, avg_score, verdict, report_json, created_at
            FROM interview_sessions WHERE candidate_id = %s ORDER BY created_at DESC
        """, (cid,))
        sessions = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"Could not load status: {e}"); return

    if not pipeline:
        st.info("Your application has not been added to the pipeline yet.")
    else:
        for stage, resume_score, rec_email, idate, notes, feedback, rec_notes, job_title in pipeline:
            stage = stage or "Applied"
            cfg   = _STAGE_CFG.get(stage, _STAGE_CFG["Applied"])
            score = float(resume_score or 0)
            step  = cfg["step"]
            bar   = "".join(
                f"<div style='flex:1;height:6px;border-radius:4px;margin:0 2px;"
                f"background:{'linear-gradient(90deg,#7c3aed,#2563eb)' if i < step else 'rgba(255,255,255,0.1)'}'></div>"
                for i in range(len(_STAGE_ORDER))
            ) if stage != "Rejected" else ""

            extra = ""
            if any([notes, feedback, rec_notes]):
                extra = (
                    f"<div style='font-size:0.8rem;color:#cbd5e1;margin-top:10px;padding-top:10px;"
                    f"border-top:1px solid rgba(255,255,255,0.08)'>"
                    + (f"📝 <b>Notes:</b> {html.escape(notes)}<br>" if notes else "")
                    + (f"💬 <b>Feedback:</b> {html.escape(feedback)}<br>" if feedback else "")
                    + (f"📌 <b>Recruiter Notes:</b> {html.escape(rec_notes)}" if rec_notes else "")
                    + "</div>"
                )

            st.html(
                f"<div style='background:{cfg['bg']};border-radius:16px;padding:20px 24px;"
                f"border:1px solid {cfg['color']}40;margin-bottom:12px'>"
                f"<div style='display:flex;align-items:center;gap:16px'>"
                f"<div style='font-size:2rem'>{cfg['icon']}</div>"
                f"<div style='flex:1'>"
                f"<div style='font-size:1.1rem;font-weight:800;color:{cfg['color']}'>{html.escape(stage)}</div>"
                f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:2px'>"
                f"{'Job: <b style=color:#f1f5f9>' + html.escape(job_title or '') + '</b> &nbsp;·&nbsp; ' if job_title else ''}"
                f"Resume Score: <b style='color:#f1f5f9'>{score:.0f}%</b>"
                f"{'&nbsp;·&nbsp; Interview: <b style=color:#f1f5f9>' + str(idate) + '</b>' if idate else ''}"
                f"</div></div></div>"
                f"{'<div style=display:flex;gap:4px;margin-top:12px>' + bar + '</div>' if bar else ''}"
                + extra + "</div>"
            )

    if sessions:
        st.html("<div style='font-size:1rem;font-weight:800;color:#e2e8f0;margin:20px 0 12px'>🎤 AI Interview Results</div>")
        for job_title, avg_score, verdict, report_json, created_at in sessions:
            v_color   = "#10b981" if "Strong" in (verdict or "") else "#f59e0b" if "Good" in (verdict or "") else "#ef4444"
            score_val = float(avg_score or 0)
            with st.expander(f"🎤 {job_title or 'Interview'} — {score_val:.1f}% · {verdict or 'Pending'} · {str(created_at)[:10]}"):
                try:
                    report  = json.loads(report_json or "{}")
                    answers = report.get("answers", [])
                    st.html(
                        f"<div style='display:flex;gap:24px;margin-bottom:12px'>"
                        f"<div><span style='font-size:0.7rem;color:#94a3b8'>VERDICT</span><br>"
                        f"<b style='color:{v_color}'>{html.escape(verdict or '—')}</b></div>"
                        f"<div><span style='font-size:0.7rem;color:#94a3b8'>AVG SCORE</span><br>"
                        f"<b style='color:#f1f5f9'>{score_val:.1f}%</b></div>"
                        f"<div><span style='font-size:0.7rem;color:#94a3b8'>DATE</span><br>"
                        f"<b style='color:#f1f5f9'>{str(created_at)[:10]}</b></div></div>"
                    )
                    for i, a in enumerate(answers, 1):
                        ev = a.get("evaluation", {})
                        st.html(
                            f"<div style='padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.07)'>"
                            f"<div style='font-size:0.78rem;color:#94a3b8'>Q{i}: {html.escape(a.get('question',''))}</div>"
                            f"<div style='font-size:0.8rem;color:#e2e8f0;margin-top:2px'>{html.escape(a.get('answer','') or '(skipped)')}</div>"
                            f"<div style='font-size:0.72rem;color:#60a5fa;margin-top:2px'>Score: {ev.get('score','—')}% — {html.escape(ev.get('feedback',''))}</div>"
                            f"</div>"
                        )
                except Exception:
                    st.caption("Could not parse report.")


# ── Scheduled Interviews tab ─────────────────────────────────────────────────

def _render_scheduled(c: dict) -> None:
    cid = c["candidate_id"]
    try:
        conn = _db()
        cur  = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM recruiter_interviews
            WHERE candidate_id = %s ORDER BY interview_date ASC, interview_time ASC
        """, (cid,))
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        st.warning(f"Could not load interviews: {e}"); return

    if not rows:
        st.info("No interviews scheduled for you yet.")
        return

    st.caption(f"{len(rows)} interview(s) scheduled")
    from datetime import date
    today = date.today().isoformat()

    for s in rows:
        is_past = s["interview_date"] < today
        cfg_color = "rgba(100,116,139,0.3)" if is_past else "rgba(245,158,11,0.4)"
        link_html = ""
        if s.get("meeting_link"):
            link_html = f"<a href='{html.escape(s['meeting_link'])}' target='_blank' style='color:#60a5fa;font-size:0.8rem'>🔗 Join Meeting</a>"

        st.html(
            f"<div style='background:rgba(255,255,255,0.04);border-radius:14px;padding:18px 22px;"
            f"border:1px solid {cfg_color};margin-bottom:10px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
            f"<div>"
            f"<div style='font-size:0.95rem;font-weight:700;color:#f1f5f9'>💼 {html.escape(s.get('job_title') or '—')}</div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:4px'>🧑‍💼 Interviewer: <b style='color:#e2e8f0'>{html.escape(s.get('interviewer') or '—')}</b></div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:2px'>📅 {s['interview_date']} &nbsp; 🕐 {s['interview_time']} &nbsp; 📍 {s.get('mode','Online')}</div>"
            f"{'<div style=margin-top:6px>' + link_html + '</div>' if link_html else ''}"
            f"{'<div style=font-size:0.75rem;color:#94a3b8;margin-top:4px>📝 ' + html.escape(s['notes']) + '</div>' if s.get('notes') else ''}"
            f"</div>"
            f"<div style='font-size:0.7rem;color:{'#64748b' if is_past else '#f59e0b'};font-weight:700'>{'Past' if is_past else 'Upcoming'}</div>"
            f"</div></div>"
        )


# ── Voice Screening tab ──────────────────────────────────────────────────────

def _render_voice_screening(candidate: dict, service: CandidateService, jobs: list[dict]) -> None:
    ss  = st.session_state
    cid = candidate["candidate_id"]

    # Init tables once per session
    if "cand_vs_tables_ready" not in ss:
        try:
            init_db()
            _init_voice_table()
            ss["cand_vs_tables_ready"] = True
        except Exception as e:
            st.error(f"Database init failed: {e}")
            return

    if not jobs:
        st.html(
            "<div style='background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);"
            "border-radius:14px;padding:24px;text-align:center'>"
            "<div style='font-size:2rem;margin-bottom:10px'>🔒</div>"
            "<div style='font-size:1rem;font-weight:700;color:#a78bfa'>Voice Screening Not Available Yet</div>"
            "<div style='font-size:0.82rem;color:#94a3b8;margin-top:8px'>"
            "Your recruiter needs to schedule an interview before you can take the voice screening."
            "</div></div>"
        )
        return

    defaults = {
        "cand_vs_active": False, "cand_vs_history": [], "cand_vs_index": 0,
        "cand_vs_done": False, "cand_vs_start": None, "cand_vs_current_q": None,
    }
    for k, v in defaults.items():
        if k not in ss:
            ss[k] = v

    # ── Setup screen ──────────────────────────────────────────────────────
    if not ss["cand_vs_active"]:
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#a78bfa;"
                "margin-bottom:12px'>⚙️ Start Voice Screening</div>",
                unsafe_allow_html=True,
            )
            job_opts = {j["job_title"]: j for j in jobs}
            sel_job  = job_opts[st.selectbox("💼 Select Job Role", list(job_opts.keys()), key="vs_cand_job_sel")]
            engine   = "🔮 Gemini" if _use_gemini() else "🤖 Groq"
            st.info(
                f"**{_VS_TOTAL} voice questions** · Engine: {engine}\n\n"
                "Upload a **WAV file** for each question. Your answers are transcribed and scored automatically."
            )
            if st.button("🚀 Start Voice Screening", type="primary", use_container_width=True, key="vs_cand_start"):
                ss["cand_vs_active"]    = True
                ss["cand_vs_history"]   = []
                ss["cand_vs_index"]     = 0
                ss["cand_vs_done"]      = False
                ss["cand_vs_start"]     = time.time()
                ss["cand_vs_candidate"] = candidate
                ss["cand_vs_job"]       = sel_job
                ss["cand_vs_current_q"] = None
                st.rerun()
        return

    # ── Results screen ────────────────────────────────────────────────────
    if ss["cand_vs_done"]:
        history = ss["cand_vs_history"]
        scores  = [h["evaluation"]["score"] for h in history if h.get("evaluation")]
        avg     = round(sum(scores) / len(scores), 1) if scores else 0
        clr     = "#10b981" if avg >= 70 else "#f59e0b" if avg >= 40 else "#ef4444"
        verdict = "Strong Performance 🎉" if avg >= 70 else "Good Effort 👍" if avg >= 40 else "Needs More Preparation 📚"
        elapsed = int(time.time() - ss["cand_vs_start"])

        st.html(
            f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));"
            f"border-radius:20px;padding:28px;border:1px solid {clr}40;text-align:center;margin-bottom:20px'>"
            f"<div style='font-size:3rem;font-weight:900;color:{clr}'>{avg}%</div>"
            f"<div style='font-size:1rem;font-weight:700;color:#f1f5f9;margin-top:8px'>{verdict}</div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:6px'>"
            f"⏱️ {elapsed//60:02d}:{elapsed%60:02d} · {_VS_TOTAL} questions · 🎙 all voice</div></div>"
        )

        # Save report
        report = {
            "candidate": candidate,
            "job":       ss["cand_vs_job"],
            "answers":   [{"question": h["question"], "answer": h["transcript"],
                           "transcript": h["transcript"], "via": "voice",
                           "skill": "Voice Screening", "evaluation": h["evaluation"],
                           "ideal": "", "audio_path": h.get("audio_path", "")}
                          for h in history],
            "avg_score": avg, "verdict": verdict, "mode": "voice_screening",
        }
        st.session_state.sim_last_report = report
        try:
            session_id = save_report(report)
            _backfill_session_id(cid, ss["cand_vs_job"]["job_id"], session_id)
        except Exception:
            pass

        st.divider()
        for i, h in enumerate(history):
            ev = h.get("evaluation", {})
            with st.expander(f"🎙 Q{i+1}: {h['question'][:65]}… — {ev.get('score','—')}%"):
                st.markdown(f"**Transcript:** _{h.get('transcript') or '(none)'}_")
                st.markdown(f"**Score:** {ev.get('score','—')}% — {ev.get('level','')}")
                st.caption(ev.get("feedback", ""))

        if st.button("🔄 Try Again", type="primary", use_container_width=True, key="vs_cand_retry"):
            for k in defaults:
                ss[k] = defaults[k]
            st.rerun()
        return

    # ── Active session ────────────────────────────────────────────────────
    job_title = ss["cand_vs_job"].get("job_title") or "Engineer"
    elapsed   = int(time.time() - ss["cand_vs_start"])
    cand_name = (candidate.get("name") or "Unknown").splitlines()[0]

    _progress(ss["cand_vs_index"], cand_name, job_title, elapsed)

    # Replay answered questions
    for h in ss["cand_vs_history"]:
        _q_bubble(h["question"])
        _a_bubble(h.get("transcript") or "(no transcript)", h["evaluation"].get("score", 0))
        _eval_card(h["evaluation"])

    # Generate next question
    if ss["cand_vs_current_q"] is None:
        with st.spinner("🤖 Generating question…"):
            ss["cand_vs_current_q"] = _generate_question(
                candidate, ss["cand_vs_job"], ss["cand_vs_history"], ss["cand_vs_index"] + 1
            )
        st.rerun()

    _q_bubble(ss["cand_vs_current_q"])

    st.markdown(
        "<div style='background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);"
        "border-radius:12px;padding:14px 18px;margin-bottom:12px;font-size:0.85rem;color:#c4b5fd'>"
        "🎙️ Record your answer as a <b>WAV file</b> and upload below. "
        "It will be transcribed and evaluated automatically.</div>",
        unsafe_allow_html=True,
    )

    audio_file = st.file_uploader("Upload voice answer (WAV)", type=["wav"], key=f"vs_cand_audio_{ss['cand_vs_index']}")
    transcript   = ""
    audio_path   = ""
    final_answer = ""

    if audio_file:
        audio_bytes = audio_file.read()
        st.audio(audio_bytes, format="audio/wav")
        with st.spinner("🎙️ Transcribing…"):
            transcript = _transcribe(audio_bytes)
        if transcript:
            st.success(f"📝 Transcript: **{transcript}**")
            final_answer = transcript
        else:
            st.warning("Could not transcribe. Enter answer manually below.")
        manual = st.text_input("✏️ Edit or enter answer manually:", value=transcript, key=f"vs_cand_manual_{ss['cand_vs_index']}")
        if manual.strip():
            final_answer = manual.strip()
            transcript   = manual.strip()

        c1, c2 = st.columns([4, 1])
        with c1:
            submit = st.button("✅ Submit Answer", type="primary", use_container_width=True, key=f"vs_cand_sub_{ss['cand_vs_index']}")
        with c2:
            skip = st.button("⏭ Skip", use_container_width=True, key=f"vs_cand_skip_{ss['cand_vs_index']}")

        if submit or skip:
            q   = ss["cand_vs_current_q"]
            idx = ss["cand_vs_index"]
            jid = ss["cand_vs_job"].get("job_id", 0)
            if submit and audio_bytes:
                try:
                    audio_path = _save_audio_file(audio_bytes, cid, idx)
                except Exception:
                    pass
            with st.spinner("Evaluating…"):
                ev = _evaluate(q, final_answer, job_title)
            try:
                _save_answer(cid, jid, idx, q, audio_path, transcript, ev)
            except Exception:
                pass
            ss["cand_vs_history"].append({"question": q, "transcript": transcript, "audio_path": audio_path, "evaluation": ev})
            ss["cand_vs_index"]    += 1
            ss["cand_vs_current_q"] = None
            ss["cand_vs_done"]      = ss["cand_vs_index"] >= _VS_TOTAL
            st.rerun()
    else:
        if st.button("⏭ Skip Question", key=f"vs_cand_skip_na_{ss['cand_vs_index']}"):
            q   = ss["cand_vs_current_q"]
            idx = ss["cand_vs_index"]
            jid = ss["cand_vs_job"].get("job_id", 0)
            ev  = _evaluate(q, "", job_title)
            try:
                _save_answer(cid, jid, idx, q, "", "", ev)
            except Exception:
                pass
            ss["cand_vs_history"].append({"question": q, "transcript": "", "audio_path": "", "evaluation": ev})
            ss["cand_vs_index"]    += 1
            ss["cand_vs_current_q"] = None
            ss["cand_vs_done"]      = ss["cand_vs_index"] >= _VS_TOTAL
            st.rerun()


# ── AI Interview tab ─────────────────────────────────────────────────────────

def _render_ai_interview(candidate: dict, service: CandidateService, jobs: list[dict]) -> None:
    ss = st.session_state
    cid = candidate["candidate_id"]

    if not jobs:
        st.html(
            "<div style='background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);"
            "border-radius:14px;padding:24px;text-align:center'>"
            "<div style='font-size:2rem;margin-bottom:10px'>🔒</div>"
            "<div style='font-size:1rem;font-weight:700;color:#f59e0b'>AI Interview Not Available Yet</div>"
            "<div style='font-size:0.82rem;color:#94a3b8;margin-top:8px'>"
            "Your recruiter needs to schedule an interview for you first."
            "</div></div>"
        )
        return

    defaults = {
        "cai_active": False, "cai_history": [], "cai_index": 0,
        "cai_done": False, "cai_start": None, "cai_q": None,
    }
    for k, v in defaults.items():
        if k not in ss: ss[k] = v

    if not ss.cai_active:
        with st.container(border=True):
            st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#a78bfa;margin-bottom:12px'>⚙️ Start AI Interview Practice</div>", unsafe_allow_html=True)
            job_opts = {j['job_title']: j for j in jobs}
            sel_job  = job_opts[st.selectbox("💼 Select Job Role", list(job_opts.keys()), key="cai_job_sel")]
            engine   = "🔮 Gemini" if _use_gemini() else "🤖 Groq"
            st.info(f"**{_TOTAL} questions** · Engine: {engine} · Your answers are scored on 5 dimensions")
            if st.button("🚀 Start Interview", type="primary", use_container_width=True, key="cai_start_btn"):
                ss.cai_active  = True
                ss.cai_history = []
                ss.cai_index   = 0
                ss.cai_done    = False
                ss.cai_start   = time.time()
                ss.cai_job     = sel_job
                ss.cai_q       = None
                st.rerun()
        return

    job_title = ss.cai_job.get("job_title", "Engineer")
    elapsed   = int(time.time() - ss.cai_start)
    pct       = int((ss.cai_index / _TOTAL) * 100)
    mins, secs = elapsed // 60, elapsed % 60

    st.markdown(
        f"<div style='margin-bottom:14px'>"
        f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;color:#94a3b8;margin-bottom:6px'>"
        f"<span>🎤 <b style='color:#e2e8f0'>{html.escape(job_title)}</b></span>"
        f"<span>❓ {ss.cai_index}/{_TOTAL} &nbsp; ⏱️ {mins:02d}:{secs:02d}</span></div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:8px;overflow:hidden'>"
        f"<div style='background:linear-gradient(90deg,#7c3aed,#2563eb);height:100%;width:{pct}%;border-radius:20px'></div>"
        f"</div></div>", unsafe_allow_html=True,
    )

    # Results
    if ss.cai_done:
        scores  = [h["ev"]["score"] for h in ss.cai_history if h.get("ev")]
        avg     = round(sum(scores) / len(scores), 1) if scores else 0
        verdict = "Strong Performance 🎉" if avg >= 70 else "Good Effort 👍" if avg >= 40 else "Needs More Preparation 📚"
        clr     = "#10b981" if avg >= 70 else "#f59e0b" if avg >= 40 else "#ef4444"

        st.html(
            f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));"
            f"border-radius:20px;padding:32px;border:1px solid rgba(124,58,237,0.3);text-align:center;margin-bottom:20px'>"
            f"<div style='font-size:3rem;font-weight:900;color:{clr}'>{avg}%</div>"
            f"<div style='font-size:1rem;font-weight:700;color:#f1f5f9;margin-top:8px'>{verdict}</div>"
            f"<div style='font-size:0.78rem;color:#94a3b8;margin-top:6px'>⏱️ {mins:02d}:{secs:02d} · {_TOTAL} questions</div>"
            f"</div>"
        )

        _report = {
            "candidate": {**candidate, "candidate_id": cid},
            "job": ss.cai_job,
            "answers": [{"question": h["q"], "answer": h["a"], "evaluation": h["ev"]} for h in ss.cai_history],
            "avg_score": avg, "verdict": verdict,
        }
        st.session_state.sim_last_report = _report
        try:
            init_db(); save_report(_report)
        except Exception:
            pass

        st.divider()
        for i, h in enumerate(ss.cai_history):
            ev = h.get("ev", {})
            with st.expander(f"Q{i+1}: {h['q'][:70]}… — {ev.get('score','—')}%"):
                st.markdown(f"**Answer:** {h['a'] or '_(skipped)_'}")
                st.markdown(f"**Score:** {ev.get('score','—')}% — {ev.get('level','')}")
                st.caption(ev.get("feedback", ""))

        if st.button("🔄 Try Again", type="primary", use_container_width=True, key="cai_retry"):
            for k in defaults: ss[k] = defaults[k]
            st.rerun()
        return

    # Chat history
    for h in ss.cai_history:
        st.markdown(
            f"<div style='background:rgba(124,58,237,0.1);border-radius:12px;padding:12px 16px;margin-bottom:8px'>"
            f"<b style='color:#a78bfa'>🤖 Q:</b> <span style='color:#ffffff'>{html.escape(h['q'])}</span></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='background:rgba(14,165,233,0.08);border-radius:12px;padding:10px 16px;margin-bottom:14px;text-align:right'>"
            f"<b style='color:#38bdf8'>You:</b> {html.escape(h['a'] or '(skipped)')} "
            f"<span style='color:#60a5fa;font-size:0.75rem'>[{h['ev'].get('score','—')}%]</span></div>", unsafe_allow_html=True)

    # Generate question
    if ss.cai_q is None:
        with st.spinner("🤖 Generating question…"):
            ss.cai_q = _generate_question(candidate, ss.cai_job, ss.cai_history, ss.cai_index + 1)
        st.rerun()

    st.markdown(
        f"<div style='background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.3);"
        f"border-radius:14px;padding:16px 20px;margin-bottom:16px'>"
        f"<b style='color:#a78bfa'>🤖 Q{ss.cai_index+1}:</b> <span style='color:#ffffff'>{html.escape(ss.cai_q)}</span></div>",
        unsafe_allow_html=True,
    )

    ans = st.text_area("✍️ Your Answer", height=120, key=f"cai_ans_{ss.cai_index}", placeholder="Type your answer…")
    c1, c2 = st.columns([4, 1])
    with c1:
        submit = st.button("✅ Submit", type="primary", use_container_width=True, key=f"cai_sub_{ss.cai_index}")
    with c2:
        skip = st.button("⏭ Skip", use_container_width=True, key=f"cai_skip_{ss.cai_index}")

    if submit or skip:
        final = ans.strip() if submit else ""
        with st.spinner("Evaluating…"):
            ev = _evaluate(ss.cai_q, final, job_title)
        ss.cai_history.append({"q": ss.cai_q, "a": final, "ev": ev})
        ss.cai_index += 1
        ss.cai_q      = None
        ss.cai_done   = ss.cai_index >= _TOTAL
        st.rerun()
    else:
        time.sleep(1)
        st.rerun()


# ── Helper ───────────────────────────────────────────────────────────────────

def _lines(val, empty_msg):
    lines = [l.strip() for l in (val or "").splitlines() if l.strip()]
    if not lines:
        if empty_msg: st.caption(empty_msg)
        return
    for line in lines:
        st.html(
            f"<div style='display:flex;gap:10px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.07)'>"
            f"<div style='color:#818cf8;font-size:0.7rem;margin-top:3px'>●</div>"
            f"<div style='font-size:0.85rem;color:#e2e8f0'>{html.escape(line)}</div></div>"
        )
