"""
ATS Dashboard — MySQL backed, zero blink.
"""

import html
import logging
from contextlib import contextmanager
from datetime import date
from typing import Generator

import mysql.connector
import streamlit as st

from config.settings import MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_STAGES  = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

_STAGE_CFG = {
    "Applied":   {"color": "#3b82f6", "bg": "rgba(59,130,246,0.13)",  "border": "rgba(59,130,246,0.4)",  "icon": "📥", "glow": "rgba(59,130,246,0.25)"},
    "Screening": {"color": "#8b5cf6", "bg": "rgba(139,92,246,0.13)",  "border": "rgba(139,92,246,0.4)",  "icon": "🔍", "glow": "rgba(139,92,246,0.25)"},
    "Interview": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.13)",  "border": "rgba(245,158,11,0.4)",  "icon": "🎤", "glow": "rgba(245,158,11,0.25)"},
    "Selected":  {"color": "#10b981", "bg": "rgba(16,185,129,0.13)",  "border": "rgba(16,185,129,0.4)",  "icon": "✅", "glow": "rgba(16,185,129,0.25)"},
    "Rejected":  {"color": "#ef4444", "bg": "rgba(239,68,68,0.13)",   "border": "rgba(239,68,68,0.4)",   "icon": "❌", "glow": "rgba(239,68,68,0.25)"},
}

# ── MySQL ──────────────────────────────────────────────────────────────────

_MYSQL_CFG = {
    "host": MYSQL_HOST, "port": MYSQL_PORT, "database": MYSQL_DATABASE,
    "user": MYSQL_USER, "password": MYSQL_PASSWORD,
    "autocommit": False, "charset": "utf8mb4",
}

_db_initialized = False  # guard: run CREATE TABLE IF NOT EXISTS once per process


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
    global _db_initialized
    if _db_initialized:
        return
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ats_pipeline (
                candidate_id    INT          NOT NULL,
                recruiter_email VARCHAR(255) NOT NULL DEFAULT '',
                job_id          INT          NOT NULL DEFAULT 0,
                stage           VARCHAR(50)  NOT NULL DEFAULT 'Applied',
                recruiter       VARCHAR(255) NOT NULL DEFAULT '',
                resume_score    FLOAT        NOT NULL DEFAULT 0.0,
                interview_date  VARCHAR(20)  NOT NULL DEFAULT '',
                notes           TEXT         NOT NULL,
                feedback        TEXT         NOT NULL,
                recruiter_notes TEXT         NOT NULL,
                updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (candidate_id, recruiter_email)
            )
        """)
        cur.close()
    _db_initialized = True


def _load_all(recruiter_email: str = "") -> dict[int, dict]:
    """Load pipeline rows scoped to the logged-in recruiter."""
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        if recruiter_email:
            cur.execute("SELECT * FROM ats_pipeline WHERE recruiter_email = %s", (recruiter_email,))
        else:
            cur.execute("SELECT * FROM ats_pipeline")
        rows = cur.fetchall()
        cur.close()
    return {r["candidate_id"]: r for r in rows}


def _add_to_pipeline(cid: int, job_id: int, score: float = 0.0, recruiter_email: str = "") -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT IGNORE INTO ats_pipeline (candidate_id, job_id, resume_score, recruiter_email, notes, feedback, recruiter_notes) VALUES (%s, %s, %s, %s, '', '', '')",
            (cid, job_id, score, recruiter_email),
        )
        cur.close()


def _compute_score(candidate: dict, job: dict) -> float:
    """Skill-match score: % of job's required skills found in candidate's skills."""
    c = {s.strip().lower() for s in (candidate.get("skills") or "").split(",") if s.strip()}
    j = {s.strip().lower() for s in (job.get("skills_required") or "").split(",") if s.strip()}
    if not j:
        return round(len(c) / max(len(c), 1) * 50, 1)  # 50% base if no job skills defined
    return round(len(c & j) / len(j) * 100, 1)


def _backfill_scores(candidates: list[dict], jobs_map: dict[int, dict], recruiter_email: str = "") -> None:
    """Update resume_score=0 rows with computed skill-match scores."""
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        if recruiter_email:
            cur.execute("SELECT candidate_id, job_id FROM ats_pipeline WHERE resume_score = 0 AND recruiter_email = %s", (recruiter_email,))
        else:
            cur.execute("SELECT candidate_id, job_id FROM ats_pipeline WHERE resume_score = 0")
        rows = cur.fetchall()
        cur.close()

    if not rows:
        return

    cand_map = {c["candidate_id"]: c for c in candidates}
    with _db() as conn:
        cur = conn.cursor()
        for row in rows:
            cand = cand_map.get(row["candidate_id"], {})
            job  = jobs_map.get(row["job_id"], {})
            score = _compute_score(cand, job)
            if score > 0:
                cur.execute(
                    "UPDATE ats_pipeline SET resume_score=%s WHERE candidate_id=%s",
                    (score, row["candidate_id"]),
                )
        cur.close()


def _save_recruiter_notes(cid: int, notes: str, recruiter_email: str = "") -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ats_pipeline SET recruiter_notes=%s WHERE candidate_id=%s AND recruiter_email=%s",
            (notes, cid, recruiter_email),
        )
        cur.close()


def _update_stage(cid: int, stage: str, recruiter_email: str = "") -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ats_pipeline SET stage=%s WHERE candidate_id=%s AND recruiter_email=%s",
            (stage, cid, recruiter_email),
        )
        cur.close()


def _save_full(cid: int, stage: str, recruiter: str,
               score: float, idate: str, notes: str, feedback: str, job_id: int = 0, recruiter_email: str = "") -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE ats_pipeline
               SET stage=%s, recruiter=%s, resume_score=%s,
                   interview_date=%s, notes=%s, feedback=%s, job_id=%s
             WHERE candidate_id=%s AND recruiter_email=%s
        """, (stage, recruiter, score, idate, notes, feedback, job_id, cid, recruiter_email))
        cur.close()


