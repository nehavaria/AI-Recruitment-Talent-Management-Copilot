"""
Interview Scheduling — MySQL backed.
Allows recruiter to schedule interviews with candidate, interviewer,
date, time, meeting link, and mode (Online/Offline).
Displays upcoming interviews sorted by date/time.
Does not touch any existing module.
"""

import html
import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator

import mysql.connector
import streamlit as st

from config.settings import MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_MYSQL_CFG = {
    "host": MYSQL_HOST, "port": MYSQL_PORT, "database": MYSQL_DATABASE,
    "user": MYSQL_USER, "password": MYSQL_PASSWORD,
    "autocommit": False, "charset": "utf8mb4",
}

# ── MySQL ─────────────────────────────────────────────────────────────────

@contextmanager
def _db() -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(**_MYSQL_CFG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db() -> None:
    conn = mysql.connector.connect(**{**_MYSQL_CFG, "autocommit": True})
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recruiter_interviews (
                id             INT          PRIMARY KEY AUTO_INCREMENT,
                candidate_id   INT          NOT NULL DEFAULT 0,
                candidate_name VARCHAR(255) NOT NULL DEFAULT '',
                job_title      VARCHAR(255) NOT NULL DEFAULT '',
                interviewer    VARCHAR(255) NOT NULL DEFAULT '',
                interview_date VARCHAR(20)  NOT NULL DEFAULT '',
                interview_time VARCHAR(10)  NOT NULL DEFAULT '',
                mode           VARCHAR(20)  NOT NULL DEFAULT 'Online',
                meeting_link   VARCHAR(500) NOT NULL DEFAULT '',
                notes          VARCHAR(1000) NOT NULL DEFAULT '',
                created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migrate: add job_title if missing (table created before this column was added)
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'recruiter_interviews' AND COLUMN_NAME = 'job_title'
        """, (MYSQL_DATABASE,))
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE recruiter_interviews ADD COLUMN job_title VARCHAR(255) NOT NULL DEFAULT '' AFTER candidate_name")
        cur.close()
    finally:
        conn.close()


def _save_schedule(candidate_id: int, candidate_name: str, job_title: str,
                   interviewer: str, interview_date: str, interview_time: str,
                   mode: str, meeting_link: str, notes: str) -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO recruiter_interviews
                (candidate_id, candidate_name, job_title, interviewer, interview_date,
                 interview_time, mode, meeting_link, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (candidate_id, candidate_name, job_title, interviewer, interview_date,
              interview_time, mode, meeting_link, notes))
        cur.close()


def _delete_schedule(schedule_id: int) -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM recruiter_interviews WHERE id=%s", (schedule_id,))
        cur.close()


def _load_upcoming() -> list[dict]:
    today = date.today().isoformat()
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM recruiter_interviews
            WHERE interview_date >= %s
            ORDER BY interview_date ASC, interview_time ASC
        """, (today,))
        rows = cur.fetchall()
        cur.close()
    return rows


def _load_all_schedules() -> list[dict]:
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM recruiter_interviews
            ORDER BY interview_date DESC, interview_time DESC
        """)
        rows = cur.fetchall()
        cur.close()
    return rows


# ── UI helpers ─────────────────────────────────────────────────────────────

def _mode_badge(mode: str) -> str:
    if mode == "Online":
        return "<span style='background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:2px 10px;border-radius:20px;font-size:0.68rem;font-weight:700'>🌐 Online</span>"
    return "<span style='background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:2px 10px;border-radius:20px;font-size:0.68rem;font-weight:700'>🏢 Offline</span>"


def _metric(col, label: str, value, color: str) -> None:
    col.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:16px;padding:18px 20px;"
        f"border:1px solid {color}30;text-align:center'>"
        f"<div style='font-size:1.8rem;font-weight:900;color:{color}'>{value}</div>"
        f"<div style='font-size:0.68rem;color:#94a3b8;margin-top:5px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:0.08em'>{label}</div></div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header("📅 Interview Scheduling", "Schedule interviews · Track upcoming sessions · MySQL backed")

    _init_db()

    candidates  = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs        = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))
    all_scheds  = _load_all_schedules()
    upcoming    = _load_upcoming()

    # ── Top metric cards ──────────────────────────────────────────────────
    today_str   = date.today().isoformat()
    total_sched = len(all_scheds)
    upcoming_ct = len(upcoming)
    online_ct   = sum(1 for s in all_scheds if s["mode"] == "Online")
    offline_ct  = sum(1 for s in all_scheds if s["mode"] == "Offline")

    m1, m2, m3, m4 = st.columns(4)
    _metric(m1, "Total Scheduled", total_sched, "#3b82f6")
    _metric(m2, "Upcoming",        upcoming_ct, "#f59e0b")
    _metric(m3, "Online",          online_ct,   "#8b5cf6")
    _metric(m4, "Offline",         offline_ct,  "#10b981")
    st.divider()

    tab_schedule, tab_upcoming, tab_all = st.tabs([
        "➕ Schedule Interview", "📅 Upcoming Interviews", "📋 All Interviews"
    ])

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 1 — SCHEDULE FORM
    # ══════════════════════════════════════════════════════════════════════
    with tab_schedule:
        if not candidates:
            st.info("No candidates found. Upload resumes first.")
        else:
            with st.container(border=True):
                st.markdown(
                    "<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
                    "margin-bottom:16px'>🗓️ New Interview</div>",
                    unsafe_allow_html=True,
                )

                cand_opts = {
                    f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                    for c in candidates
                }
                job_opts = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
                f1, f2 = st.columns(2)
                with f1:
                    sel_cand = cand_opts[st.selectbox("👤 Candidate", list(cand_opts.keys()), key="sch_cand")]
                with f2:
                    sel_job = job_opts[st.selectbox("💼 Applying For", list(job_opts.keys()), key="sch_job")]
                f1b, f2b = st.columns(2)
                with f1b:
                    interviewer = st.text_input("🧑‍💼 Interviewer Name", placeholder="e.g. Priya Sharma", key="sch_interviewer")
                with f2b:
                    st.text_input("💼 Job Role", value=sel_job.get('job_title',''), disabled=True, key="sch_job_display")

                f3, f4, f5 = st.columns(3)
                with f3:
                    idate = st.date_input("📅 Interview Date", value=date.today(), key="sch_date")
                with f4:
                    itime = st.time_input("🕐 Interview Time", key="sch_time")
                with f5:
                    mode = st.selectbox("📍 Mode", ["Online", "Offline"], key="sch_mode")

                meeting_link = ""
                if mode == "Online":
                    meeting_link = st.text_input(
                        "🔗 Meeting Link",
                        placeholder="https://meet.google.com/...",
                        key="sch_link",
                    )
                else:
                    st.text_input("🔗 Meeting Link", value="N/A (Offline)", disabled=True, key="sch_link_off")
                notes = st.text_area("📝 Notes", placeholder="Any additional notes…", height=80, key="sch_notes")

                if st.button("💾 Schedule Interview", type="primary", use_container_width=True, key="sch_save"):
                    if not interviewer.strip():
                        st.error("Please enter the interviewer name.")
                    else:
                        cname    = (sel_cand.get("name") or "Unknown").splitlines()[0]
                        jtitle   = sel_job.get("job_title") or ""
                        time_obj = itime if hasattr(itime, "strftime") else itime
                        time_str = time_obj.strftime("%H:%M") if hasattr(time_obj, "strftime") else str(time_obj)[:5]
                        _save_schedule(
                            sel_cand["candidate_id"], cname, jtitle,
                            interviewer.strip(),
                            idate.isoformat(),
                            time_str,
                            mode,
                            meeting_link.strip() if mode == "Online" else "",
                            notes.strip(),
                        )
                        st.success(f"✅ Interview scheduled for **{cname}** applying for **{jtitle}** on {idate} at {time_str} ({mode})")
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 2 — UPCOMING INTERVIEWS
    # ══════════════════════════════════════════════════════════════════════
    with tab_upcoming:
        if not upcoming:
            st.info("No upcoming interviews scheduled.")
        else:
            st.caption(f"{len(upcoming)} upcoming interview(s)")
            for s in upcoming:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 3, 1])
                    with c1:
                        name = html.escape(s["candidate_name"] or "—")
                        ini  = "".join(w[0].upper() for w in (s["candidate_name"] or "U").split()[:2])
                        st.markdown(
                            f"<div style='display:flex;align-items:center;gap:10px'>"
                            f"<div style='width:38px;height:38px;border-radius:10px;flex-shrink:0;"
                            f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
                            f"display:flex;align-items:center;justify-content:center;"
                            f"font-weight:900;color:#fff;font-size:0.8rem'>{ini}</div>"
                            f"<div>"
                            f"<div style='font-size:0.92rem;font-weight:700;color:#f1f5f9'>{name}</div>"
                            f"<div style='font-size:0.72rem;color:#a78bfa'>💼 {html.escape(s.get('job_title') or '—')}</div>"
                            f"<div style='font-size:0.72rem;color:#94a3b8'>🧑‍💼 {html.escape(s['interviewer'] or '—')}</div>"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        link_html = ""
                        if s.get("meeting_link"):
                            link_html = f"&nbsp;·&nbsp; <a href='{html.escape(s['meeting_link'])}' target='_blank' style='color:#60a5fa;font-size:0.68rem'>🔗 Join</a>"
                        st.markdown(
                            f"<div style='padding-top:6px'>"
                            f"<div style='font-size:0.8rem;font-weight:700;color:#f1f5f9'>"
                            f"📅 {s['interview_date']} &nbsp; 🕐 {s['interview_time']}</div>"
                            f"<div style='margin-top:4px'>{_mode_badge(s['mode'])}{link_html}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        if s.get("notes"):
                            st.caption(f"📝 {s['notes']}")
                    with c3:
                        if st.button("🗑️", key=f"del_up_{s['id']}", help="Cancel interview"):
                            _delete_schedule(s["id"])
                            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 3 — ALL INTERVIEWS
    # ══════════════════════════════════════════════════════════════════════
    with tab_all:
        if not all_scheds:
            st.info("No interviews scheduled yet.")
        else:
            # filter
            fa, fb = st.columns([3, 2])
            with fa:
                search = st.text_input("🔍 Search candidate / interviewer", key="all_search")
            with fb:
                mode_f = st.selectbox("Filter Mode", ["All", "Online", "Offline"], key="all_mode_f")

            rows = all_scheds
            if search:
                q = search.lower()
                rows = [r for r in rows if q in (r["candidate_name"] or "").lower()
                        or q in (r["interviewer"] or "").lower()]
            if mode_f != "All":
                rows = [r for r in rows if r["mode"] == mode_f]

            st.caption(f"Showing {len(rows)} of {len(all_scheds)} interviews")
            st.divider()

            today_str = date.today().isoformat()
            for s in rows:
                is_past = s["interview_date"] < today_str
                border_color = "rgba(100,116,139,0.3)" if is_past else "rgba(245,158,11,0.4)"
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    with c1:
                        past_tag = "<span style='font-size:0.6rem;color:#64748b;background:rgba(100,116,139,0.15);padding:1px 6px;border-radius:8px;margin-left:6px'>Past</span>" if is_past else ""
                        st.markdown(
                            f"<div style='font-size:0.9rem;font-weight:700;color:#f1f5f9'>"
                            f"{html.escape(s['candidate_name'] or '—')}{past_tag}</div>"
                            f"<div style='font-size:0.72rem;color:#a78bfa'>💼 {html.escape(s.get('job_title') or '—')}</div>"
                            f"<div style='font-size:0.72rem;color:#94a3b8'>🧑‍💼 {html.escape(s['interviewer'] or '—')}</div>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f"<div style='font-size:0.8rem;color:#f1f5f9;padding-top:4px'>"
                            f"📅 {s['interview_date']}<br>🕐 {s['interview_time']}</div>",
                            unsafe_allow_html=True,
                        )
                    with c3:
                        link_html = ""
                        if s.get("meeting_link"):
                            link_html = f"<br><a href='{html.escape(s['meeting_link'])}' target='_blank' style='color:#60a5fa;font-size:0.68rem'>🔗 Join Meeting</a>"
                        st.markdown(
                            f"<div style='padding-top:4px'>{_mode_badge(s['mode'])}{link_html}</div>",
                            unsafe_allow_html=True,
                        )
                    with c4:
                        if st.button("🗑️", key=f"del_all_{s['id']}", help="Delete"):
                            _delete_schedule(s["id"])
                            st.rerun()
