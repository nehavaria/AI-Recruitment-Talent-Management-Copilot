"""
Milestone 4 — Recruitment Analytics
All data sourced from existing MySQL tables:
  - ats_candidates  : stage, resume_score, job_id
  - jobs            : job_title  (JOIN on job_id)
  - interview_sessions : avg_score, verdict, candidate_name
No new tables are created.
"""

import html
import json
import logging
from contextlib import contextmanager
from typing import Generator

import mysql.connector
import plotly.graph_objects as go
import streamlit as st

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_CFG = dict(
    host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
    user=MYSQL_USER, password=MYSQL_PASSWORD,
    autocommit=False, charset="utf8mb4",
)

_STAGE_COLORS = {
    "Applied":   "#3b82f6",
    "Screening": "#8b5cf6",
    "Interview": "#f59e0b",
    "Selected":  "#10b981",
    "Rejected":  "#ef4444",
}

_CHART_BG   = "rgba(0,0,0,0)"
_PAPER_BG   = "rgba(0,0,0,0)"
_FONT_COLOR = "#e2e8f0"
_GRID_COLOR = "rgba(255,255,255,0.08)"


@contextmanager
def _db() -> Generator[mysql.connector.MySQLConnection, None, None]:
    conn = mysql.connector.connect(**_CFG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _base_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=_FONT_COLOR, size=14, family="Inter")),
        paper_bgcolor=_PAPER_BG,
        plot_bgcolor=_CHART_BG,
        font=dict(color=_FONT_COLOR, family="Inter"),
        margin=dict(l=40, r=20, t=50, b=40),
    )


