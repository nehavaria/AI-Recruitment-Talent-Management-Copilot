"""Recruiter Dashboard — KPI cards + visual analytics (skills, skill gaps, pipeline)."""

import logging
from collections import Counter
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

_CHART_BG   = "rgba(0,0,0,0)"
_FONT_COLOR = "#e2e8f0"
_GRID_COLOR = "rgba(255,255,255,0.08)"

_STAGE_COLORS = {
    "Applied":   "#3b82f6",
    "Screening": "#8b5cf6",
    "Interview": "#f59e0b",
    "Selected":  "#10b981",
    "Rejected":  "#ef4444",
}


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


def _base_layout(title: str, height: int = 360) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=_FONT_COLOR, size=14, family="Inter")),
        paper_bgcolor=_CHART_BG,
        plot_bgcolor=_CHART_BG,
        font=dict(color=_FONT_COLOR, family="Inter"),
        height=height,
    )


# ══════════════════════════════════════════════
#  DATA QUERIES
# ══════════════════════════════════════════════

@st.cache_data(ttl=60, show_spinner=False)
def _load_kpis(recruiter_email: str) -> dict:
    kpis = dict(total_candidates=0, total_jobs=0, shortlisted=0,
                interviews=0, selected=0, rejected=0,
                avg_hiring_score=0.0, pipeline_total=0)
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS cnt FROM candidates WHERE recruiter_email = %s", (recruiter_email,))
            kpis["total_candidates"] = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'Open' AND recruiter_email = %s", (recruiter_email,))
            kpis["total_jobs"] = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("""
                SELECT COUNT(*) AS total,
                       SUM(stage='Screening') AS shortlisted,
                       SUM(stage='Interview') AS interviews,
                       SUM(stage='Selected')  AS selected,
                       SUM(stage='Rejected')  AS rejected,
                       ROUND(AVG(resume_score),1) AS avg_score
                FROM ats_pipeline WHERE recruiter_email = %s
            """, (recruiter_email,))
            row = cur.fetchone() or {}
            kpis["pipeline_total"]   = int(row.get("total") or 0)
            kpis["shortlisted"]      = int(row.get("shortlisted") or 0)
            kpis["interviews"]       = int(row.get("interviews") or 0)
            kpis["selected"]         = int(row.get("selected") or 0)
            kpis["rejected"]         = int(row.get("rejected") or 0)
            kpis["avg_hiring_score"] = float(row.get("avg_score") or 0.0)
            cur.close()
    except Exception as exc:
        logger.warning("KPI query failed: %s", exc)
    return kpis


@st.cache_data(ttl=60, show_spinner=False)
def _load_candidate_skills(recruiter_email: str) -> Counter:
    """Return Counter of individual skills across all candidates."""
    counter: Counter = Counter()
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT skills FROM candidates WHERE recruiter_email = %s AND skills IS NOT NULL",
                (recruiter_email,),
            )
            for (skills_str,) in cur.fetchall():
                for s in skills_str.split(","):
                    s = s.strip().lower()
                    if s:
                        counter[s] += 1
            cur.close()
    except Exception as exc:
        logger.warning("Candidate skills query failed: %s", exc)
    return counter


@st.cache_data(ttl=60, show_spinner=False)
def _load_job_skills(recruiter_email: str) -> Counter:
    """Return Counter of skills required across all open jobs."""
    counter: Counter = Counter()
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT skills_required FROM jobs WHERE recruiter_email = %s AND skills_required IS NOT NULL",
                (recruiter_email,),
            )
            for (skills_str,) in cur.fetchall():
                for s in skills_str.split(","):
                    s = s.strip().lower()
                    if s:
                        counter[s] += 1
            cur.close()
    except Exception as exc:
        logger.warning("Job skills query failed: %s", exc)
    return counter


