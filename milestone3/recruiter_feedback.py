"""Recruiter Feedback Module — star rating, comments, store & history."""

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

# ── DB ─────────────────────────────────────────────────────────────────────

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


def _init_db() -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recruiter_feedback (
                feedback_id   INT          NOT NULL AUTO_INCREMENT,
                candidate_id  INT          NOT NULL,
                recruiter     VARCHAR(255) NOT NULL DEFAULT '',
                rating        TINYINT      NOT NULL DEFAULT 0 COMMENT '1-5 stars',
                comment       TEXT         NOT NULL,
                stage         VARCHAR(50)  NOT NULL DEFAULT '',
                created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (feedback_id),
                INDEX idx_candidate (candidate_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.close()


def _save_feedback(candidate_id: int, recruiter: str, rating: int,
                   comment: str, stage: str) -> None:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO recruiter_feedback "
            "(candidate_id, recruiter, rating, comment, stage) "
            "VALUES (%s, %s, %s, %s, %s)",
            (candidate_id, recruiter.strip(), rating, comment.strip(), stage),
        )
        cur.close()


def _load_feedback(candidate_id: int) -> list[dict]:
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM recruiter_feedback "
            "WHERE candidate_id = %s ORDER BY created_at DESC",
            (candidate_id,),
        )
        rows = cur.fetchall()
        cur.close()
    return rows


def _load_all_feedback() -> list[dict]:
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT rf.*, c.name AS cand_name "
            "FROM recruiter_feedback rf "
            "LEFT JOIN candidates c ON c.candidate_id = rf.candidate_id "
            "ORDER BY rf.created_at DESC"
        )
        rows = cur.fetchall()
        cur.close()
    return rows


# ── UI helpers ─────────────────────────────────────────────────────────────

_STAR_COLORS = {1: "#ef4444", 2: "#f97316", 3: "#f59e0b", 4: "#34d399", 5: "#10b981"}
_STAR_LABELS = {1: "Poor", 2: "Fair", 3: "Good", 4: "Great", 5: "Excellent"}


def _stars_html(rating: int, size: str = "1.4rem") -> str:
    color = _STAR_COLORS.get(rating, "#64748b")
    filled = "★" * rating
    empty  = "☆" * (5 - rating)
    return (
        f"<span style='font-size:{size};color:{color};letter-spacing:2px'>{filled}</span>"
        f"<span style='font-size:{size};color:rgba(255,255,255,0.15);letter-spacing:2px'>{empty}</span>"
        f"<span style='font-size:0.75rem;font-weight:700;color:{color};"
        f"margin-left:8px;vertical-align:middle'>{_STAR_LABELS.get(rating,'')}</span>"
    )


def _feedback_card(fb: dict, show_candidate: bool = False) -> None:
    rating    = fb.get("rating") or 0
    color     = _STAR_COLORS.get(rating, "#64748b")
    recruiter = html.escape(fb.get("recruiter") or "Anonymous")
    comment   = html.escape(fb.get("comment") or "—")
    stage     = html.escape(fb.get("stage") or "")
    ts        = fb.get("created_at")
    date_str  = ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts)[:16]
    name_line = ""
    if show_candidate:
        cname = html.escape((fb.get("cand_name") or "Unknown").splitlines()[0])
        name_line = (
            f"<div style='font-size:0.78rem;font-weight:700;color:#a78bfa;"
            f"margin-bottom:6px'>👤 {cname}</div>"
        )

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:16px;"
        f"padding:18px 20px;border:1px solid {color}25;"
        f"border-left:4px solid {color};margin-bottom:10px'>"
        f"{name_line}"
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"margin-bottom:10px'>"
        f"<div>{_stars_html(rating)}</div>"
        f"<div style='font-size:0.68rem;color:#64748b'>{date_str}</div>"
        f"</div>"
        f"<div style='font-size:0.88rem;color:#e2e8f0;line-height:1.6;"
        f"margin-bottom:10px'>{comment}</div>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap'>"
        f"<span style='font-size:0.68rem;font-weight:700;color:#94a3b8;"
        f"background:rgba(255,255,255,0.06);padding:3px 10px;border-radius:20px'>"
        f"👤 {recruiter}</span>"
        + (f"<span style='font-size:0.68rem;font-weight:700;color:#a78bfa;"
           f"background:rgba(139,92,246,0.1);padding:3px 10px;border-radius:20px'>"
           f"📍 {stage}</span>" if stage else "")
        + f"</div></div>",
        unsafe_allow_html=True,
    )


