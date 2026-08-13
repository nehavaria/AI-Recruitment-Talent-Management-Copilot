"""Candidate Activity Timeline — vertical timeline of all recruitment events."""

import html
import logging
from contextlib import contextmanager
from typing import Generator

import mysql.connector
import streamlit as st

from config.settings import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_CFG = dict(host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
            user=MYSQL_USER, password=MYSQL_PASSWORD,
            autocommit=False, charset="utf8mb4")


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


# ── Event config ───────────────────────────────────────────────────────────

_EVENT_CFG = {
    "resume_uploaded":      {"icon": "📄", "color": "#3b82f6",  "label": "Resume Uploaded"},
    "resume_parsed":        {"icon": "🔍", "color": "#8b5cf6",  "label": "Resume Parsed"},
    "shortlisted":          {"icon": "⭐", "color": "#06b6d4",  "label": "Shortlisted"},
    "interview_scheduled":  {"icon": "📅", "color": "#f59e0b",  "label": "Interview Scheduled"},
    "interview_completed":  {"icon": "🎤", "color": "#f97316",  "label": "Interview Completed"},
    "feedback_added":       {"icon": "💬", "color": "#a78bfa",  "label": "Feedback Added"},
    "selected":             {"icon": "✅", "color": "#10b981",  "label": "Selected"},
    "rejected":             {"icon": "❌", "color": "#ef4444",  "label": "Rejected"},
}


# ── Data fetching ──────────────────────────────────────────────────────────

def _fetch_events(candidate_id: int, candidate: dict) -> list[dict]:
    """Build a chronological list of events for a candidate from all sources."""
    events: list[dict] = []

    # 1. Resume Uploaded — use candidate created_date
    created = candidate.get("created_date")
    if created:
        events.append({
            "type": "resume_uploaded",
            "ts": created,
            "detail": f"Resume file: {html.escape((candidate.get('resume_path') or 'N/A').split('/')[-1].split(chr(92))[-1])}",
        })
        # 2. Resume Parsed — same timestamp, slightly after upload
        events.append({
            "type": "resume_parsed",
            "ts": created,
            "detail": (
                f"Skills: {html.escape((candidate.get('skills') or 'N/A')[:80])}…"
                if len(candidate.get('skills') or '') > 80
                else f"Skills: {html.escape(candidate.get('skills') or 'N/A')}"
            ),
        })

    # 3–7. ATS pipeline events
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT stage, recruiter, resume_score, interview_date, updated_at "
                "FROM ats_pipeline WHERE candidate_id = %s",
                (candidate_id,),
            )
            pipeline = cur.fetchone()
            cur.close()

        if pipeline:
            stage      = (pipeline.get("stage") or "").strip()
            updated_at = pipeline.get("updated_at")
            recruiter  = html.escape(pipeline.get("recruiter") or "Recruiter")
            score      = pipeline.get("resume_score") or 0.0

            # Shortlisted = Screening stage
            if stage in ("Screening", "Interview", "Selected", "Rejected"):
                events.append({
                    "type": "shortlisted",
                    "ts": updated_at,
                    "detail": f"Moved to Screening by {recruiter} · Resume Score: {score:.1f}%",
                })

            # Interview Scheduled
            idate_str = (pipeline.get("interview_date") or "").strip()
            if idate_str:
                events.append({
                    "type": "interview_scheduled",
                    "ts": updated_at,
                    "detail": f"Interview date: {html.escape(idate_str)} · Mode: In-Person",
                })

            # Interview Completed
            if stage in ("Selected", "Rejected") or (stage == "Interview" and idate_str):
                events.append({
                    "type": "interview_completed",
                    "ts": updated_at,
                    "detail": f"Interview stage completed · Interviewer: {recruiter}",
                })

            # Selected / Rejected
            if stage == "Selected":
                events.append({
                    "type": "selected",
                    "ts": updated_at,
                    "detail": f"Candidate selected by {recruiter} 🎉",
                })
            elif stage == "Rejected":
                events.append({
                    "type": "rejected",
                    "ts": updated_at,
                    "detail": f"Candidate rejected at {stage} stage",
                })

    except Exception as e:
        logger.warning("ATS pipeline fetch failed for cid=%s: %s", candidate_id, e)

    # 8. Feedback Added — from recruiter_feedback table
    try:
        with _db() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT recruiter, rating, comment, stage, created_at "
                "FROM recruiter_feedback WHERE candidate_id = %s "
                "ORDER BY created_at ASC",
                (candidate_id,),
            )
            feedbacks = cur.fetchall()
            cur.close()

        for fb in feedbacks:
            stars = "★" * (fb.get("rating") or 0)
            events.append({
                "type": "feedback_added",
                "ts": fb.get("created_at"),
                "detail": (
                    f"{stars} by {html.escape(fb.get('recruiter') or 'Recruiter')} "
                    f"· {html.escape((fb.get('comment') or '')[:80])}"
                    + ("…" if len(fb.get('comment') or '') > 80 else "")
                ),
            })
    except Exception as e:
        logger.warning("Feedback fetch failed for cid=%s: %s", candidate_id, e)

    # Sort by timestamp (None goes last)
    events.sort(key=lambda e: (e["ts"] is None, e["ts"]))
    return events


