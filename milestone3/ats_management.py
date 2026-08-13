"""
Milestone 3 — ATS Dashboard
Pipeline: Applied → Screening → Interview → Selected → Rejected
Uses existing MySQL connection (config/settings.py + mysql-connector-python).
Does NOT touch any other module.
"""

import html
import logging
from contextlib import contextmanager
from datetime import date
from typing import Any, Generator

import mysql.connector
import streamlit as st

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)
from database.ats_schema import init_ats_schema
from services.candidate_service import CandidateService
from ui.components import empty_state, page_header

logger = logging.getLogger(__name__)

# ── Pipeline config ────────────────────────────────────────────────────────
_STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

_STAGE_CFG = {
    "Applied":   {"color": "#3b82f6", "bg": "rgba(59,130,246,0.12)",  "border": "rgba(59,130,246,0.35)",  "icon": "📥"},
    "Screening": {"color": "#8b5cf6", "bg": "rgba(139,92,246,0.12)", "border": "rgba(139,92,246,0.35)", "icon": "🔍"},
    "Interview": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.12)", "border": "rgba(245,158,11,0.35)", "icon": "🎤"},
    "Selected":  {"color": "#10b981", "bg": "rgba(16,185,129,0.12)", "border": "rgba(16,185,129,0.35)", "icon": "✅"},
    "Rejected":  {"color": "#ef4444", "bg": "rgba(239,68,68,0.12)",  "border": "rgba(239,68,68,0.35)",  "icon": "❌"},
}

# ── MySQL helpers ──────────────────────────────────────────────────────────

