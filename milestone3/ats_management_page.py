"""
ATS Management Page
Loads candidate details directly from MySQL (candidates table).
Status dropdown updates MySQL immediately on change.
No new tables. No existing modules modified.
"""

import html
import logging
from contextlib import contextmanager
from datetime import date
from typing import Generator

import mysql.connector
import streamlit as st

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)
from database.ats_schema import init_ats_schema
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

_STAGE_CFG = {
    "Applied":   {"color": "#3b82f6", "bg": "rgba(59,130,246,0.12)",  "border": "rgba(59,130,246,0.35)",  "icon": "📥"},
    "Screening": {"color": "#8b5cf6", "bg": "rgba(139,92,246,0.12)",  "border": "rgba(139,92,246,0.35)",  "icon": "🔍"},
    "Interview": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.12)",  "border": "rgba(245,158,11,0.35)",  "icon": "🎤"},
    "Selected":  {"color": "#10b981", "bg": "rgba(16,185,129,0.12)",  "border": "rgba(16,185,129,0.35)",  "icon": "✅"},
    "Rejected":  {"color": "#ef4444", "bg": "rgba(239,68,68,0.12)",   "border": "rgba(239,68,68,0.35)",   "icon": "❌"},
}


# ── MySQL connection ───────────────────────────────────────────────────────

@contextmanager
def _db() -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        autocommit=False, charset="utf8mb4",
        collation="utf8mb4_unicode_ci", raise_on_warnings=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(cursor, row: tuple) -> dict:
    return dict(zip([c[0] for c in cursor.description], row))


# ── Core upsert — UPDATE first, INSERT if no row exists ───────────────────
# Cannot use ON DUPLICATE KEY UPDATE with NULL job_id because
# MySQL treats NULL != NULL in unique indexes.

def _ats_upsert(candidate_id: int, stage: str, recruiter: str = "", resume_score: float = 0.0) -> int:
    """Update existing row or insert new one. Returns ats_id."""
    with _db() as conn:
        cur = conn.cursor()

        # Try UPDATE first
        cur.execute("""
            UPDATE ats_candidates
               SET stage=%s, recruiter=%s, resume_score=%s
             WHERE candidate_id=%s AND job_id IS NULL
        """, (stage, recruiter, resume_score, candidate_id))
        updated = cur.rowcount

        if not updated:
            # No row yet — INSERT
            cur.execute("""
                INSERT INTO ats_candidates
                    (candidate_id, job_id, stage, recruiter, resume_score)
                VALUES (%s, NULL, %s, %s, %s)
            """, (candidate_id, stage, recruiter, resume_score))

        # Fetch ats_id
        cur.execute(
            "SELECT ats_id FROM ats_candidates WHERE candidate_id=%s AND job_id IS NULL",
            (candidate_id,)
        )
        row = cur.fetchone()
        cur.close()
    return row[0] if row else 0


def _stage_only(candidate_id: int, stage: str) -> None:
    """Update only stage — called instantly on dropdown change."""
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ats_candidates SET stage=%s WHERE candidate_id=%s AND job_id IS NULL",
            (stage, candidate_id)
        )
        updated = cur.rowcount
        if not updated:
            cur.execute(
                "INSERT INTO ats_candidates (candidate_id, job_id, stage) VALUES (%s, NULL, %s)",
                (candidate_id, stage)
            )
        cur.close()


def _save_schedule(ats_id: int, interview_date) -> None:
    if not ats_id or not interview_date:
        return
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT schedule_id FROM interview_schedule WHERE ats_id=%s ORDER BY created_at DESC LIMIT 1",
            (ats_id,)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE interview_schedule SET interview_date=%s WHERE schedule_id=%s",
                (str(interview_date), row[0])
            )
        else:
            cur.execute(
                "INSERT INTO interview_schedule (ats_id, interview_date) VALUES (%s, %s)",
                (ats_id, str(interview_date))
            )
        cur.close()


# ── Data loader ────────────────────────────────────────────────────────────

def _load_candidates() -> list[dict]:
    sql = """
        SELECT
            c.candidate_id,
            c.name,
            c.email,
            c.phone,
            c.skills,
            COALESCE(a.resume_score, 0)       AS resume_score,
            COALESCE(a.stage, 'Applied')       AS stage,
            COALESCE(a.recruiter, '')          AS recruiter,
            COALESCE(a.ats_id, 0)             AS ats_id,
            s.interview_date
        FROM candidates c
        LEFT JOIN ats_candidates a
               ON a.candidate_id = c.candidate_id
              AND a.job_id IS NULL
        LEFT JOIN interview_schedule s
               ON s.schedule_id = (
                   SELECT schedule_id FROM interview_schedule
                   WHERE ats_id = a.ats_id
                   ORDER BY created_at DESC LIMIT 1
               )
        ORDER BY c.name ASC
    """
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        result = [_row_to_dict(cur, r) for r in rows]
        cur.close()
    return result