# ── SQL queries ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def _q_stage_distribution(recruiter_email: str) -> list[dict]:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT COALESCE(stage, 'Unknown') AS stage, COUNT(*) AS cnt
                FROM ats_pipeline
                WHERE recruiter_email = %s OR %s = ''
                GROUP BY stage
                ORDER BY FIELD(stage,'Applied','Screening','Interview','Selected','Rejected')
            """, (recruiter_email, recruiter_email))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("stage_distribution query failed: %s", exc)
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _q_score_buckets(recruiter_email: str) -> list[dict]:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    CASE
                        WHEN resume_score < 20 THEN '0–19'
                        WHEN resume_score < 40 THEN '20–39'
                        WHEN resume_score < 60 THEN '40–59'
                        WHEN resume_score < 80 THEN '60–79'
                        ELSE '80–100'
                    END AS bucket,
                    COUNT(*) AS cnt
                FROM ats_pipeline
                WHERE (recruiter_email = %s OR %s = '') AND resume_score IS NOT NULL
                GROUP BY bucket
                ORDER BY MIN(resume_score)
            """, (recruiter_email, recruiter_email))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("score_buckets query failed: %s", exc)
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _q_skill_match_buckets(recruiter_email: str) -> list[dict]:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    CASE
                        WHEN resume_score < 25 THEN 'Low (<25%)'
                        WHEN resume_score < 50 THEN 'Moderate (25–49%)'
                        WHEN resume_score < 75 THEN 'Good (50–74%)'
                        ELSE 'Excellent (75–100%)'
                    END AS match_band,
                    COUNT(*) AS cnt
                FROM ats_pipeline
                WHERE (recruiter_email = %s OR %s = '') AND resume_score IS NOT NULL
                GROUP BY match_band
                ORDER BY MIN(resume_score)
            """, (recruiter_email, recruiter_email))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("skill_match_buckets query failed: %s", exc)
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _q_candidates_by_job(recruiter_email: str) -> list[dict]:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT COALESCE(j.job_title, 'Unassigned') AS job_title, COUNT(*) AS cnt
                FROM ats_pipeline p
                LEFT JOIN jobs j ON j.job_id = p.job_id
                WHERE p.recruiter_email = %s OR %s = ''
                GROUP BY j.job_title
                ORDER BY cnt DESC
                LIMIT 15
            """, (recruiter_email, recruiter_email))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("candidates_by_job query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _q_interview_performance(recruiter_email: str) -> list[dict]:
    """Chart 5 — interview_sessions.avg_score, verdict (GROUP BY verdict, AVG score)."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COALESCE(verdict, 'Pending') AS verdict,
                    COUNT(*)                     AS cnt,
                    ROUND(AVG(avg_score), 1)     AS avg_score
                FROM interview_sessions
                GROUP BY verdict
                ORDER BY avg_score DESC
            """)
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("interview_performance query failed: %s", exc)
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _q_selected_vs_rejected(recruiter_email: str) -> dict:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    SUM(stage = 'Selected') AS selected,
                    SUM(stage = 'Rejected') AS rejected,
                    SUM(stage NOT IN ('Selected','Rejected')) AS active
                FROM ats_pipeline
                WHERE recruiter_email = %s OR %s = ''
            """, (recruiter_email, recruiter_email))
            row = cur.fetchone() or {}
            cur.close()
        return {
            "selected": int(row.get("selected") or 0),
            "rejected": int(row.get("rejected") or 0),
            "active":   int(row.get("active")   or 0),
        }
    except Exception as exc:
        logger.warning("selected_vs_rejected query failed: %s", exc)
        return {"selected": 0, "rejected": 0, "active": 0}


# ── Chart builders ─────────────────────────────────────────────────────────

def _chart_stage_distribution(rows: list[dict]) -> go.Figure:
    stages = [r["stage"] for r in rows]
    counts = [r["cnt"]   for r in rows]
    colors = [_STAGE_COLORS.get(s, "#94a3b8") for s in stages]

    fig = go.Figure(go.Pie(
        labels=stages, values=counts,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.3)", width=1)),
        textinfo="label+percent",
        textfont=dict(color=_FONT_COLOR, size=12),
        hole=0.45,
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("Candidate Distribution by Status"),
        legend=dict(font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_score_distribution(rows: list[dict]) -> go.Figure:
    buckets = [r["bucket"] for r in rows]
    counts  = [r["cnt"]    for r in rows]
    colors  = ["#ef4444", "#f97316", "#f59e0b", "#34d399", "#10b981"][:len(buckets)]

    fig = go.Figure(go.Bar(
        x=buckets, y=counts,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.2)", width=1)),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR),
        hovertemplate="<b>Score %{x}</b><br>Candidates: %{y}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("Hiring Score Distribution"),
        xaxis=dict(title="Score Range (%)", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(title="Candidates",      gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        bargap=0.3,
    )
    return fig


def _chart_skill_match(rows: list[dict]) -> go.Figure:
    bands  = [r["match_band"] for r in rows]
    counts = [r["cnt"]        for r in rows]
    colors = ["#ef4444", "#f59e0b", "#3b82f6", "#10b981"][:len(bands)]

    fig = go.Figure(go.Bar(
        x=counts, y=bands,
        orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.2)", width=1)),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR),
        hovertemplate="<b>%{y}</b><br>Candidates: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("Skill Match Distribution"),
        xaxis=dict(title="Candidates", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR),
    )
    return fig


def _chart_by_job(rows: list[dict]) -> go.Figure:
    titles = [r["job_title"] for r in rows]
    counts = [r["cnt"]       for r in rows]

    fig = go.Figure(go.Bar(
        x=counts, y=titles,
        orientation="h",
        marker=dict(
            color=counts,
            colorscale=[[0, "#3b82f6"], [0.5, "#8b5cf6"], [1, "#ec4899"]],
            showscale=False,
            line=dict(color="rgba(0,0,0,0.2)", width=1),
        ),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR),
        hovertemplate="<b>%{y}</b><br>Candidates: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("Candidates by Job Role"),
        xaxis=dict(title="Candidates", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, automargin=True),
        height=max(300, len(titles) * 38 + 80),
    )
    return fig


def _chart_interview_performance(rows: list[dict]) -> go.Figure:
    verdicts   = [r["verdict"]   for r in rows]
    avg_scores = [float(r["avg_score"] or 0) for r in rows]
    counts     = [r["cnt"]       for r in rows]

    verdict_colors = {
        "Highly Recommended": "#10b981",
        "Good Match":         "#34d399",
        "Partial Match":      "#f59e0b",
        "Not Recommended":    "#ef4444",
        "Pending":            "#94a3b8",
    }
    colors = [verdict_colors.get(v, "#8b5cf6") for v in verdicts]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Avg Interview Score",
        x=verdicts, y=avg_scores,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.2)", width=1)),
        text=[f"{s}%" for s in avg_scores],
        textposition="outside",
        textfont=dict(color=_FONT_COLOR),
        hovertemplate="<b>%{x}</b><br>Avg Score: %{y}%<extra></extra>",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        name="Candidate Count",
        x=verdicts, y=counts,
        mode="markers+text",
        marker=dict(size=12, color="#f59e0b", symbol="circle"),
        text=counts,
        textposition="top center",
        textfont=dict(color=_FONT_COLOR, size=11),
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
        yaxis="y2",
    ))
    fig.update_layout(
        **_base_layout("Interview Performance by Verdict"),
        xaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(title="Avg Score (%)", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis2=dict(title="Count", overlaying="y", side="right", color=_FONT_COLOR),
        bargap=0.35,
        legend=dict(orientation="h", y=-0.2, font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_selected_vs_rejected(data: dict) -> go.Figure:
    labels = ["Selected", "Rejected", "Active"]
    values = [data["selected"], data["rejected"], data["active"]]
    colors = ["#10b981", "#ef4444", "#3b82f6"]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.3)", width=2)),
        textinfo="label+value+percent",
        textfont=dict(color=_FONT_COLOR, size=12),
        hole=0.5,
        pull=[0.05, 0.05, 0],
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("Selected vs Rejected vs Active"),
        legend=dict(font=dict(color=_FONT_COLOR)),
    )
    return fig


# ── Summary metrics ────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def _load_summary(recruiter_email: str) -> dict:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COUNT(*)                        AS total,
                    ROUND(AVG(resume_score), 1)     AS avg_score,
                    SUM(stage = 'Selected')         AS selected,
                    SUM(stage = 'Rejected')         AS rejected,
                    SUM(stage = 'Interview')        AS interviews
                FROM ats_pipeline
                WHERE recruiter_email = %s OR %s = ''
            """, (recruiter_email, recruiter_email))
            row = cur.fetchone() or {}
            cur.execute("SELECT COUNT(*) AS cnt FROM interview_sessions")
            isrow = cur.fetchone() or {}
            cur.close()
        return {
            "total":      int(row.get("total")      or 0),
            "avg_score":  float(row.get("avg_score") or 0),
            "selected":   int(row.get("selected")   or 0),
            "rejected":   int(row.get("rejected")   or 0),
            "interviews": int(row.get("interviews") or 0),
            "sessions":   int(isrow.get("cnt")      or 0),
        }
    except Exception as exc:
        logger.warning("summary query failed: %s", exc)
        return {"total": 0, "avg_score": 0.0, "selected": 0,
                "rejected": 0, "interviews": 0, "sessions": 0}