# ── Timeline renderer ──────────────────────────────────────────────────────

def _fmt_ts(ts) -> str:
    if ts is None:
        return "—"
    if hasattr(ts, "strftime"):
        return ts.strftime("%d %b %Y · %H:%M")
    return str(ts)[:16]


def _render_timeline(events: list[dict]) -> None:
    if not events:
        st.info("No activity recorded for this candidate yet.")
        return

    for i, ev in enumerate(events):
        cfg     = _EVENT_CFG.get(ev["type"], {"icon": "🔵", "color": "#64748b", "label": ev["type"]})
        is_last = i == len(events) - 1
        c       = cfg["color"]
        icon    = cfg["icon"]
        label   = cfg["label"]
        detail  = ev.get("detail", "")
        ts_str  = _fmt_ts(ev.get("ts"))

        line = (
            ""
            if is_last
            else f"<div style='position:absolute;left:19px;top:42px;width:2px;height:calc(100%% - 10px);background:linear-gradient({c}60,rgba(255,255,255,0.05))'></div>"
        )

        card = (
            "<div style='position:relative;display:flex;gap:20px;margin-bottom:0'>"
            + line
            + f"<div style='flex-shrink:0;width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,{c}33,{c}18);border:2px solid {c};display:flex;align-items:center;justify-content:center;font-size:1.1rem;z-index:1;box-shadow:0 0 12px {c}50'>{icon}</div>"
            + f"<div style='flex:1;background:rgba(255,255,255,0.04);border-radius:14px;padding:14px 18px;border:1px solid {c}25;border-left:3px solid {c};margin-bottom:24px'>"
            + f"<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;flex-wrap:wrap;gap:6px'>"
            + f"<span style='font-size:0.88rem;font-weight:700;color:#f1f5f9'>{label}</span>"
            + f"<span style='font-size:0.68rem;color:#64748b;background:rgba(255,255,255,0.05);padding:3px 10px;border-radius:20px'>&#128336; {ts_str}</span>"
            + "</div>"
            + f"<div style='font-size:0.8rem;color:#94a3b8;line-height:1.5'>{detail}</div>"
            + "</div></div>"
        )

        st.markdown(card, unsafe_allow_html=True)


# ── Candidate header card ──────────────────────────────────────────────────