# ── Rating widget (clickable stars via radio) ──────────────────────────────

def _star_selector(key: str) -> int:
    """Render a 1-5 star selector using a styled radio group. Returns chosen int."""
    options = ["⭐ 1 — Poor", "⭐⭐ 2 — Fair", "⭐⭐⭐ 3 — Good",
               "⭐⭐⭐⭐ 4 — Great", "⭐⭐⭐⭐⭐ 5 — Excellent"]
    st.markdown(
        "<style>.star-radio div[role='radiogroup']{display:flex;gap:8px;flex-wrap:wrap}"
        ".star-radio div[role='radiogroup'] label{background:rgba(255,255,255,0.05);"
        "border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:8px 14px;"
        "font-size:0.82rem;cursor:pointer;transition:all 0.2s}"
        ".star-radio div[role='radiogroup'] label:hover{border-color:#f59e0b;"
        "background:rgba(245,158,11,0.1)}</style>",
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="star-radio">', unsafe_allow_html=True)
        choice = st.radio("Rating", options, key=key, horizontal=True,
                          label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)
    return options.index(choice) + 1


# ── Tabs ───────────────────────────────────────────────────────────────────

def _tab_submit(candidates: list[dict]) -> None:
    """Tab: submit new feedback for a candidate."""
    if not candidates:
        st.info("No candidates found. Upload resumes first.")
        return

    opts = {
        f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
        for c in candidates
    }

    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.85rem;font-weight:700;color:#a78bfa;"
            "margin-bottom:16px'>📝 Submit Candidate Feedback</div>",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns([3, 2])
        with col1:
            sel_key  = st.selectbox("Select Candidate", list(opts.keys()),
                                    key="fb_cand_sel")
            selected = opts[sel_key]
            cid      = selected["candidate_id"]
        with col2:
            recruiter = st.text_input("Your Name (Recruiter)", placeholder="e.g. Priya Sharma",
                                      key="fb_recruiter")

        stage = st.selectbox("Pipeline Stage",
                             ["Applied", "Screening", "Interview", "Selected", "Rejected"],
                             key="fb_stage")

        st.markdown(
            "<div style='font-size:0.8rem;font-weight:600;color:#94a3b8;"
            "margin:14px 0 8px'>⭐ Rating</div>",
            unsafe_allow_html=True,
        )
        rating = _star_selector("fb_rating")

        # Live star preview
        st.markdown(
            f"<div style='margin:8px 0 16px'>{_stars_html(rating, '1.8rem')}</div>",
            unsafe_allow_html=True,
        )

        comment = st.text_area(
            "💬 Comments",
            placeholder="Share your observations about this candidate — strengths, concerns, overall impression…",
            height=130,
            key="fb_comment",
        )

        if st.button("💾 Submit Feedback", type="primary", use_container_width=True,
                     key="fb_submit"):
            if not recruiter.strip():
                st.warning("Please enter your name.")
            elif not comment.strip():
                st.warning("Please add a comment before submitting.")
            else:
                _save_feedback(cid, recruiter, rating, comment, stage)
                st.success(
                    f"✅ Feedback submitted for **{(selected.get('name') or 'Candidate').splitlines()[0]}** "
                    f"— {_STAR_LABELS[rating]} ({rating}/5)"
                )
                st.balloons()


def _tab_history(candidates: list[dict]) -> None:
    """Tab: view feedback history per candidate."""
    if not candidates:
        st.info("No candidates found.")
        return

    opts = {
        f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
        for c in candidates
    }

    col1, col2 = st.columns([3, 2])
    with col1:
        sel_key  = st.selectbox("Select Candidate", list(opts.keys()), key="hist_cand_sel")
        selected = opts[sel_key]
        cid      = selected["candidate_id"]
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)

    feedbacks = _load_feedback(cid)
    name      = (selected.get("name") or "Unknown").splitlines()[0]

    if not feedbacks:
        st.info(f"No feedback recorded for **{name}** yet.")
        return

    # Summary bar
    avg_rating = round(sum(f["rating"] for f in feedbacks) / len(feedbacks), 1)
    avg_color  = _STAR_COLORS.get(round(avg_rating), "#f59e0b")
    s1, s2, s3 = st.columns(3)
    for col, label, val, clr in [
        (s1, "Total Reviews", len(feedbacks), "#3b82f6"),
        (s2, "Avg Rating",    f"{avg_rating}/5", avg_color),
        (s3, "Latest Stage",  feedbacks[0].get("stage") or "—", "#8b5cf6"),
    ]:
        col.markdown(
            f"<div style='background:rgba(255,255,255,0.04);border-radius:14px;"
            f"padding:16px;border:1px solid {clr}25;text-align:center'>"
            f"<div style='font-size:1.6rem;font-weight:900;color:{clr}'>{val}</div>"
            f"<div style='font-size:0.68rem;color:#94a3b8;margin-top:4px;"
            f"text-transform:uppercase;letter-spacing:0.08em;font-weight:700'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
        f"margin-bottom:12px'>📋 {len(feedbacks)} feedback record(s) for "
        f"<span style='color:#f1f5f9'>{html.escape(name)}</span></div>",
        unsafe_allow_html=True,
    )

    for fb in feedbacks:
        _feedback_card(fb)