# ══════════════════════════════════════════════
#  CANDIDATE MANAGEMENT — queries
# ══════════════════════════════════════════════

_STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

_STAGE_CFG = {
    "Applied":   {"color": "#3b82f6", "bg": "rgba(59,130,246,0.12)",  "border": "rgba(59,130,246,0.35)",  "icon": "📥"},
    "Screening": {"color": "#8b5cf6", "bg": "rgba(139,92,246,0.12)",  "border": "rgba(139,92,246,0.35)",  "icon": "🔍"},
    "Interview": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.12)",  "border": "rgba(245,158,11,0.35)",  "icon": "🎤"},
    "Selected":  {"color": "#10b981", "bg": "rgba(16,185,129,0.12)",  "border": "rgba(16,185,129,0.35)",  "icon": "✅"},
    "Rejected":  {"color": "#ef4444", "bg": "rgba(239,68,68,0.12)",   "border": "rgba(239,68,68,0.35)",   "icon": "❌"},
}


@st.cache_data(ttl=60, show_spinner=False)
def _load_jobs_for_filter(recruiter_email: str) -> list[dict]:
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT DISTINCT j.job_id, j.job_title FROM jobs j "
                "INNER JOIN ats_pipeline p ON p.job_id = j.job_id "
                "WHERE p.recruiter_email = %s OR %s = '' ORDER BY j.job_title",
                (recruiter_email, recruiter_email),
            )
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception:
        return []