def _candidate_header(c: dict, event_count: int) -> None:
    name     = (c.get("name") or "Unknown").splitlines()[0]
    email    = c.get("email") or "—"
    phone    = c.get("phone") or "—"
    initials = "".join(w[0].upper() for w in name.split()[:2]) or "?"
    skills   = (c.get("skills") or "").split(",")[:4]
    skill_badges = "".join(
        f"<span style='background:rgba(139,92,246,0.15);color:#c4b5fd;"
        f"border:1px solid rgba(139,92,246,0.3);padding:2px 10px;"
        f"border-radius:20px;font-size:0.7rem;margin:2px;display:inline-block'>"
        f"{html.escape(s.strip().title())}</span>"
        for s in skills if s.strip()
    )

    st.markdown(
        f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.12),rgba(37,99,235,0.08));"
        f"border-radius:20px;padding:20px 24px;border:1px solid rgba(124,58,237,0.25);"
        f"display:flex;align-items:center;gap:20px;margin-bottom:24px;flex-wrap:wrap'>"
        f"<div style='width:56px;height:56px;border-radius:16px;flex-shrink:0;"
        f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-weight:900;color:#fff;font-size:1.3rem;"
        f"box-shadow:0 4px 16px rgba(124,58,237,0.4)'>{html.escape(initials)}</div>"
        f"<div style='flex:1;min-width:0'>"
        f"<div style='font-size:1.05rem;font-weight:800;color:#f1f5f9'>{html.escape(name)}</div>"
        f"<div style='font-size:0.75rem;color:#94a3b8;margin-top:3px'>"
        f"📧 {html.escape(email)} &nbsp;·&nbsp; 📞 {html.escape(phone)}</div>"
        f"<div style='margin-top:8px'>{skill_badges}</div>"
        f"</div>"
        f"<div style='text-align:center;flex-shrink:0'>"
        f"<div style='font-size:1.8rem;font-weight:900;color:#a78bfa'>{event_count}</div>"
        f"<div style='font-size:0.65rem;color:#64748b;text-transform:uppercase;"
        f"letter-spacing:0.08em;font-weight:700'>Events</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header("🕐 Candidate Activity Timeline",
                "Full recruitment journey — from resume upload to final decision.")

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    if not candidates:
        st.info("No candidates found. Upload resumes first.")
        return

    # ── Candidate selector + search ───────────────────────────────────────
    col_sel, col_search = st.columns([3, 2])
    with col_search:
        search = st.text_input("🔍 Search candidate", placeholder="Name or email…",
                               key="tl_search")

    filtered = candidates
    if search:
        q = search.lower()
        filtered = [c for c in candidates
                    if q in (c.get("name") or "").lower()
                    or q in (c.get("email") or "").lower()]

    if not filtered:
        st.warning("No candidates match your search.")
        return

    opts = {
        f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
        for c in filtered
    }
    with col_sel:
        sel_key  = st.selectbox("Select Candidate", list(opts.keys()), key="tl_cand_sel")
    selected = opts[sel_key]
    cid      = selected["candidate_id"]

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Build events ──────────────────────────────────────────────────────
    events = _fetch_events(cid, selected)

    # ── Candidate header ──────────────────────────────────────────────────
    _candidate_header(selected, len(events))

    # ── Progress bar showing current stage ───────────────────────────────
    _STAGE_ORDER = ["resume_uploaded", "resume_parsed", "shortlisted",
                    "interview_scheduled", "interview_completed",
                    "feedback_added", "selected"]
    event_types  = {e["type"] for e in events}
    completed    = sum(1 for s in _STAGE_ORDER if s in event_types)
    total_steps  = len(_STAGE_ORDER)
    pct          = round(completed / total_steps * 100)
    bar_color    = "#10b981" if "selected" in event_types else \
                   "#ef4444" if "rejected" in event_types else "#f59e0b"

    st.markdown(
        f"<div style='margin-bottom:24px'>"
        f"<div style='display:flex;justify-content:space-between;margin-bottom:6px'>"
        f"<span style='font-size:0.75rem;font-weight:700;color:#94a3b8;"
        f"text-transform:uppercase;letter-spacing:0.08em'>Journey Progress</span>"
        f"<span style='font-size:0.75rem;font-weight:800;color:{bar_color}'>{pct}%</span>"
        f"</div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:8px;overflow:hidden'>"
        f"<div style='background:linear-gradient(90deg,{bar_color}99,{bar_color});"
        f"height:100%;width:{pct}%;border-radius:20px;"
        f"transition:width 0.6s ease'></div></div>"
        f"<div style='font-size:0.7rem;color:#64748b;margin-top:5px'>"
        f"{completed} of {total_steps} milestones reached</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Event type filter chips ───────────────────────────────────────────
    all_types   = list(dict.fromkeys(e["type"] for e in events))  # preserve order
    filter_opts = ["All"] + [_EVENT_CFG.get(t, {}).get("label", t) for t in all_types]
    chosen      = st.selectbox("🔎 Filter by event type", filter_opts, key="tl_filter")

    if chosen != "All":
        chosen_type = next((t for t in all_types
                            if _EVENT_CFG.get(t, {}).get("label") == chosen), None)
        display_events = [e for e in events if e["type"] == chosen_type]
    else:
        display_events = events

    st.caption(f"Showing {len(display_events)} event(s)")
    st.divider()

    # ── Vertical timeline ─────────────────────────────────────────────────
    _render_timeline(display_events)