def _tab_all(candidates: list[dict]) -> None:
    """Tab: all feedback across all candidates with search/filter."""
    feedbacks = _load_all_feedback()

    if not feedbacks:
        st.info("No feedback submitted yet.")
        return

    # Filters
    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        search = st.text_input("🔍 Search candidate / recruiter",
                               placeholder="Type to filter…", key="all_fb_search")
    with f2:
        rating_filter = st.selectbox("Filter by Rating",
                                     ["All", "5 ⭐", "4 ⭐", "3 ⭐", "2 ⭐", "1 ⭐"],
                                     key="all_fb_rating")
    with f3:
        stage_filter = st.selectbox("Filter by Stage",
                                    ["All", "Applied", "Screening", "Interview",
                                     "Selected", "Rejected"],
                                    key="all_fb_stage")

    filtered = feedbacks
    if search:
        q = search.lower()
        filtered = [f for f in filtered
                    if q in (f.get("cand_name") or "").lower()
                    or q in (f.get("recruiter") or "").lower()]
    if rating_filter != "All":
        r = int(rating_filter[0])
        filtered = [f for f in filtered if f.get("rating") == r]
    if stage_filter != "All":
        filtered = [f for f in filtered if f.get("stage") == stage_filter]

    st.caption(f"Showing {len(filtered)} of {len(feedbacks)} feedback records")
    st.divider()

    for fb in filtered:
        _feedback_card(fb, show_candidate=True)


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header("⭐ Recruiter Feedback", "Rate candidates, add comments and track feedback history.")

    try:
        _init_db()
    except Exception as e:
        st.error(f"DB init failed: {e}")
        return

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))

    tab_submit, tab_history, tab_all = st.tabs([
        "📝 Submit Feedback", "📋 Candidate History", "🗂️ All Feedback",
    ])

    with tab_submit:
        _tab_submit(candidates)

    with tab_history:
        _tab_history(candidates)

    with tab_all:
        _tab_all(candidates)