def _load_candidates_managed(
    recruiter_email: str,
    search: str,
    stage: str,
    job_id: int | None,
    score_min: float,
    score_max: float,
    sort: str,
) -> list[dict]:
    """
    JOIN ats_pipeline + candidates + jobs + latest interview_session.
    All filtering and ordering in SQL. Fully parameterized.
    """
    where = ["(p.recruiter_email = %s OR %s = '')"]
    params: list = [recruiter_email, recruiter_email]

    if search:
        where.append("(c.name LIKE %s OR c.email LIKE %s OR c.skills LIKE %s)")
        like = f"%{search}%"
        params += [like, like, like]
    if stage and stage != "All":
        where.append("p.stage = %s")
        params.append(stage)
    if job_id:
        where.append("p.job_id = %s")
        params.append(job_id)

    where.append("p.resume_score BETWEEN %s AND %s")
    params += [score_min, score_max]

    order_map = {
        "Hiring Score ↓":  "p.resume_score DESC",
        "Hiring Score ↑":  "p.resume_score ASC",
        "Newest First":    "c.created_date DESC",
        "Oldest First":    "c.created_date ASC",
        "Name A–Z":        "c.name ASC",
    }
    order = order_map.get(sort, "p.resume_score DESC")

    sql = f"""
        SELECT
            c.candidate_id,
            c.name,
            c.email,
            c.phone,
            c.skills,
            c.education,
            c.experience,
            c.certifications,
            c.projects,
            c.created_date,
            p.stage,
            p.resume_score,
            p.interview_date,
            p.notes,
            p.recruiter_notes,
            COALESCE(j.job_title, 'Unassigned') AS job_title,
            p.job_id,
            isess.avg_score   AS interview_score,
            isess.verdict     AS interview_verdict,
            isess.report_json AS report_json
        FROM ats_pipeline p
        INNER JOIN candidates c ON c.candidate_id = p.candidate_id
        LEFT JOIN  jobs j       ON j.job_id = p.job_id
        LEFT JOIN  interview_sessions isess
               ON isess.session_id = (
                   SELECT session_id FROM interview_sessions
                   WHERE candidate_id = c.candidate_id
                   ORDER BY created_at DESC LIMIT 1
               )
        WHERE {' AND '.join(where)}
        ORDER BY {order}
    """
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("load_candidates_managed failed: %s", exc)
        return []


def _update_stage_pipeline(candidate_id: int, recruiter_email: str, new_stage: str) -> None:
    """UPDATE ats_pipeline.stage for the existing row — never inserts."""
    if new_stage not in _STAGES:
        return
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ats_pipeline SET stage = %s "
            "WHERE candidate_id = %s AND recruiter_email = %s",
            (new_stage, candidate_id, recruiter_email),
        )
        cur.close()


# ── UI helpers ─────────────────────────────────────────────────────────────

def _badge(stage: str) -> str:
    cfg = _STAGE_CFG.get(stage, {"color": "#94a3b8", "bg": "rgba(148,163,184,0.1)",
                                  "border": "rgba(148,163,184,0.3)", "icon": ""})
    return (
        f"<span style='background:{cfg['bg']};color:{cfg['color']};"
        f"border:1px solid {cfg['border']};padding:3px 12px;"
        f"border-radius:20px;font-size:0.72rem;font-weight:700'>"
        f"{cfg['icon']} {html.escape(stage)}</span>"
    )


def _score_pill(score: float) -> str:
    c = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    return (
        f"<span style='background:{c}18;color:{c};border:1px solid {c}40;"
        f"padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:800'>{score:.1f}%</span>"
    )


def _hiring_score(resume: float, interview) -> float:
    iv = float(interview) if interview is not None else None
    return round(resume * 0.6 + iv * 0.4, 1) if iv is not None else round(resume, 1)