# ── UI helpers ─────────────────────────────────────────────────────────────

def _badge(stage: str) -> str:
    cfg = _STAGE_CFG.get(stage, {"color": "#94a3b8", "bg": "rgba(148,163,184,0.1)", "border": "rgba(148,163,184,0.3)", "icon": ""})
    return (
        f"<span style='background:{cfg['bg']};color:{cfg['color']};"
        f"border:1px solid {cfg['border']};padding:3px 12px;"
        f"border-radius:20px;font-size:0.72rem;font-weight:700'>"
        f"{cfg['icon']} {html.escape(stage)}</span>"
    )


def _score_bar(score: float) -> str:
    color = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    pct   = min(score, 100)
    return (
        f"<div style='display:flex;align-items:center;gap:8px'>"
        f"<div style='flex:1;background:rgba(255,255,255,0.08);border-radius:20px;height:6px;overflow:hidden'>"
        f"<div style='background:{color};height:100%;width:{pct}%;border-radius:20px'></div></div>"
        f"<span style='font-size:0.75rem;font-weight:700;color:{color};min-width:38px'>{score}%</span>"
        f"</div>"
    )


def _metrics(records: list[dict]) -> None:
    total    = len(records)
    selected = sum(1 for r in records if r["stage"] == "Selected")
    rejected = sum(1 for r in records if r["stage"] == "Rejected")
    active   = total - selected - rejected
    avg      = round(sum(r["resume_score"] for r in records) / total, 1) if total else 0

    for col, label, val, color in zip(
        st.columns(5),
        ["Total", "Active", "Selected", "Rejected", "Avg Score"],
        [total, active, selected, rejected, f"{avg}%"],
        ["#3b82f6", "#8b5cf6", "#10b981", "#ef4444", "#f59e0b"],
    ):
        col.markdown(
            f"<div style='background:rgba(255,255,255,0.04);border-radius:14px;"
            f"padding:16px 20px;border:1px solid {color}30;text-align:center'>"
            f"<div style='font-size:1.6rem;font-weight:900;color:{color}'>{val}</div>"
            f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:4px;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.06em'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header("🗂️ ATS Management", "Manage candidate records · Status updates save to MySQL instantly")

    if "ats_schema_ready" not in st.session_state:
        try:
            init_ats_schema()
            st.session_state["ats_schema_ready"] = True
        except Exception as e:
            st.error(f"MySQL connection failed: {e}")
            return

    records = _load_candidates()
    if not records:
        st.info("No candidates found. Upload resumes first.")
        return

    _metrics(records)
    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────
    fa, fb, fc = st.columns([3, 2, 2])
    with fa:
        search = st.text_input("🔍 Search name / email", placeholder="Type to filter...", key="mgmt_search")
    with fb:
        f_stage = st.selectbox("Filter by Status", ["All"] + _STAGES, key="mgmt_fstage")
    with fc:
        f_sort = st.selectbox("Sort by", ["Name A-Z", "Score ↓", "Score ↑", "Stage"], key="mgmt_sort")

    rows = records
    if search:
        q = search.lower()
        rows = [r for r in rows if q in (r["name"] or "").lower() or q in (r["email"] or "").lower()]
    if f_stage != "All":
        rows = [r for r in rows if r["stage"] == f_stage]
    if f_sort == "Score ↓":
        rows = sorted(rows, key=lambda r: r["resume_score"], reverse=True)
    elif f_sort == "Score ↑":
        rows = sorted(rows, key=lambda r: r["resume_score"])
    elif f_sort == "Stage":
        rows = sorted(rows, key=lambda r: _STAGES.index(r["stage"]))
    else:
        rows = sorted(rows, key=lambda r: (r["name"] or "").lower())

    st.caption(f"Showing {len(rows)} of {len(records)} candidates")
    st.divider()

    # ── Candidate cards ───────────────────────────────────────────────────
    @st.fragment
    def _candidate_card(rec: dict) -> None:
        cid       = rec["candidate_id"]
        current_stage_val = st.session_state.get(f"mgmt_stage_{cid}", rec["stage"])
        stage_idx = _STAGES.index(current_stage_val) if current_stage_val in _STAGES else 0

        idate_val = rec.get("interview_date")
        if isinstance(idate_val, date):
            idate_default = idate_val
        elif isinstance(idate_val, str) and idate_val:
            try:
                idate_default = date.fromisoformat(str(idate_val))
            except ValueError:
                idate_default = None
        else:
            idate_default = None

        with st.container(border=True):

            # ── Header row ────────────────────────────────────────────────
            h1, h2 = st.columns([5, 2])
            with h1:
                initials = "".join(w[0].upper() for w in (rec["name"] or "U").split()[:2])
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:12px'>"
                    f"<div style='width:42px;height:42px;border-radius:12px;flex-shrink:0;"
                    f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
                    f"display:flex;align-items:center;justify-content:center;"
                    f"font-weight:900;color:#fff;font-size:1rem'>{initials}</div>"
                    f"<div>"
                    f"<div style='font-size:0.95rem;font-weight:700;color:#f1f5f9'>"
                    f"{html.escape(rec['name'] or '—')}</div>"
                    f"<div style='font-size:0.72rem;color:#94a3b8'>"
                    f"📧 {html.escape(rec['email'] or '—')} &nbsp;·&nbsp; "
                    f"📞 {html.escape(rec['phone'] or '—')}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
            with h2:
                current_stage = st.session_state.get(f"mgmt_stage_{cid}", rec["stage"])
                st.markdown(
                    f"<div style='text-align:right;padding-top:6px'>{_badge(current_stage)}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"<div style='margin:8px 0 4px'>{_score_bar(rec['resume_score'])}</div>",
                unsafe_allow_html=True,
            )

            # ── Editable fields ───────────────────────────────────────────
            e1, e2, e3, e4 = st.columns([2, 2, 2, 2])

            with e1:
                def _on_change(cid=cid):
                    new_stage = st.session_state[f"mgmt_stage_{cid}"]
                    try:
                        _stage_only(cid, new_stage)
                        st.session_state[f"mgmt_saved_{cid}"] = f"✓ {new_stage} saved"
                        st.session_state[f"mgmt_err_{cid}"]   = ""
                    except Exception as ex:
                        st.session_state[f"mgmt_err_{cid}"]   = str(ex)
                        st.session_state[f"mgmt_saved_{cid}"] = ""

                st.selectbox(
                    "📍 Status", _STAGES,
                    index=stage_idx,
                    key=f"mgmt_stage_{cid}",
                    on_change=_on_change,
                )

                saved_msg = st.session_state.get(f"mgmt_saved_{cid}", "")
                err_msg   = st.session_state.get(f"mgmt_err_{cid}", "")
                if saved_msg:
                    cfg = _STAGE_CFG.get(st.session_state.get(f"mgmt_stage_{cid}", "Applied"), _STAGE_CFG["Applied"])
                    st.markdown(
                        f"<div style='font-size:0.68rem;color:{cfg['color']};margin-top:2px'>{saved_msg}</div>",
                        unsafe_allow_html=True,
                    )
                if err_msg:
                    st.markdown(
                        f"<div style='font-size:0.68rem;color:#ef4444;margin-top:2px'>⚠ {err_msg}</div>",
                        unsafe_allow_html=True,
                    )

            with e2:
                new_recruiter = st.text_input(
                    "👤 Recruiter", value=rec["recruiter"] or "",
                    key=f"mgmt_rec_{cid}",
                )
            with e3:
                new_score = st.number_input(
                    "🎯 Resume Score", min_value=0.0, max_value=100.0,
                    value=float(rec["resume_score"]),
                    step=0.5, format="%.1f",
                    key=f"mgmt_score_{cid}",
                )
            with e4:
                new_idate = st.date_input(
                    "📅 Interview Date", value=idate_default,
                    key=f"mgmt_idate_{cid}",
                )

            # ── Save details button ───────────────────────────────────────
            if st.button("💾 Save Details", key=f"mgmt_save_{cid}", type="primary"):
                try:
                    current = st.session_state.get(f"mgmt_stage_{cid}", rec["stage"])
                    ats_id  = _ats_upsert(cid, current, new_recruiter, new_score)
                    _save_schedule(ats_id, new_idate)
                    st.success(f"✅ {rec['name']} saved to MySQL")
                    logger.info("ATS saved candidate_id=%s stage=%s", cid, current)
                except Exception as e:
                    st.error(f"Save failed: {e}")

    for rec in rows:
        _candidate_card(rec)