# ── UI helpers ─────────────────────────────────────────────────────────────

def _badge(stage: str) -> str:
    cfg = _STAGE_CFG.get(stage, {"color": "#94a3b8", "bg": "rgba(148,163,184,0.1)", "border": "rgba(148,163,184,0.3)", "icon": ""})
    return (
        f"<span style='background:{cfg['bg']};color:{cfg['color']};"
        f"border:1px solid {cfg['border']};padding:4px 14px;"
        f"border-radius:20px;font-size:0.72rem;font-weight:700'>"
        f"{cfg['icon']} {html.escape(stage)}</span>"
    )


def _score_bar(score: float) -> str:
    c = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    p = min(max(score, 0), 100)
    return (
        f"<div style='display:flex;align-items:center;gap:8px;margin:4px 0'>"
        f"<div style='flex:1;background:rgba(255,255,255,0.08);border-radius:20px;height:7px;overflow:hidden'>"
        f"<div style='background:{c};height:100%;width:{p}%;border-radius:20px'></div></div>"
        f"<span style='font-size:0.75rem;font-weight:800;color:{c};min-width:40px;text-align:right'>{score:.1f}%</span>"
        f"</div>"
    )


def _metric(col, label: str, value, color: str) -> None:
    col.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:16px;padding:18px 20px;"
        f"border:1px solid {color}30;text-align:center'>"
        f"<div style='font-size:1.8rem;font-weight:900;color:{color}'>{value}</div>"
        f"<div style='font-size:0.68rem;color:#94a3b8;margin-top:5px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:0.08em'>{label}</div></div>",
        unsafe_allow_html=True,
    )


# ── key helpers ────────────────────────────────────────────────────────────

def _sk(prefix: str, cid: int) -> str:
    return f"{prefix}_{cid}"