def _show_profile(rec: dict) -> None:
    rs = float(rec.get("resume_score") or 0)
    iv = rec.get("interview_score")
    hs = _hiring_score(rs, iv)
    name = (rec.get("name") or "Unknown").splitlines()[0]
    ini  = "".join(w[0].upper() for w in name.split()[:2]) or "?"

    st.markdown(
        f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.12),rgba(37,99,235,0.08));"
        f"border-radius:16px;padding:18px;border:1px solid rgba(124,58,237,0.25);margin-bottom:14px'>"
        f"<div style='display:flex;align-items:center;gap:14px'>"
        f"<div style='width:48px;height:48px;border-radius:12px;flex-shrink:0;"
        f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
        f"display:flex;align-items:center;justify-content:center;"
        f"color:#fff;font-weight:900;font-size:1.1rem'>{html.escape(ini)}</div>"
        f"<div style='flex:1'>"
        f"<div style='font-size:1rem;font-weight:800;color:#f1f5f9'>{html.escape(name)}</div>"
        f"<div style='font-size:0.73rem;color:#94a3b8;margin-top:2px'>"
        f"✉ {html.escape(rec.get('email') or '—')} &nbsp;·&nbsp; "
        f"📞 {html.escape(rec.get('phone') or '—')}</div>"
        f"</div>"
        f"<div>{_badge(rec.get('stage','Applied'))}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("🎯 Resume Score",    f"{rs:.1f}%")
    p2.metric("🎤 Interview Score", f"{float(iv):.1f}%" if iv is not None else "N/A")
    p3.metric("🏆 Hiring Score",    f"{hs}%")
    p4.metric("💼 Job Role",        rec.get("job_title") or "—")

    st.markdown("<br>", unsafe_allow_html=True)
    cl, cr = st.columns(2)
    with cl:
        st.markdown("**🎓 Education**")
        st.caption(rec.get("education") or "—")
        st.markdown("**🛠 Skills**")
        skills = [s.strip() for s in (rec.get("skills") or "").split(",") if s.strip()]
        if skills:
            badges = "".join(
                f"<span style='background:rgba(139,92,246,0.15);color:#c4b5fd;"
                f"border:1px solid rgba(139,92,246,0.35);padding:3px 10px;"
                f"border-radius:20px;font-size:0.72rem;font-weight:600;"
                f"margin:2px;display:inline-block'>{html.escape(s)}</span>"
                for s in skills
            )
            st.markdown(f"<div style='line-height:2.2'>{badges}</div>", unsafe_allow_html=True)
        else:
            st.caption("—")
    with cr:
        st.markdown("**💼 Experience**")
        st.caption(rec.get("experience") or "—")
        st.markdown("**🏅 Certifications**")
        st.caption(rec.get("certifications") or "—")
        if rec.get("projects"):
            st.markdown("**🗂 Projects**")
            st.caption(rec["projects"])


def _show_report(rec: dict) -> None:
    raw = rec.get("report_json")
    if not raw:
        st.info("No interview report yet. Run the AI Interview Simulator first.")
        return
    try:
        report = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        st.info("Could not parse interview report.")
        return

    avg     = report.get("avg_score", 0)
    verdict = report.get("verdict", "")
    answers = report.get("answers", [])
    clr     = "#10b981" if avg >= 70 else "#f59e0b" if avg >= 40 else "#ef4444"

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:16px;"
        f"padding:20px;border:1px solid {clr}40;text-align:center;margin-bottom:14px'>"
        f"<div style='font-size:2.8rem;font-weight:900;color:{clr}'>{avg}%</div>"
        f"<div style='font-size:0.9rem;font-weight:700;color:{clr};margin-top:4px'>"
        f"{html.escape(str(verdict))}</div></div>",
        unsafe_allow_html=True,
    )
    for ans in answers:
        ev = ans.get("evaluation", {})
        sc = ev.get("score", 0)
        c2 = "#10b981" if sc >= 70 else "#f59e0b" if sc >= 40 else "#ef4444"
        q  = str(ans.get("question", ""))[:90]
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:8px 12px;"
            f"background:rgba(255,255,255,0.03);border-radius:10px;"
            f"border:1px solid rgba(255,255,255,0.06);margin-bottom:4px'>"
            f"<span style='font-size:0.72rem;font-weight:800;color:{c2};"
            f"background:{c2}18;padding:2px 8px;border-radius:8px;min-width:36px;text-align:center'>"
            f"{sc}%</span>"
            f"<div style='font-size:0.82rem;color:#f1f5f9'>{html.escape(q)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════