def _conn_cfg() -> dict:
    return {
        "host": MYSQL_HOST, "port": MYSQL_PORT, "database": MYSQL_DATABASE,
        "user": MYSQL_USER, "password": MYSQL_PASSWORD,
        "autocommit": False, "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }


@contextmanager
def _db() -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(**_conn_cfg())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(cursor, row) -> dict:
    return dict(zip([c[0] for c in cursor.description], row))


# ── Schema init ────────────────────────────────────────────────────────────

def _init_table() -> None:
    """Create all ATS tables (ats_candidates, recruiter_notes,
    interview_schedule, interview_feedback) if they do not exist."""
    init_ats_schema()


# ── CRUD ───────────────────────────────────────────────────────────────────

def _upsert(r: dict) -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ats_candidates
                (candidate_id, job_id, cand_name, email, phone, resume_score,
                 stage, recruiter)
            VALUES
                (%(candidate_id)s, %(job_id)s, %(cand_name)s, %(email)s, %(phone)s,
                 %(resume_score)s, %(stage)s, %(recruiter)s)
            ON DUPLICATE KEY UPDATE
                cand_name    = VALUES(cand_name),
                email        = VALUES(email),
                phone        = VALUES(phone),
                resume_score = VALUES(resume_score),
                stage        = VALUES(stage),
                recruiter    = VALUES(recruiter)
        """, r)
        ats_id = cur.lastrowid or _get_ats_id(r["candidate_id"], r["job_id"], conn)

        # persist notes → recruiter_notes
        if r.get("notes"):
            cur.execute("""
                INSERT INTO recruiter_notes (ats_id, recruiter, note)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE note = VALUES(note)
            """, (ats_id, r.get("recruiter") or "", r["notes"]))

        # persist interview date → interview_schedule
        if r.get("interview_date"):
            cur.execute("""
                INSERT INTO interview_schedule (ats_id, interview_date, interviewer)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    interview_date = VALUES(interview_date),
                    interviewer    = VALUES(interviewer)
            """, (ats_id, r["interview_date"], r.get("recruiter") or ""))

        # persist feedback → interview_feedback
        if r.get("feedback"):
            cur.execute("""
                INSERT INTO interview_feedback (ats_id, interviewer, comments)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE comments = VALUES(comments)
            """, (ats_id, r.get("recruiter") or "", r["feedback"]))

        cur.close()


def _get_ats_id(candidate_id: int, job_id: int, conn) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT ats_id FROM ats_candidates WHERE candidate_id=%s AND job_id=%s",
        (candidate_id, job_id),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else 0


def _get_all() -> list[dict]:
    """Join ats_candidates with latest note, schedule and feedback per entry."""
    sql = """
        SELECT
            a.ats_id, a.candidate_id, a.job_id, a.cand_name, a.email, a.phone,
            a.resume_score, a.stage, a.recruiter, a.updated_at,
            rn.note          AS notes,
            s.interview_date,
            f.comments       AS feedback
        FROM ats_candidates a
        LEFT JOIN recruiter_notes rn
               ON rn.note_id = (
                   SELECT note_id FROM recruiter_notes
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        LEFT JOIN interview_schedule s
               ON s.schedule_id = (
                   SELECT schedule_id FROM interview_schedule
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        LEFT JOIN interview_feedback f
               ON f.feedback_id = (
                   SELECT feedback_id FROM interview_feedback
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        ORDER BY a.updated_at DESC
    """
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        result = [_row_to_dict(cur, row) for row in rows]
        cur.close()
    return result


def _get_one(candidate_id: int, job_id: int) -> dict:
    sql = """
        SELECT
            a.ats_id, a.candidate_id, a.job_id, a.cand_name, a.email, a.phone,
            a.resume_score, a.stage, a.recruiter, a.updated_at,
            rn.note          AS notes,
            s.interview_date,
            f.comments       AS feedback
        FROM ats_candidates a
        LEFT JOIN recruiter_notes rn
               ON rn.note_id = (
                   SELECT note_id FROM recruiter_notes
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        LEFT JOIN interview_schedule s
               ON s.schedule_id = (
                   SELECT schedule_id FROM interview_schedule
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        LEFT JOIN interview_feedback f
               ON f.feedback_id = (
                   SELECT feedback_id FROM interview_feedback
                   WHERE ats_id = a.ats_id ORDER BY created_at DESC LIMIT 1
               )
        WHERE a.candidate_id = %s AND a.job_id = %s
    """
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(sql, (candidate_id, job_id))
        row = cur.fetchone()
        result = _row_to_dict(cur, row) if row else {}
        cur.close()
    return result


def _update_stage(candidate_id: int, job_id: int, stage: str) -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ats_candidates SET stage=%s WHERE candidate_id=%s AND job_id=%s",
            (stage, candidate_id, job_id),
        )
        cur.close()


def _update_field(candidate_id: int, job_id: int, field: str, value: Any) -> None:
    allowed = {"recruiter", "stage"}
    if field not in allowed:
        return
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE ats_candidates SET `{field}`=%s WHERE candidate_id=%s AND job_id=%s",
            (value, candidate_id, job_id),
        )
        cur.close()


# ── Score helper ───────────────────────────────────────────────────────────

def _skill_score(candidate: dict, job: dict) -> float:
    c = {s.strip().lower() for s in (candidate.get("skills") or "").split(",") if s.strip()}
    j = {s.strip().lower() for s in (job.get("skills_required") or "").split(",") if s.strip()}
    return round(len(c & j) / len(j) * 100, 1) if j else 0.0


# ── UI helpers ─────────────────────────────────────────────────────────────

def _badge(stage: str) -> str:
    cfg = _STAGE_CFG.get(stage, {"color": "#94a3b8", "bg": "rgba(148,163,184,0.12)", "border": "rgba(148,163,184,0.3)", "icon": ""})
    return (
        f"<span style='background:{cfg['bg']};color:{cfg['color']};"
        f"border:1px solid {cfg['border']};padding:3px 12px;"
        f"border-radius:20px;font-size:0.72rem;font-weight:700'>"
        f"{cfg['icon']} {html.escape(stage)}</span>"
    )


def _score_color(score: float) -> str:
    return "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"


def _kanban_card(rec: dict) -> str:
    cfg   = _STAGE_CFG.get(rec.get("stage", "Applied"), _STAGE_CFG["Applied"])
    score = rec.get("resume_score") or 0
    sc    = _score_color(score)
    return f"""
    <div style="background:rgba(255,255,255,0.04);border-radius:12px;padding:14px 16px;
                border:1px solid {cfg['border']};border-left:4px solid {cfg['color']};
                margin-bottom:10px">
        <div style="font-size:0.88rem;font-weight:700;color:#f1f5f9;margin-bottom:4px">
            {html.escape(rec.get('cand_name') or '—')}</div>
        <div style="font-size:0.72rem;color:#94a3b8;margin-bottom:8px">
            {html.escape(rec.get('email') or '—')} · {html.escape(rec.get('phone') or '—')}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span style="font-size:0.68rem;color:{sc};font-weight:700;
                         background:{sc}18;padding:2px 8px;border-radius:10px">
                🎯 {score}%</span>
            <span style="font-size:0.68rem;color:#94a3b8;background:rgba(255,255,255,0.06);
                         padding:2px 8px;border-radius:10px">
                📅 {rec.get('interview_date') or '—'}</span>
            <span style="font-size:0.68rem;color:#94a3b8;background:rgba(255,255,255,0.06);
                         padding:2px 8px;border-radius:10px">
                👤 {html.escape(rec.get('recruiter') or '—')}</span>
        </div>
    </div>"""


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header("📌 ATS Dashboard", "Candidate pipeline · Applied → Screening → Interview → Selected → Rejected")

    try:
        _init_table()
    except Exception as e:
        st.error(f"MySQL connection failed: {e}")
        return

    candidates = service.get_all_candidates()
    jobs       = service.jobs.get_all_jobs()

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    tab_board, tab_add, tab_table, tab_stats = st.tabs([
        "📋 Kanban Board", "➕ Add / Edit", "📊 Pipeline Table", "📈 Stats",
    ])

    # ══════════════════════════════════════════
    #  TAB 1 — Kanban Board (drag-drop via selectbox)
    # ══════════════════════════════════════════
    with tab_board:
        all_recs = _get_all()
        if not all_recs:
            st.info("No candidates in pipeline yet. Use **Add / Edit** tab to add.")
        else:
            grouped = {s: [r for r in all_recs if r.get("stage") == s] for s in _STAGES}
            cols = st.columns(5)
            for col, stage in zip(cols, _STAGES):
                cfg    = _STAGE_CFG[stage]
                bucket = grouped[stage]
                with col:
                    st.markdown(
                        f"<div style='background:{cfg['bg']};border:1px solid {cfg['border']};"
                        f"border-radius:12px;padding:10px 14px;margin-bottom:12px;text-align:center'>"
                        f"<div style='font-size:1.1rem'>{cfg['icon']}</div>"
                        f"<div style='font-size:0.75rem;font-weight:800;color:{cfg['color']};"
                        f"text-transform:uppercase;letter-spacing:0.06em'>{stage}</div>"
                        f"<div style='font-size:1.4rem;font-weight:900;color:#f1f5f9'>{len(bucket)}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    for rec in bucket:
                        st.markdown(_kanban_card(rec), unsafe_allow_html=True)
                        new_stage = st.selectbox(
                            "Move to", _STAGES,
                            index=_STAGES.index(stage),
                            key=f"kb_{rec['candidate_id']}_{rec['job_id']}",
                            label_visibility="collapsed",
                        )
                        if new_stage != stage:
                            _update_stage(rec["candidate_id"], rec["job_id"], new_stage)
                            st.rerun()
                        if rec.get("notes"):
                            with st.expander("📝 Notes"):
                                st.caption(rec["notes"])
                        if rec.get("feedback"):
                            with st.expander("💬 Feedback"):
                                st.caption(rec["feedback"])

    # ══════════════════════════════════════════
    #  TAB 2 — Add / Edit
    # ══════════════════════════════════════════
    with tab_add:
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                job_opts = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
                sel_job  = job_opts[st.selectbox("💼 Job", list(job_opts.keys()), key="ats_job")]
            with c2:
                cand_opts = {
                    f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                    for c in candidates
                }
                sel_cand = cand_opts[st.selectbox("👤 Candidate", list(cand_opts.keys()), key="ats_cand")]

        cid      = sel_cand["candidate_id"]
        jid      = sel_job["job_id"]
        existing = _get_one(cid, jid)
        score    = _skill_score(sel_cand, sel_job)
        name     = (sel_cand.get("name") or "Unknown").splitlines()[0]

        if existing:
            st.markdown(
                f"<div style='margin:12px 0'>Current stage: {_badge(existing.get('stage','Applied'))}</div>",
                unsafe_allow_html=True,
            )

        with st.container(border=True):
            f1, f2, f3 = st.columns(3)
            with f1:
                stage = st.selectbox(
                    "📍 Stage", _STAGES,
                    index=_STAGES.index(existing.get("stage", "Applied")),
                    key=f"ae_stage_{cid}_{jid}",
                )
            with f2:
                recruiter = st.text_input(
                    "👤 Recruiter", value=existing.get("recruiter") or "",
                    key=f"ae_rec_{cid}_{jid}",
                )
            with f3:
                idate_str = existing.get("interview_date") or ""
                try:
                    idate_default = date.fromisoformat(idate_str) if idate_str else None
                except ValueError:
                    idate_default = None
                interview_date = st.date_input(
                    "📅 Interview Date", value=idate_default,
                    key=f"ae_idate_{cid}_{jid}",
                )

            n1, n2 = st.columns(2)
            with n1:
                notes = st.text_area(
                    "📝 Notes", value=existing.get("notes") or "",
                    height=110, placeholder="Interview notes, observations...",
                    key=f"ae_notes_{cid}_{jid}",
                )
            with n2:
                feedback = st.text_area(
                    "💬 Feedback", value=existing.get("feedback") or "",
                    height=110, placeholder="Recruiter feedback...",
                    key=f"ae_fb_{cid}_{jid}",
                )

            st.markdown(
                f"<div style='display:flex;gap:24px;padding:10px 0;font-size:0.78rem;color:#94a3b8'>"
                f"<span>📧 {html.escape(sel_cand.get('email') or '—')}</span>"
                f"<span>📞 {html.escape(sel_cand.get('phone') or '—')}</span>"
                f"<span>🎯 Resume Score: <b style='color:#f1f5f9'>{score}%</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if st.button("💾 Save to ATS", type="primary", use_container_width=True, key=f"ae_save_{cid}_{jid}"):
                _upsert({
                    "candidate_id":   cid,
                    "job_id":         jid,
                    "cand_name":      name,
                    "email":          sel_cand.get("email") or "",
                    "phone":          sel_cand.get("phone") or "",
                    "resume_score":   score,
                    "stage":          stage,
                    "interview_date": str(interview_date) if interview_date else "",
                    "recruiter":      recruiter,
                    "notes":          notes,
                    "feedback":       feedback,
                })
                st.success(f"✅ {name} saved — stage: **{stage}**")
                st.rerun()

    # ══════════════════════════════════════════
    #  TAB 3 — Pipeline Table
    # ══════════════════════════════════════════
    with tab_table:
        all_recs = _get_all()
        if not all_recs:
            st.info("No pipeline records yet.")
        else:
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                f_stage = st.selectbox("Filter Stage", ["All"] + _STAGES, key="tbl_stage")
            with fc2:
                f_search = st.text_input("🔍 Search name / email", key="tbl_search")
            with fc3:
                f_sort = st.selectbox("Sort by", ["Updated", "Score ↓", "Score ↑", "Name"], key="tbl_sort")

            rows = all_recs
            if f_stage != "All":
                rows = [r for r in rows if r.get("stage") == f_stage]
            if f_search:
                q = f_search.lower()
                rows = [r for r in rows if q in (r.get("cand_name") or "").lower()
                        or q in (r.get("email") or "").lower()]
            if f_sort == "Score ↓":
                rows = sorted(rows, key=lambda r: r.get("resume_score") or 0, reverse=True)
            elif f_sort == "Score ↑":
                rows = sorted(rows, key=lambda r: r.get("resume_score") or 0)
            elif f_sort == "Name":
                rows = sorted(rows, key=lambda r: (r.get("cand_name") or "").lower())

            st.caption(f"Showing {len(rows)} of {len(all_recs)} records")

            for rec in rows:
                score = rec.get("resume_score") or 0
                sc    = _score_color(score)
                with st.container(border=True):
                    r1, r2, r3, r4 = st.columns([3, 2, 1, 1])
                    with r1:
                        st.markdown(
                            f"<div style='font-size:0.9rem;font-weight:700;color:#f1f5f9'>"
                            f"{html.escape(rec.get('cand_name') or '—')}</div>"
                            f"<div style='font-size:0.72rem;color:#94a3b8'>"
                            f"📧 {html.escape(rec.get('email') or '—')} &nbsp;·&nbsp; "
                            f"📞 {html.escape(rec.get('phone') or '—')}</div>",
                            unsafe_allow_html=True,
                        )
                    with r2:
                        st.markdown(
                            f"<div style='margin-top:4px'>{_badge(rec.get('stage','Applied'))}</div>"
                            f"<div style='font-size:0.7rem;color:#64748b;margin-top:4px'>"
                            f"📅 {rec.get('interview_date') or '—'} &nbsp; "
                            f"👤 {html.escape(rec.get('recruiter') or '—')}</div>",
                            unsafe_allow_html=True,
                        )
                    with r3:
                        st.markdown(
                            f"<div style='text-align:center;padding-top:4px'>"
                            f"<div style='font-size:1.1rem;font-weight:800;color:{sc}'>{score}%</div>"
                            f"<div style='font-size:0.62rem;color:#64748b'>Resume Score</div></div>",
                            unsafe_allow_html=True,
                        )
                    with r4:
                        new_s = st.selectbox(
                            "Stage", _STAGES,
                            index=_STAGES.index(rec.get("stage", "Applied")),
                            key=f"tbl_mv_{rec['candidate_id']}_{rec['job_id']}",
                            label_visibility="collapsed",
                        )
                        if new_s != rec.get("stage"):
                            _update_stage(rec["candidate_id"], rec["job_id"], new_s)
                            st.rerun()

                    if rec.get("notes") or rec.get("feedback"):
                        with st.expander("Notes & Feedback"):
                            if rec.get("notes"):
                                st.markdown(f"**Notes:** {rec['notes']}")
                            if rec.get("feedback"):
                                st.markdown(f"**Feedback:** {rec['feedback']}")

    # ══════════════════════════════════════════
    #  TAB 4 — Stats
    # ══════════════════════════════════════════
    with tab_stats:
        all_recs = _get_all()
        if not all_recs:
            st.info("No pipeline data yet.")
        else:
            total     = len(all_recs)
            selected  = sum(1 for r in all_recs if r.get("stage") == "Selected")
            rejected  = sum(1 for r in all_recs if r.get("stage") == "Rejected")
            active    = total - selected - rejected
            avg_score = round(sum(r.get("resume_score") or 0 for r in all_recs) / total, 1)

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("📋 Total",     total)
            m2.metric("🔄 Active",    active)
            m3.metric("✅ Selected",  selected)
            m4.metric("❌ Rejected",  rejected)
            m5.metric("🎯 Avg Score", f"{avg_score}%")

            st.divider()
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:14px'>"
                "📊 Stage Breakdown</div>",
                unsafe_allow_html=True,
            )
            for stage in _STAGES:
                count = sum(1 for r in all_recs if r.get("stage") == stage)
                pct   = round(count / total * 100) if total else 0
                cfg   = _STAGE_CFG[stage]
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;"
                    f"padding:10px 14px;background:rgba(255,255,255,0.03);"
                    f"border-radius:10px;border:1px solid rgba(255,255,255,0.06)'>"
                    f"<div style='min-width:110px;font-size:0.8rem;font-weight:600;color:#f1f5f9'>"
                    f"{cfg['icon']} {stage}</div>"
                    f"<div style='flex:1;background:rgba(255,255,255,0.08);border-radius:20px;"
                    f"height:8px;overflow:hidden'>"
                    f"<div style='background:{cfg['color']};height:100%;width:{pct}%;border-radius:20px'></div></div>"
                    f"<div style='min-width:60px;text-align:right;font-size:0.8rem;"
                    f"font-weight:700;color:{cfg['color']}'>{count} ({pct}%)</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.divider()
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:14px'>"
                "🏆 Top Candidates by Resume Score</div>",
                unsafe_allow_html=True,
            )
            for i, rec in enumerate(
                sorted(all_recs, key=lambda r: r.get("resume_score") or 0, reverse=True)[:5], 1
            ):
                score = rec.get("resume_score") or 0
                sc    = _score_color(score)
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:14px;padding:8px 14px;"
                    f"background:rgba(255,255,255,0.03);border-radius:10px;margin-bottom:6px;"
                    f"border:1px solid rgba(255,255,255,0.06)'>"
                    f"<span style='font-size:0.8rem;font-weight:800;color:#64748b;min-width:20px'>#{i}</span>"
                    f"<span style='font-size:0.85rem;font-weight:600;color:#f1f5f9;flex:1'>"
                    f"{html.escape(rec.get('cand_name') or '—')}</span>"
                    f"{_badge(rec.get('stage','Applied'))}"
                    f"<span style='font-size:0.85rem;font-weight:800;color:{sc}'>{score}%</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