def _seed(key: str, value) -> None:
    """Write to session_state only if key is not already there."""
    if key not in st.session_state:
        st.session_state[key] = value


# ══════════════════════════════════════════════════════════════════════════
#  TAB — KANBAN
# ══════════════════════════════════════════════════════════════════════════

def _tab_kanban(candidates: list[dict], ats: dict[int, dict], jobs: dict[int, str]) -> None:
    # Seed once from DB
    for c in candidates:
        cid = c["candidate_id"]
        _seed(_sk("kb", cid), ats.get(cid, {}).get("stage", "Applied"))

    # Group by live session_state value — no DB read needed
    grouped: dict[str, list] = {s: [] for s in _STAGES}
    for c in candidates:
        cid = c["candidate_id"]
        grouped[st.session_state[_sk("kb", cid)]].append((c, ats.get(cid, {})))

    cols = st.columns(5, gap="small")
    for col, stage in zip(cols, _STAGES):
        cfg = _STAGE_CFG[stage]
        bucket = grouped[stage]
        with col:
            st.markdown(
                f"<div style='background:{cfg['bg']};border:1px solid {cfg['border']};"
                f"border-radius:14px;padding:12px 14px;margin-bottom:14px;text-align:center;"
                f"box-shadow:0 4px 16px {cfg['glow']}'>"
                f"<div style='font-size:1.4rem'>{cfg['icon']}</div>"
                f"<div style='font-size:0.72rem;font-weight:800;color:{cfg['color']};"
                f"text-transform:uppercase;letter-spacing:0.08em;margin-top:4px'>{stage}</div>"
                f"<div style='font-size:1.6rem;font-weight:900;color:#f1f5f9'>{len(bucket)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            for c, row in bucket:
                cid   = c["candidate_id"]
                score = row.get("resume_score", 0.0)
                sc    = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
                name  = (c.get("name") or "Unknown").splitlines()[0]
                ini   = "".join(w[0].upper() for w in name.split()[:2]) or "?"
                st.markdown(
                    f"<div style='background:rgba(255,255,255,0.05);border-radius:12px;"
                    f"padding:12px 14px;border:1px solid {cfg['border']};"
                    f"border-left:4px solid {cfg['color']};margin-bottom:8px'>"
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>"
                    f"<div style='width:32px;height:32px;border-radius:8px;flex-shrink:0;"
                    f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
                    f"display:flex;align-items:center;justify-content:center;"
                    f"font-weight:900;color:#fff;font-size:0.75rem'>{ini}</div>"
                    f"<div style='min-width:0'>"
                    f"<div style='font-size:0.8rem;font-weight:700;color:#f1f5f9;"
                    f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{html.escape(name)}</div>"
                    f"<div style='font-size:0.65rem;color:#94a3b8;white-space:nowrap;"
                    f"overflow:hidden;text-overflow:ellipsis'>{html.escape(c.get('email') or '—')}</div>"
                    f"</div></div>"
                    f"<div style='font-size:0.62rem;color:#a78bfa;font-weight:600;"
                    f"background:rgba(139,92,246,0.12);padding:2px 7px;border-radius:8px;"
                    f"margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                    f"💼 {html.escape(jobs.get(row.get('job_id', 0), 'No Job Assigned'))}</div>"
                    f"<span style='font-size:0.62rem;color:{sc};font-weight:700;"
                    f"background:{sc}18;padding:2px 7px;border-radius:8px'>🎯 {score:.0f}%</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                def _kb_change(cid=cid):
                    _update_stage(cid, st.session_state[_sk("kb", cid)])
                st.selectbox(
                    "stage", _STAGES,
                    key=_sk("kb", cid),
                    on_change=_kb_change,
                    label_visibility="collapsed",
                )


# ══════════════════════════════════════════════════════════════════════════
#  TAB — PIPELINE TABLE
# ══════════════════════════════════════════════════════════════════════════

def _tab_table(candidates: list[dict], ats: dict[int, dict], jobs: dict[int, str]) -> None:
    # Seed once from DB
    for c in candidates:
        cid = c["candidate_id"]
        _seed(_sk("tbl", cid), ats.get(cid, {}).get("stage", "Applied"))

    fa, fb, fc = st.columns([3, 2, 2])
    with fa:
        search  = st.text_input("🔍 Search name / email", placeholder="Type to filter…", key="dash_search")
    with fb:
        f_stage = st.selectbox("Filter Stage", ["All"] + _STAGES, key="dash_fstage")
    with fc:
        f_sort  = st.selectbox("Sort by", ["Name A–Z", "Score ↓", "Score ↑", "Stage"], key="dash_sort")

    rows = []
    for c in candidates:
        cid = c["candidate_id"]
        row = ats.get(cid, {})
        rows.append({**c, **row,
                     "stage":        st.session_state[_sk("tbl", cid)],
                     "resume_score": row.get("resume_score", 0.0)})

    if search:
        q = search.lower()
        rows = [r for r in rows if q in (r.get("name") or "").lower()
                or q in (r.get("email") or "").lower()]
    if f_stage != "All":
        rows = [r for r in rows if r["stage"] == f_stage]
    if f_sort == "Score ↓":
        rows = sorted(rows, key=lambda r: r["resume_score"], reverse=True)
    elif f_sort == "Score ↑":
        rows = sorted(rows, key=lambda r: r["resume_score"])
    elif f_sort == "Stage":
        rows = sorted(rows, key=lambda r: _STAGES.index(r["stage"]))
    else:
        rows = sorted(rows, key=lambda r: (r.get("name") or "").lower())

    st.caption(f"Showing {len(rows)} of {len(candidates)} candidates")
    st.divider()

    for rec in rows:
        cid   = rec["candidate_id"]
        score = rec["resume_score"]
        sc    = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
        name  = (rec.get("name") or "Unknown").splitlines()[0]

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 1, 2])
            with c1:
                job_title = jobs.get(rec.get("job_id", 0), "No Job Assigned")
                st.markdown(
                    f"<div style='font-size:0.92rem;font-weight:700;color:#f1f5f9'>{html.escape(name)}</div>"
                    f"<div style='font-size:0.7rem;color:#a78bfa;font-weight:600;margin-top:2px'>"
                    f"💼 {html.escape(job_title)}</div>"
                    f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:2px'>"
                    f"📧 {html.escape(rec.get('email') or '—')} &nbsp;·&nbsp; "
                    f"📞 {html.escape(rec.get('phone') or '—')}</div>"
                    f"<div style='font-size:0.68rem;color:#64748b;margin-top:2px'>"
                    f"👤 {html.escape(rec.get('recruiter') or '—')} &nbsp;·&nbsp; "
                    f"📅 {rec.get('interview_date') or '—'}</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(f"<div style='margin-top:6px'>{_badge(rec['stage'])}</div>", unsafe_allow_html=True)
                st.markdown(_score_bar(score), unsafe_allow_html=True)
            with c3:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px'>"
                    f"<div style='font-size:1.2rem;font-weight:900;color:{sc}'>{score:.0f}%</div>"
                    f"<div style='font-size:0.6rem;color:#64748b'>Score</div></div>",
                    unsafe_allow_html=True,
                )
            with c4:
                def _tbl_change(cid=cid):
                    _update_stage(cid, st.session_state[_sk("tbl", cid)])
                st.selectbox(
                    "Stage", _STAGES,
                    key=_sk("tbl", cid),
                    on_change=_tbl_change,
                    label_visibility="collapsed",
                )

            if rec.get("notes") or rec.get("feedback") or True:
                with st.expander("📝 Notes & Feedback / Recruiter Notes"):
                    if rec.get("notes"):
                        st.markdown(f"**Notes:** {rec['notes']}")
                    if rec.get("feedback"):
                        st.markdown(f"**Feedback:** {rec['feedback']}")
                    # ── Recruiter Notes ──────────────────────────────────
                    st.markdown("**🗒️ Recruiter Notes**")
                    rn_key  = _sk("rnotes", cid)
                    _seed(rn_key, rec.get("recruiter_notes") or "")
                    st.text_area(
                        "Recruiter Notes",
                        key=rn_key,
                        height=100,
                        placeholder="Add recruiter notes here…",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 Save Notes", key=_sk("rnsave", cid)):
                        _save_recruiter_notes(cid, st.session_state[rn_key])
                        st.success("✅ Notes saved")


# ══════════════════════════════════════════════════════════════════════════
#  TAB — EDIT
# ══════════════════════════════════════════════════════════════════════════

def _tab_edit(all_candidates: list[dict], ats: dict[int, dict], jobs: dict[int, str], all_jobs: list[dict]) -> None:
    """Add new candidates to pipeline or edit existing ones."""
    pipeline_ids = set(ats.keys())
    not_added    = [c for c in all_candidates if c["candidate_id"] not in pipeline_ids]

    # ── Add new candidate to pipeline ────────────────────────────────────
    if not_added:
        st.markdown("**➕ Add Candidate to Pipeline**")
        add_opts = {f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c for c in not_added}
        job_opts  = {f"#{j['job_id']} — {j['job_title']}": j for j in all_jobs}
        a1, a2, a3 = st.columns([3, 3, 1])
        with a1:
            add_sel = st.selectbox("Candidate", list(add_opts.keys()), key="add_cand_sel", label_visibility="collapsed")
        with a2:
            job_sel = st.selectbox("Job", list(job_opts.keys()), key="add_job_sel", label_visibility="collapsed")
        with a3:
            if st.button("➕ Add", type="primary", use_container_width=True, key="add_cand_btn"):
                cand_to_add    = add_opts[add_sel]
                job_to_add     = job_opts[job_sel]
                score          = _compute_score(cand_to_add, job_to_add)
                rec_email      = st.session_state.get("recruiter_email", "")
                _add_to_pipeline(cand_to_add["candidate_id"], job_to_add["job_id"], score, rec_email)
                st.success(f"✅ {cand_to_add.get('name','').splitlines()[0]} added — Score: {score}%")
                st.rerun()
        st.divider()

    # ── Edit existing pipeline candidates ────────────────────────────────
    pipeline_candidates = [c for c in all_candidates if c["candidate_id"] in pipeline_ids]
    if not pipeline_candidates:
        st.info("No candidates in pipeline yet. Add one above.")
        return

    opts = {f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]} ({jobs.get(ats.get(c['candidate_id'],{}).get('job_id',0),'No Job')})": c for c in pipeline_candidates}
    sel  = opts[st.selectbox("✏️ Edit candidate", list(opts.keys()), key="edit_sel")]
    cid  = sel["candidate_id"]
    row  = ats.get(cid, {})

    _seed(_sk("edit_stage", cid), row.get("stage", "Applied"))
    st.markdown(f"<div style='margin:10px 0 16px'>{_badge(st.session_state[_sk('edit_stage', cid)])}</div>", unsafe_allow_html=True)

    with st.container(border=True):
        e1, e2, e3 = st.columns(3)
        with e1:
            st.selectbox("📍 Stage", _STAGES, key=_sk("edit_stage", cid))
        with e2:
            recruiter = st.text_input("👤 Recruiter", value=row.get("recruiter") or "", key=_sk("edit_rec", cid))
        with e3:
            resume_score = st.number_input(
                "🎯 Resume Score", min_value=0.0, max_value=100.0,
                value=float(row.get("resume_score") or 0.0),
                step=0.5, format="%.1f", key=_sk("edit_score", cid),
            )

        # show assigned job
        assigned_job = jobs.get(row.get("job_id", 0), "No Job Assigned")
        st.markdown(
            f"<div style='font-size:0.78rem;color:#a78bfa;font-weight:600;margin-bottom:8px'>"
            f"💼 Applied for: {html.escape(assigned_job)}</div>",
            unsafe_allow_html=True,
        )

        e4, e5 = st.columns(2)
        with e4:
            idate_str = row.get("interview_date") or ""
            try:
                idate_default = date.fromisoformat(idate_str) if idate_str else None
            except ValueError:
                idate_default = None
            interview_date = st.date_input("📅 Interview Date", value=idate_default, key=_sk("edit_idate", cid))
        with e5:
            st.markdown(
                f"<div style='padding-top:8px;font-size:0.78rem;color:#94a3b8'>"
                f"📧 {html.escape(sel.get('email') or '—')}<br>"
                f"📞 {html.escape(sel.get('phone') or '—')}</div>",
                unsafe_allow_html=True,
            )

        n1, n2 = st.columns(2)
        with n1:
            notes    = st.text_area("📝 Notes",    value=row.get("notes") or "",    height=120, key=_sk("edit_notes", cid))
        with n2:
            feedback = st.text_area("💬 Feedback", value=row.get("feedback") or "", height=120, key=_sk("edit_fb", cid))

        st.markdown(_score_bar(resume_score), unsafe_allow_html=True)

        if st.button("💾 Save to ATS", type="primary", use_container_width=True, key=_sk("edit_save", cid)):
            chosen_stage = st.session_state[_sk("edit_stage", cid)]
            _save_full(cid, chosen_stage, recruiter, resume_score,
                       str(interview_date) if interview_date else "", notes, feedback, row.get("job_id", 0))
            st.session_state[_sk("kb",  cid)] = chosen_stage
            st.session_state[_sk("tbl", cid)] = chosen_stage
            st.success(f"✅ {(sel.get('name') or 'Candidate').splitlines()[0]} saved — stage: **{chosen_stage}**")