#  CANDIDATE MANAGEMENT TAB
# ══════════════════════════════════════════════

def _tab_candidate_management(recruiter_email: str) -> None:
    # ── Filters ────────────────────────────────────────────────────────────
    jobs = _load_jobs_for_filter(recruiter_email)
    job_options = {"All Jobs": None} | {j["job_title"]: j["job_id"] for j in jobs}

    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        search = st.text_input("🔍 Search name / email / skill",
                               placeholder="Type to filter…", key="cm_search")
    with f2:
        stage_sel = st.selectbox("📍 Status", ["All"] + _STAGES, key="cm_stage")
    with f3:
        job_sel = st.selectbox("💼 Job Role", list(job_options.keys()), key="cm_job")

    f4, f5, f6 = st.columns([2, 2, 2])
    with f4:
        score_min = st.number_input("Score min (%)", 0.0, 100.0, 0.0, 5.0, key="cm_smin")
    with f5:
        score_max = st.number_input("Score max (%)", 0.0, 100.0, 100.0, 5.0, key="cm_smax")
    with f6:
        sort_sel = st.selectbox("↕ Sort by",
                                ["Hiring Score ↓", "Hiring Score ↑",
                                 "Newest First", "Oldest First", "Name A–Z"],
                                key="cm_sort")

    selected_job_id = job_options.get(job_sel)
    stage_filter    = stage_sel if stage_sel != "All" else ""

    rows = _load_candidates_managed(
        recruiter_email, search, stage_filter,
        selected_job_id, score_min, score_max, sort_sel,
    )

    st.caption(f"Showing {len(rows)} candidate(s)")
    st.divider()

    if not rows:
        st.info("No candidates match the current filters.")
        return

    # ── Candidate rows ──────────────────────────────────────────────────────
    for rec in rows:
        cid   = rec["candidate_id"]
        stage = rec.get("stage") or "Applied"
        rs    = float(rec.get("resume_score") or 0)
        hs    = _hiring_score(rs, rec.get("interview_score"))
        name  = (rec.get("name") or "Unknown").splitlines()[0]

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 2])

            with c1:
                st.markdown(
                    f"<div style='font-size:0.92rem;font-weight:700;color:#f1f5f9'>"
                    f"{html.escape(name)}</div>"
                    f"<div style='font-size:0.7rem;color:#a78bfa;font-weight:600;margin-top:2px'>"
                    f"💼 {html.escape(rec.get('job_title') or '—')}</div>"
                    f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:2px'>"
                    f"✉ {html.escape(rec.get('email') or '—')} &nbsp;·&nbsp; "
                    f"📞 {html.escape(rec.get('phone') or '—')}</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"<div style='margin-top:6px'>{_badge(stage)}</div>"
                    f"<div style='font-size:0.68rem;color:#64748b;margin-top:4px'>"
                    f"📅 {rec.get('interview_date') or '—'}</div>",
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    f"<div style='text-align:center;padding-top:4px'>"
                    f"<div style='font-size:0.6rem;color:#64748b;font-weight:700;"
                    f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px'>Resume</div>"
                    f"{_score_pill(rs)}</div>",
                    unsafe_allow_html=True,
                )
            with c4:
                st.markdown(
                    f"<div style='text-align:center;padding-top:4px'>"
                    f"<div style='font-size:0.6rem;color:#64748b;font-weight:700;"
                    f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px'>Hiring</div>"
                    f"{_score_pill(hs)}</div>",
                    unsafe_allow_html=True,
                )
            with c5:
                # Status update — UPDATE existing row only, no INSERT
                new_stage = st.selectbox(
                    "Stage", _STAGES,
                    index=_STAGES.index(stage) if stage in _STAGES else 0,
                    key=f"cm_stage_sel_{cid}",
                    label_visibility="collapsed",
                )
                if new_stage != stage:
                    try:
                        _update_stage_pipeline(cid, recruiter_email, new_stage)
                        _load_summary.clear()
                        _q_stage_distribution.clear()
                        _q_selected_vs_rejected.clear()
                        _q_score_buckets.clear()
                        _q_skill_match_buckets.clear()
                        _q_candidates_by_job.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

            with st.expander("👤 Profile  |  📄 Interview Report"):
                tab_p, tab_r = st.tabs(["👤 Full Profile", "📄 Interview Report"])
                with tab_p:
                    _show_profile(rec)
                with tab_r:
                    _show_report(rec)


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header(
        "📊 Recruitment Analytics",
        "Visual insights across pipeline stages, scores, roles and interview performance.",
    )

    recruiter_email = st.session_state.get("recruiter_email", "")
    tab_analytics, tab_manage = st.tabs(["📈 Analytics", "👥 Candidate Management"])

    with tab_manage:
        _tab_candidate_management(recruiter_email)

    with tab_analytics:
        try:
            summary = _load_summary(recruiter_email)
        except Exception as exc:
            st.error(f"Database connection failed: {exc}")
            return

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        for col, icon, label, val, color in [
            (k1, "🗂️", "Pipeline Total",   summary["total"],           "#3b82f6"),
            (k2, "🎯", "Avg Hiring Score", f"{summary['avg_score']}%", "#8b5cf6"),
            (k3, "✅", "Selected",         summary["selected"],        "#10b981"),
            (k4, "❌", "Rejected",         summary["rejected"],        "#ef4444"),
            (k5, "🎤", "In Interview",     summary["interviews"],      "#f59e0b"),
            (k6, "🤖", "AI Sessions",      summary["sessions"],        "#ec4899"),
        ]:
            col.markdown(
                f"<div style='background:rgba(255,255,255,0.05);border-radius:16px;"
                f"padding:16px 10px;border:1px solid {color}30;text-align:center'>"
                f"<div style='font-size:1.2rem'>{icon}</div>"
                f"<div style='font-size:0.62rem;font-weight:700;color:#94a3b8;"
                f"text-transform:uppercase;letter-spacing:0.06em;margin:4px 0 2px'>{label}</div>"
                f"<div style='font-size:1.6rem;font-weight:900;color:{color};line-height:1'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        if summary["total"] == 0 and summary["sessions"] == 0:
            st.info(
                "No pipeline data found. Add candidates via **ATS Dashboard → Add / Edit** "
                "and run the **AI Interview Simulator** to populate analytics."
            )
            return

        col1, col2 = st.columns(2)
        with col1:
            rows = _q_stage_distribution(recruiter_email)
            if rows:
                st.plotly_chart(_chart_stage_distribution(rows),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No stage data available yet.")
        with col2:
            rows = _q_score_buckets(recruiter_email)
            if rows:
                st.plotly_chart(_chart_score_distribution(rows),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No hiring score data available yet.")

        col3, col4 = st.columns(2)
        with col3:
            rows = _q_skill_match_buckets(recruiter_email)
            if rows:
                st.plotly_chart(_chart_skill_match(rows),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No skill match data available yet.")
        with col4:
            rows = _q_candidates_by_job(recruiter_email)
            if rows:
                st.plotly_chart(_chart_by_job(rows),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No job role data available yet.")

        col5, col6 = st.columns(2)
        with col5:
            rows = _q_interview_performance(recruiter_email)
            if rows:
                st.plotly_chart(_chart_interview_performance(rows),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No interview session data yet. Run the AI Interview Simulator first.")
        with col6:
            data = _q_selected_vs_rejected(recruiter_email)
            if data["selected"] + data["rejected"] + data["active"] > 0:
                st.plotly_chart(_chart_selected_vs_rejected(data),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No pipeline data available yet.")