@st.cache_data(ttl=60, show_spinner=False)
def _load_pipeline_by_job(recruiter_email: str) -> list[dict]:
    """Stage counts grouped by job title."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COALESCE(j.job_title, 'Unassigned') AS job_title,
                    p.stage,
                    COUNT(*) AS cnt
                FROM ats_pipeline p
                LEFT JOIN jobs j ON j.job_id = p.job_id
                WHERE p.recruiter_email = %s
                GROUP BY j.job_title, p.stage
                ORDER BY j.job_title, p.stage
            """, (recruiter_email,))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("Pipeline by job query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _load_overall_pipeline(recruiter_email: str) -> list[dict]:
    """Overall stage distribution across all jobs."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT stage, COUNT(*) AS cnt
                FROM ats_pipeline
                WHERE recruiter_email = %s
                GROUP BY stage
            """, (recruiter_email,))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("Overall pipeline query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _load_score_distribution(recruiter_email: str) -> list[float]:
    """Resume scores for all pipeline candidates."""
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT resume_score FROM ats_pipeline WHERE recruiter_email = %s AND resume_score IS NOT NULL",
                (recruiter_email,),
            )
            scores = [float(r[0]) for r in cur.fetchall()]
            cur.close()
        return scores
    except Exception as exc:
        logger.warning("Score distribution query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _load_top_jobs_by_applicants(recruiter_email: str) -> list[dict]:
    """Top job roles ranked by applicant count."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT COALESCE(j.job_title, 'Unassigned') AS job_title, COUNT(*) AS cnt
                FROM ats_pipeline p
                LEFT JOIN jobs j ON j.job_id = p.job_id
                WHERE p.recruiter_email = %s
                GROUP BY j.job_title
                ORDER BY cnt DESC
                LIMIT 10
            """, (recruiter_email,))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("Top jobs query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _load_interview_modes(recruiter_email: str) -> list[dict]:
    """Interview date presence as a proxy for scheduled interviews per job."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    CASE
                        WHEN p.interview_date IS NOT NULL AND p.interview_date != '' THEN 'Scheduled'
                        ELSE 'Not Scheduled'
                    END AS mode,
                    COUNT(*) AS cnt
                FROM ats_pipeline p
                WHERE p.recruiter_email = %s
                GROUP BY mode
            """, (recruiter_email,))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("Interview modes query failed: %s", exc)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _load_avg_feedback_rating(recruiter_email: str) -> list[dict]:
    """Top candidates by resume score who have feedback written."""
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COALESCE(j.job_title, 'Unassigned') AS job_title,
                    ROUND(AVG(p.resume_score), 1) AS avg_rating,
                    COUNT(*) AS cnt
                FROM ats_pipeline p
                LEFT JOIN jobs j ON j.job_id = p.job_id
                WHERE p.recruiter_email = %s
                  AND p.feedback IS NOT NULL AND p.feedback != ''
                GROUP BY j.job_title
                ORDER BY avg_rating DESC
            """, (recruiter_email,))
            rows = cur.fetchall()
            cur.close()
        return rows
    except Exception as exc:
        logger.warning("Feedback rating query failed: %s", exc)
        return []


# ══════════════════════════════════════════════
#  CHART BUILDERS
# ══════════════════════════════════════════════

def _chart_top_skills(counter: Counter, top_n: int = 20) -> go.Figure:
    top = counter.most_common(top_n)
    if not top:
        return None
    skills = [t[0] for t in reversed(top)]
    counts = [t[1] for t in reversed(top)]
    colors = [
        f"hsl({int(i / len(skills) * 260 + 200)},70%,60%)"
        for i in range(len(skills))
    ]
    fig = go.Figure(go.Bar(
        x=counts, y=skills, orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.15)", width=1)),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR, size=11),
        hovertemplate="<b>%{y}</b><br>Candidates: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("🛠 Top Candidate Skills by Frequency", height=max(360, len(skills) * 26 + 80)),
        xaxis=dict(title="Candidate Count", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, automargin=True),
    )
    return fig


def _chart_skills_pie(counter: Counter, top_n: int = 12) -> go.Figure:
    top = counter.most_common(top_n)
    if not top:
        return None
    labels = [t[0] for t in top]
    values = [t[1] for t in top]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.45,
        textinfo="percent",
        textposition="inside",
        textfont=dict(color="#ffffff", size=11),
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
        marker=dict(line=dict(color="rgba(0,0,0,0.25)", width=2)),
        showlegend=True,
    ))
    layout = _base_layout("🥧 Skill Share Distribution (Top 12)", height=420)
    layout["margin"] = dict(l=20, r=140, t=50, b=20)
    fig.update_layout(
        **layout,
        legend=dict(
            font=dict(color=_FONT_COLOR, size=11),
            orientation="v",
            x=1.02, y=0.5,
            xanchor="left", yanchor="middle",
        ),
    )
    return fig


def _chart_skill_gap(candidate_counter: Counter, job_counter: Counter, top_n: int = 15) -> go.Figure:
    """Side-by-side bar: job demand vs candidate supply for top demanded skills."""
    top_demanded = [s for s, _ in job_counter.most_common(top_n)]
    if not top_demanded:
        return None

    demanded  = [job_counter[s]       for s in top_demanded]
    available = [candidate_counter[s] for s in top_demanded]
    gap       = [max(0, d - a)        for d, a in zip(demanded, available)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Job Demand", x=top_demanded, y=demanded,
        marker=dict(color="#3b82f6", line=dict(color="rgba(0,0,0,0.15)", width=1)),
        hovertemplate="<b>%{x}</b><br>Jobs requiring: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Candidate Supply", x=top_demanded, y=available,
        marker=dict(color="#10b981", line=dict(color="rgba(0,0,0,0.15)", width=1)),
        hovertemplate="<b>%{x}</b><br>Candidates with skill: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Gap", x=top_demanded, y=gap,
        marker=dict(color="#ef4444", line=dict(color="rgba(0,0,0,0.15)", width=1)),
        hovertemplate="<b>%{x}</b><br>Unfilled gap: %{y}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("📉 Skill Gap Analysis — Job Demand vs Candidate Supply", height=420),
        barmode="group",
        xaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, tickangle=-35),
        yaxis=dict(title="Count", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        bargap=0.2,
        legend=dict(orientation="h", y=-0.25, font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_gap_heatmap(candidate_counter: Counter, job_counter: Counter, top_n: int = 15) -> go.Figure:
    """Horizontal bar showing gap magnitude per skill (red = high gap)."""
    top_demanded = [s for s, _ in job_counter.most_common(top_n)]
    if not top_demanded:
        return None
    gaps   = [max(0, job_counter[s] - candidate_counter[s]) for s in top_demanded]
    paired = sorted(zip(gaps, top_demanded), reverse=True)
    gaps, skills = zip(*paired) if paired else ([], [])

    fig = go.Figure(go.Bar(
        x=list(gaps), y=list(skills), orientation="h",
        marker=dict(
            color=list(gaps),
            colorscale=[[0, "#10b981"], [0.5, "#f59e0b"], [1, "#ef4444"]],
            showscale=True,
            colorbar=dict(title=dict(text="Gap", font=dict(color=_FONT_COLOR)), tickfont=dict(color=_FONT_COLOR)),
            line=dict(color="rgba(0,0,0,0.15)", width=1),
        ),
        text=list(gaps), textposition="outside",
        textfont=dict(color=_FONT_COLOR),
        hovertemplate="<b>%{y}</b><br>Gap: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("🔴 Skill Gap Severity (High = Critical Shortage)", height=max(360, len(skills) * 26 + 80)),
        xaxis=dict(title="Unfilled Gap", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, automargin=True),
    )
    return fig


def _chart_pipeline_by_job(rows: list[dict]) -> go.Figure:
    """Grouped bar: Selected / Rejected / Active per job."""
    if not rows:
        return None

    # Build job → stage → count map
    job_stage: dict[str, dict[str, int]] = {}
    for r in rows:
        jt = r["job_title"]
        st_ = r["stage"]
        job_stage.setdefault(jt, {})
        job_stage[jt][st_] = int(r["cnt"])

    jobs = list(job_stage.keys())
    stages_to_show = ["Selected", "Rejected", "Interview", "Screening", "Applied"]

    fig = go.Figure()
    for stage in stages_to_show:
        counts = [job_stage[j].get(stage, 0) for j in jobs]
        if any(c > 0 for c in counts):
            fig.add_trace(go.Bar(
                name=stage, x=jobs, y=counts,
                marker=dict(
                    color=_STAGE_COLORS.get(stage, "#94a3b8"),
                    line=dict(color="rgba(0,0,0,0.15)", width=1),
                ),
                hovertemplate=f"<b>%{{x}}</b><br>{stage}: %{{y}}<extra></extra>",
            ))

    fig.update_layout(
        **_base_layout("💼 Pipeline Status by Job Role", height=420),
        barmode="group",
        xaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, tickangle=-30, automargin=True),
        yaxis=dict(title="Candidates", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        bargap=0.2,
        legend=dict(orientation="h", y=-0.28, font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_overall_pipeline_donut(rows: list[dict]) -> go.Figure:
    """Donut chart of overall stage distribution."""
    if not rows:
        return None
    stages = [r["stage"] for r in rows]
    counts = [int(r["cnt"]) for r in rows]
    colors = [_STAGE_COLORS.get(s, "#94a3b8") for s in stages]

    fig = go.Figure(go.Pie(
        labels=stages, values=counts,
        hole=0.5,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.25)", width=2)),
        textinfo="label+value+percent",
        textfont=dict(color=_FONT_COLOR, size=12),
        pull=[0.05 if s in ("Selected", "Rejected") else 0 for s in stages],
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("🍩 Overall Pipeline Distribution"),
        legend=dict(font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_selected_rejected_bar(rows: list[dict]) -> go.Figure:
    """Simple bar: Selected vs Rejected vs Active totals."""
    if not rows:
        return None
    stage_map = {r["stage"]: int(r["cnt"]) for r in rows}
    selected  = stage_map.get("Selected", 0)
    rejected  = stage_map.get("Rejected", 0)
    active    = sum(v for k, v in stage_map.items() if k not in ("Selected", "Rejected"))

    labels = ["Selected", "Rejected", "Active"]
    values = [selected, rejected, active]
    colors = ["#10b981", "#ef4444", "#3b82f6"]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.2)", width=1)),
        text=values, textposition="outside",
        textfont=dict(color=_FONT_COLOR, size=13),
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
        width=0.45,
    ))
    fig.update_layout(
        **_base_layout("✅ Selected vs ❌ Rejected vs 🔵 Active"),
        xaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(title="Candidates", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
    )
    return fig


def _chart_hiring_funnel(rows: list[dict]) -> go.Figure:
    """Funnel chart: Applied → Screening → Interview → Selected."""
    if not rows:
        return None
    stage_map = {r["stage"]: int(r["cnt"]) for r in rows}
    order  = ["Applied", "Screening", "Interview", "Selected"]
    labels = [s for s in order if stage_map.get(s, 0) > 0]
    values = [stage_map[s] for s in labels]
    colors = [_STAGE_COLORS[s] for s in labels]
    fig = go.Figure(go.Funnel(
        y=labels, x=values,
        textinfo="value+percent initial",
        textfont=dict(color="#ffffff", size=13),
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.2)", width=1)),
        connector=dict(line=dict(color="rgba(255,255,255,0.1)", width=2)),
        hovertemplate="<b>%{y}</b><br>Count: %{x}<br>%{percentInitial} of total<extra></extra>",
    ))
    layout = _base_layout("🔽 Hiring Funnel", height=360)
    layout["margin"] = dict(l=120, r=40, t=50, b=30)
    fig.update_layout(**layout)
    return fig


def _chart_score_distribution(scores: list[float]) -> go.Figure:
    """Histogram of resume scores bucketed into 10-point bands."""
    if not scores:
        return None
    buckets = list(range(0, 101, 10))
    counts  = [0] * 10
    for s in scores:
        idx = min(int(s // 10), 9)
        counts[idx] += 1
    labels = [f"{b}-{b+10}" for b in buckets[:-1]]
    colors = [
        "#ef4444" if b < 40 else "#f59e0b" if b < 70 else "#10b981"
        for b in buckets[:-1]
    ]
    fig = go.Figure(go.Bar(
        x=labels, y=counts,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.15)", width=1)),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR, size=11),
        hovertemplate="<b>Score %{x}</b><br>Candidates: %{y}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("📊 Resume Score Distribution", height=340),
        xaxis=dict(title="Score Range", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(title="Candidates", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        bargap=0.15,
    )
    return fig


def _chart_top_jobs(rows: list[dict]) -> go.Figure:
    """Horizontal bar: top job roles by applicant count."""
    if not rows:
        return None
    jobs   = [r["job_title"] for r in reversed(rows)]
    counts = [int(r["cnt"]) for r in reversed(rows)]
    colors = [
        f"hsl({int(i / len(jobs) * 200 + 180)},65%,58%)"
        for i in range(len(jobs))
    ]
    fig = go.Figure(go.Bar(
        x=counts, y=jobs, orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.15)", width=1)),
        text=counts, textposition="outside",
        textfont=dict(color=_FONT_COLOR, size=11),
        hovertemplate="<b>%{y}</b><br>Applicants: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("💼 Top Job Roles by Applicants", height=max(300, len(jobs) * 36 + 80)),
        xaxis=dict(title="Applicants", gridcolor=_GRID_COLOR, color=_FONT_COLOR),
        yaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, automargin=True),
    )
    return fig


def _chart_interview_modes(rows: list[dict]) -> go.Figure:
    """Donut: interview mode breakdown."""
    if not rows:
        return None
    labels = [r["mode"] for r in rows]
    values = [int(r["cnt"]) for r in rows]
    colors = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981", "#ec4899"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.48,
        marker=dict(colors=colors[:len(labels)], line=dict(color="rgba(0,0,0,0.2)", width=1)),
        textinfo="label+percent",
        textfont=dict(color=_FONT_COLOR, size=11),
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("📅 Interview Schedule Status", height=320),
        legend=dict(font=dict(color=_FONT_COLOR)),
    )
    return fig


def _chart_feedback_ratings(rows: list[dict]) -> go.Figure:
    """Bar: avg interview feedback rating per job role."""
    if not rows:
        return None
    jobs    = [r["job_title"] for r in rows]
    ratings = [float(r["avg_rating"]) for r in rows]
    colors  = [
        "#10b981" if r >= 70 else "#f59e0b" if r >= 40 else "#ef4444"
        for r in ratings
    ]
    fig = go.Figure(go.Bar(
        x=jobs, y=ratings,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0.15)", width=1)),
        text=[f"{r:.0f}%" for r in ratings], textposition="outside",
        textfont=dict(color=_FONT_COLOR, size=12),
        hovertemplate="<b>%{x}</b><br>Avg Score: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout("💬 Avg Resume Score — Candidates with Feedback", height=340),
        xaxis=dict(gridcolor=_GRID_COLOR, color=_FONT_COLOR, tickangle=-25, automargin=True),
        yaxis=dict(title="Avg Score (%)", gridcolor=_GRID_COLOR, color=_FONT_COLOR, range=[0, 110]),
    )
    return fig


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════

def _kpi_card(col, icon: str, label: str, value, color: str) -> None:
    col.markdown(
        f"<div style='background:rgba(255,255,255,0.05);border-radius:18px;"
        f"padding:20px 14px;border:1px solid {color}30;"
        f"box-shadow:0 4px 20px {color}20;text-align:center'>"
        f"<div style='font-size:1.4rem'>{icon}</div>"
        f"<div style='font-size:0.68rem;font-weight:700;color:#94a3b8;"
        f"text-transform:uppercase;letter-spacing:0.06em;margin:6px 0 4px'>{label}</div>"
        f"<div style='font-size:1.9rem;font-weight:900;color:{color};line-height:1'>{value}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _section(title: str) -> None:
    st.markdown(
        f"<div style='font-size:1rem;font-weight:800;color:#f1f5f9;"
        f"margin:28px 0 14px;padding-bottom:8px;"
        f"border-bottom:1px solid rgba(255,255,255,0.08)'>{title}</div>",
        unsafe_allow_html=True,
    )


_CHART_CFG = {"displayModeBar": False}


# ══════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "📋 Recruiter Dashboard",
        "Live KPIs · Skill analytics · Skill gap analysis · Pipeline charts",
    )

    recruiter_email = st.session_state.get("recruiter_email", "")

    # ── KPI cards ──────────────────────────────────────────────────────────
    kpis = _load_kpis(recruiter_email)

    k1, k2, k3, k4 = st.columns(4)
    _kpi_card(k1, "👥", "Total Candidates",    kpis["total_candidates"],          "#3b82f6")
    _kpi_card(k2, "💼", "Open Job Openings",   kpis["total_jobs"],                "#8b5cf6")
    _kpi_card(k3, "🔍", "Shortlisted",         kpis["shortlisted"],               "#06b6d4")
    _kpi_card(k4, "🎤", "Interviews Scheduled", kpis["interviews"],               "#f59e0b")

    st.markdown("<br>", unsafe_allow_html=True)

    k5, k6, k7, k8 = st.columns(4)
    _kpi_card(k5, "✅", "Selected",            kpis["selected"],                  "#10b981")
    _kpi_card(k6, "❌", "Rejected",            kpis["rejected"],                  "#ef4444")
    _kpi_card(k7, "🎯", "Avg Hiring Score",    f"{kpis['avg_hiring_score']}%",    "#ec4899")
    _kpi_card(k8, "🗂️", "Candidate Pipeline",  kpis["pipeline_total"],            "#a78bfa")

    st.divider()

    # ── Load data ──────────────────────────────────────────────────────────
    cand_skills    = _load_candidate_skills(recruiter_email)
    job_skills     = _load_job_skills(recruiter_email)
    pipeline_rows  = _load_pipeline_by_job(recruiter_email)
    overall_rows   = _load_overall_pipeline(recruiter_email)
    scores         = _load_score_distribution(recruiter_email)
    top_jobs_rows  = _load_top_jobs_by_applicants(recruiter_email)
    mode_rows      = _load_interview_modes(recruiter_email)
    rating_rows    = _load_avg_feedback_rating(recruiter_email)

    no_candidates = kpis["total_candidates"] == 0
    no_pipeline   = kpis["pipeline_total"] == 0

    # ══════════════════════════════════════════════
    #  SECTION 1 — CANDIDATE SKILLS
    # ══════════════════════════════════════════════
    _section("🛠 Candidate Skills Overview")

    if no_candidates or not cand_skills:
        st.info("No candidate skill data yet. Upload resumes first.")
    else:
        col1, col2 = st.columns([3, 2])
        with col1:
            fig = _chart_top_skills(cand_skills, top_n=20)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        with col2:
            fig = _chart_skills_pie(cand_skills, top_n=12)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)

    # ══════════════════════════════════════════════
    #  SECTION 2 — RESUME SCORE DISTRIBUTION
    # ══════════════════════════════════════════════
    _section("📊 Resume Score & Pipeline Overview")

    if no_pipeline:
        st.info("No pipeline data yet.")
    else:
        col_s1, col_s2 = st.columns([2, 2])
        with col_s1:
            fig = _chart_score_distribution(scores)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        with col_s2:
            fig = _chart_top_jobs(top_jobs_rows)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)

    # ══════════════════════════════════════════════
    #  SECTION 3 — SKILL GAP ANALYSIS
    # ══════════════════════════════════════════════
    _section("📉 Skill Gap Analysis")

    if not cand_skills or not job_skills:
        st.info("Skill gap analysis requires both candidates and jobs with skills defined.")
    else:
        fig_gap = _chart_skill_gap(cand_skills, job_skills, top_n=15)
        if fig_gap:
            st.plotly_chart(fig_gap, use_container_width=True, config=_CHART_CFG)

        fig_heat = _chart_gap_heatmap(cand_skills, job_skills, top_n=15)
        if fig_heat:
            st.plotly_chart(fig_heat, use_container_width=True, config=_CHART_CFG)

        # Insight summary
        top_gaps = sorted(
            [(s, max(0, job_skills[s] - cand_skills[s])) for s in job_skills],
            key=lambda x: x[1], reverse=True,
        )[:5]
        critical = [s for s, g in top_gaps if g > 0]
        if critical:
            st.markdown(
                "<div style='background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);"
                "border-radius:12px;padding:14px 18px;margin-top:8px'>"
                "<div style='font-size:0.82rem;font-weight:700;color:#fca5a5;margin-bottom:6px'>"
                "⚠️ Critical Skill Shortages</div>"
                "<div style='font-size:0.8rem;color:#fecaca'>"
                + " &nbsp;·&nbsp; ".join(
                    f"<b>{s}</b> (gap: {g})" for s, g in top_gaps if g > 0
                )
                + "</div></div>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════
    #  SECTION 4 — PIPELINE & SELECTION CHARTS
    # ══════════════════════════════════════════════
    _section("📊 Job Pipeline — Selected / Rejected / Active")

    if no_pipeline:
        st.info("No pipeline data yet. Add candidates via **ATS Dashboard → Edit / Add**.")
    else:
        col3, col4 = st.columns([3, 2])
        with col3:
            fig = _chart_pipeline_by_job(pipeline_rows)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        with col4:
            fig = _chart_overall_pipeline_donut(overall_rows)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)

        col5, col6 = st.columns([1, 1])
        with col5:
            fig = _chart_selected_rejected_bar(overall_rows)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        with col6:
            fig = _chart_hiring_funnel(overall_rows)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)

    # ══════════════════════════════════════════════
    #  SECTION 5 — INTERVIEWS
    # ══════════════════════════════════════════════
    _section("🎤 Interview Analytics")

    col7, col8 = st.columns([1, 2])
    with col7:
        fig = _chart_interview_modes(mode_rows)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        else:
            st.info("No interview schedule data yet.")
    with col8:
        fig = _chart_feedback_ratings(rating_rows)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)
        else:
            st.info("No interview feedback ratings yet.")