# ══════════════════════════════════════════════════════════════════════════
#  TAB — STATS
# ══════════════════════════════════════════════════════════════════════════

def _tab_stats(candidates: list[dict], ats: dict[int, dict]) -> None:
    total = len(candidates)
    if not total:
        st.info("No candidates yet.")
        return

    stage_counts = {s: 0 for s in _STAGES}
    scores = []
    for c in candidates:
        cid = c["candidate_id"]
        row = ats.get(cid, {})
        stage_counts[row.get("stage", "Applied")] += 1
        scores.append(row.get("resume_score") or 0.0)

    avg      = round(sum(scores) / total, 1) if scores else 0.0
    selected = stage_counts["Selected"]
    rejected = stage_counts["Rejected"]
    active   = total - selected - rejected

    m1, m2, m3, m4, m5 = st.columns(5)
    _metric(m1, "Total",     total,        "#3b82f6")
    _metric(m2, "Active",    active,       "#8b5cf6")
    _metric(m3, "Selected",  selected,     "#10b981")
    _metric(m4, "Rejected",  rejected,     "#ef4444")
    _metric(m5, "Avg Score", f"{avg}%",    "#f59e0b")

    st.divider()
    st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:14px'>📊 Stage Breakdown</div>", unsafe_allow_html=True)
    for stage in _STAGES:
        count = stage_counts[stage]
        pct   = round(count / total * 100) if total else 0
        cfg   = _STAGE_CFG[stage]
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;"
            f"padding:10px 16px;background:rgba(255,255,255,0.03);"
            f"border-radius:12px;border:1px solid rgba(255,255,255,0.06)'>"
            f"<div style='min-width:120px;font-size:0.8rem;font-weight:600;color:#f1f5f9'>{cfg['icon']} {stage}</div>"
            f"<div style='flex:1;background:rgba(255,255,255,0.08);border-radius:20px;height:8px;overflow:hidden'>"
            f"<div style='background:{cfg['color']};height:100%;width:{pct}%;border-radius:20px'></div></div>"
            f"<div style='min-width:70px;text-align:right;font-size:0.8rem;font-weight:700;color:{cfg['color']}'>{count} ({pct}%)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:14px'>🏆 Top 5 by Resume Score</div>", unsafe_allow_html=True)
    for i, c in enumerate(sorted(candidates, key=lambda c: ats.get(c["candidate_id"], {}).get("resume_score") or 0.0, reverse=True)[:5], 1):
        cid   = c["candidate_id"]
        row   = ats.get(cid, {})
        score = row.get("resume_score") or 0.0
        sc    = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
        name  = (c.get("name") or "Unknown").splitlines()[0]
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:14px;padding:10px 16px;"
            f"background:rgba(255,255,255,0.03);border-radius:12px;margin-bottom:6px;"
            f"border:1px solid rgba(255,255,255,0.06)'>"
            f"<span style='font-size:0.8rem;font-weight:800;color:#64748b;min-width:22px'>#{i}</span>"
            f"<span style='font-size:0.88rem;font-weight:600;color:#f1f5f9;flex:1'>{html.escape(name)}</span>"
            f"{_badge(row.get('stage', 'Applied'))}"
            f"<span style='font-size:0.88rem;font-weight:800;color:{sc};min-width:48px;text-align:right'>{score:.1f}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header("🗂️ ATS Dashboard", "Applied → Screening → Interview → Selected → Rejected · MySQL backed")

    _init_db()

    rec_email  = st.session_state.get("recruiter_email", "")
    candidates = service.get_all_candidates(rec_email)
    if not candidates:
        st.info("No candidates found. Upload resumes first.")
        return

    all_jobs = service.jobs.get_all_jobs(rec_email)
    jobs     = {j["job_id"]: j["job_title"] for j in all_jobs}

    # Auto-backfill zero-score rows once per session
    if "ats_backfill_done" not in st.session_state:
        _backfill_scores(candidates, {j["job_id"]: j for j in all_jobs}, rec_email)
        st.session_state["ats_backfill_done"] = True
    ats                 = _load_all(rec_email)  # reload after backfill
    pipeline_candidates = [c for c in candidates if c["candidate_id"] in ats]

    # ── Top 4 metric cards ────────────────────────────────────────────────
    total_pipeline  = len(pipeline_candidates)
    interview_count = sum(1 for r in ats.values() if r.get("stage") == "Interview")
    selected_count  = sum(1 for r in ats.values() if r.get("stage") == "Selected")
    rejected_count  = sum(1 for r in ats.values() if r.get("stage") == "Rejected")

    mc1, mc2, mc3, mc4 = st.columns(4)
    _metric(mc1, "Total Candidates",      total_pipeline,  "#3b82f6")
    _metric(mc2, "Interview Scheduled",   interview_count, "#f59e0b")
    _metric(mc3, "Selected",              selected_count,  "#10b981")
    _metric(mc4, "Rejected",              rejected_count,  "#ef4444")
    st.divider()

    tab_kanban, tab_table, tab_edit, tab_stats = st.tabs([
        "📋 Kanban Board", "📊 Pipeline Table", "✏️ Edit / Add", "📈 Stats",
    ])

    with tab_kanban:
        if not pipeline_candidates:
            st.info("No candidates in pipeline yet. Go to **Edit / Add** tab to add candidates.")
        else:
            _tab_kanban(pipeline_candidates, ats, jobs)
    with tab_table:
        if not pipeline_candidates:
            st.info("No candidates in pipeline yet. Go to **Edit / Add** tab to add candidates.")
        else:
            _tab_table(pipeline_candidates, ats, jobs)
    with tab_edit:
        _tab_edit(candidates, ats, jobs, all_jobs)
    with tab_stats:
        _tab_stats(pipeline_candidates, ats)
