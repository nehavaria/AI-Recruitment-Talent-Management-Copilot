"""Jobs page — recruiter job posting and management."""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from services.job_service import (
    DEPARTMENTS,
    EXP_LEVELS,
    JOB_STATUSES,
    JOB_TYPES,
    JobService,
)
from ui.components import empty_state, page_header, stat_strip

_STATUS_COLOR = {
    "Open":    "#059669",
    "Closed":  "#dc2626",
    "On Hold": "#d97706",
    "Draft":   "#6b7280",
}


# ── Main render ────────────────────────────────────────────────────────────

def render(service: JobService) -> None:
    page_header(
        "💼 Job Postings",
        "Post new jobs, manage existing openings, and track recruitment status.",
    )

    tab_post, tab_manage = st.tabs(["➕ Post a Job", "📋 Manage Jobs"])

    with tab_post:
        _render_post_form(service)

    with tab_manage:
        _render_manage(service)


# ── Post Job Form ──────────────────────────────────────────────────────────

def _render_post_form(service: JobService) -> None:
    st.markdown("### 📝 New Job Posting")

    with st.form("post_job_form", clear_on_submit=True):

        # ── Row 1: Title + Department ──────────────────────────────────────
        c1, c2 = st.columns(2)
        job_title  = c1.text_input("Job Title *", placeholder="e.g. Senior Python Developer")
        department = c2.selectbox("Department", DEPARTMENTS)

        # ── Row 2: Location + Job Type + Exp Level ─────────────────────────
        c1, c2, c3 = st.columns(3)
        location        = c1.text_input("Location", placeholder="e.g. Bangalore / Remote")
        job_type        = c2.selectbox("Job Type", JOB_TYPES)
        experience_level = c3.selectbox("Experience Level", EXP_LEVELS)

        # ── Row 3: Salary + Openings + Deadline ───────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        salary_min = c1.number_input("Min Salary (₹)", min_value=0, step=10000, value=0)
        salary_max = c2.number_input("Max Salary (₹)", min_value=0, step=10000, value=0)
        openings   = c3.number_input("Openings", min_value=1, step=1, value=1)
        deadline   = c4.date_input("Application Deadline", value=None)

        # ── Row 4: Posted By + Status ─────────────────────────────────────
        c1, c2 = st.columns(2)
        posted_by = c1.text_input("Posted By (Recruiter Name)", placeholder="e.g. Priya Sharma")
        status    = c2.selectbox("Status", JOB_STATUSES)

        st.divider()

        # ── Text areas ────────────────────────────────────────────────────
        description      = st.text_area("Job Description *", height=130,
                                         placeholder="Describe the role, team, and company…")
        responsibilities = st.text_area("Key Responsibilities", height=110,
                                         placeholder="• Lead backend development\n• Mentor junior engineers…")
        requirements     = st.text_area("Requirements / Qualifications", height=110,
                                         placeholder="• B.Tech in CS or equivalent\n• 3+ years Python experience…")
        skills_required  = st.text_area("Skills Required", height=80,
                                         placeholder="Python, Django, REST APIs, PostgreSQL, Docker")
        certification    = st.text_area("Certification (Optional)", height=50,
                                         placeholder="e.g. AWS Certified Developer, PMP")
        benefits         = st.text_area("Benefits & Perks", height=80,
                                         placeholder="Health insurance, flexible hours, remote work…")

        submitted = st.form_submit_button("🚀 Post Job", type="primary", use_container_width=True)

    if submitted:
        data = {
            "job_title":        job_title.strip(),
            "department":       department,
            "location":         location.strip(),
            "job_type":         job_type,
            "experience_level": experience_level,
            "salary_min":       salary_min or None,
            "salary_max":       salary_max or None,
            "description":      description.strip(),
            "requirements":     requirements.strip(),
            "responsibilities": responsibilities.strip(),
            "skills_required":  skills_required.strip(),
            "certification":    certification.strip(),
            "benefits":         benefits.strip(),
            "status":           status,
            "openings":         openings,
            "posted_by":        posted_by.strip(),
            "deadline":         deadline,
            "recruiter_email":  st.session_state.get("recruiter_email", ""),
        }
        ok, msg, job_id = service.post_job(data)
        if ok:
            st.success(f"✅ {msg}")
            st.balloons()
        else:
            st.error(f"❌ {msg}")


# ── Manage Jobs ────────────────────────────────────────────────────────────

def _render_manage(service: JobService) -> None:
    recruiter_email = st.session_state.get("recruiter_email", "")
    jobs = service.get_all_jobs(recruiter_email)

    if not jobs:
        empty_state("No jobs posted yet — use the 'Post a Job' tab to get started.")
        return

    # ── Stats ──────────────────────────────────────────────────────────────
    total    = len(jobs)
    open_j   = sum(1 for j in jobs if j.get("status") == "Open")
    closed_j = sum(1 for j in jobs if j.get("status") == "Closed")
    draft_j  = sum(1 for j in jobs if j.get("status") == "Draft")

    stat_strip([
        ("Total Jobs",    str(total),    "💼"),
        ("Open",          str(open_j),   "🟢"),
        ("Closed",        str(closed_j), "🔴"),
        ("Draft",         str(draft_j),  "📝"),
    ])
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filters ────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([3, 2, 2])
    query      = c1.text_input("🔍 Search jobs", placeholder="Title, skill, department…")
    f_status   = c2.selectbox("Filter by Status", ["All"] + JOB_STATUSES)
    f_type     = c3.selectbox("Filter by Type",   ["All"] + JOB_TYPES)

    df = pd.DataFrame(jobs)
    if query:
        q = query.lower()
        mask = (
            df["job_title"].str.lower().str.contains(q, na=False)
            | df["department"].str.lower().str.contains(q, na=False)
            | df["skills_required"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]
    if f_status != "All":
        df = df[df["status"] == f_status]
    if f_type != "All":
        df = df[df["job_type"] == f_type]

    if df.empty:
        empty_state("No jobs match the current filters.")
        return

    st.caption(f"Showing **{len(df)}** of **{total}** job(s)")
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Job cards ──────────────────────────────────────────────────────────
    # Clear any stale session state keys left by previous implementations
    for key in list(st.session_state.keys()):
        if key.startswith("replace_clicked_"):
            del st.session_state[key]

    for row in df.to_dict("records"):
        _render_job_card(row, service)


def _render_job_card(j: dict, service: JobService) -> None:
    title      = html.escape(str(j.get("job_title") or "Untitled"))
    dept       = html.escape(str(j.get("department") or "—"))
    location   = html.escape(str(j.get("location") or "—"))
    job_type   = html.escape(str(j.get("job_type") or "—"))
    exp        = html.escape(str(j.get("experience_level") or "—"))
    status     = str(j.get("status") or "Open")
    openings   = j.get("openings") or 1
    posted_by  = html.escape(str(j.get("posted_by") or "—"))
    deadline   = str(j.get("deadline") or "—")
    skills     = html.escape(str(j.get("skills_required") or "—"))
    s_min      = j.get("salary_min")
    s_max      = j.get("salary_max")
    salary_str = (
        f"₹{int(s_min):,} – ₹{int(s_max):,}"
        if s_min and s_max else "Not disclosed"
    )
    color = _STATUS_COLOR.get(status, "#6b7280")
    job_id = j.get("job_id")

    # CSS: fix button widths, prevent text wrapping, compact layout
    st.markdown(
        """
        <style>
        /* Make all action buttons same compact width */
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] button {
            width: 100% !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding: 0.35rem 0.5rem !important;
            font-size: 0.78rem !important;
            min-height: 36px !important;
        }
        /* Prevent selectbox label from wrapping */
        div[data-testid="stSelectbox"] label {
            white-space: nowrap !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            f"""
            <div style="display:flex;justify-content:space-between;align-items:flex-start;
                        flex-wrap:wrap;gap:10px;margin-bottom:10px">
                <div>
                    <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9">{title}</div>
                    <div style="font-size:0.82rem;color:#94a3b8;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        🏢 {dept} &nbsp;·&nbsp; 📍 {location} &nbsp;·&nbsp;
                        ⏱ {job_type} &nbsp;·&nbsp; 🎯 {exp}
                    </div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <span style="background:{color};color:#fff;padding:4px 14px;
                                 border-radius:20px;font-size:0.75rem;font-weight:700;white-space:nowrap">
                        {html.escape(status)}
                    </span>
                    <span style="background:rgba(255,255,255,0.08);color:#cbd5e1;
                                 padding:4px 12px;border-radius:20px;font-size:0.75rem;white-space:nowrap">
                        👥 {openings} opening(s)
                    </span>
                </div>
            </div>
            <div style="display:flex;gap:24px;flex-wrap:wrap;font-size:0.8rem;
                        color:#64748b;margin-bottom:8px">
                <span style="white-space:nowrap">💰 {html.escape(salary_str)}</span>
                <span style="white-space:nowrap">📅 Deadline: {html.escape(deadline)}</span>
                <span style="white-space:nowrap">👤 Posted by: {posted_by}</span>
            </div>
            <div style="font-size:0.78rem;color:#475569">
                🛠 <b>Skills:</b> {skills}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Single row: View | Edit | Status dropdown | Delete | Replace
        col_view, col_edit, col_status, col_del, col_replace = st.columns([1, 1, 2, 0.6, 1])

        with col_view:
            if st.button("👁 View", key=f"view_{job_id}", use_container_width=True):
                st.session_state[f"expand_{job_id}"] = not st.session_state.get(f"expand_{job_id}", False)

        with col_edit:
            if st.button("✏️ Edit", key=f"edit_{job_id}", use_container_width=True):
                st.session_state[f"edit_form_{job_id}"] = not st.session_state.get(f"edit_form_{job_id}", False)
                st.session_state[f"replace_form_{job_id}"] = False

        with col_status:
            new_status = st.selectbox(
                "Change status",
                JOB_STATUSES,
                index=JOB_STATUSES.index(status) if status in JOB_STATUSES else 0,
                key=f"status_{job_id}",
                label_visibility="collapsed",
            )
            if new_status != status:
                ok, msg = service.update_status(job_id, new_status)
                st.toast(msg) if ok else st.error(msg)
                st.rerun()

        with col_del:
            if st.button("🗑️", key=f"del_{job_id}", use_container_width=True):
                ok, msg = service.delete_job(job_id)
                st.toast(msg) if ok else st.error(msg)
                st.rerun()

        with col_replace:
            if st.button("♻️ Replace", key=f"replace_{job_id}", use_container_width=True):
                st.session_state[f"replace_form_{job_id}"] = not st.session_state.get(f"replace_form_{job_id}", False)
                st.session_state[f"edit_form_{job_id}"] = False

    # Render expand/edit/replace panels OUTSIDE the container to avoid layout issues
    if st.session_state.get(f"expand_{job_id}"):
        _render_job_detail(j)

    if st.session_state.get(f"edit_form_{job_id}"):
        _render_edit_form(j, service, replace_mode=False)

    if st.session_state.get(f"replace_form_{job_id}"):
        _render_edit_form(j, service, replace_mode=True)


def _render_job_detail(j: dict) -> None:
    st.divider()
    t1, t2, t3, t4 = st.tabs(
        ["📄 Description", "✅ Requirements", "🎯 Responsibilities", "🎁 Benefits"]
    )
    with t1:
        st.write(j.get("description") or "—")
    with t2:
        st.write(j.get("requirements") or "—")
    with t3:
        st.write(j.get("responsibilities") or "—")
    with t4:
        st.write(j.get("benefits") or "—")


def _render_edit_form(j: dict, service: JobService, replace_mode: bool = False) -> None:
    """Renders an inline form to update or fully replace an existing job."""
    st.divider()
    if replace_mode:
        st.markdown("##### ♻️ Replace Job — all fields will be overwritten")
    else:
        st.markdown("##### ✏️ Edit Job Details")

    job_id = j.get("job_id")

    with st.form(f"edit_job_{job_id}"):
        c1, c2 = st.columns(2)
        job_title = c1.text_input("Job Title *", value=j.get("job_title", ""))
        department = c2.selectbox("Department", DEPARTMENTS, index=DEPARTMENTS.index(j["department"]) if j.get("department") in DEPARTMENTS else 0)

        c1, c2, c3 = st.columns(3)
        location = c1.text_input("Location", value=j.get("location", ""))
        job_type = c2.selectbox("Job Type", JOB_TYPES, index=JOB_TYPES.index(j["job_type"]) if j.get("job_type") in JOB_TYPES else 0)
        experience_level = c3.selectbox("Experience Level", EXP_LEVELS, index=EXP_LEVELS.index(j["experience_level"]) if j.get("experience_level") in EXP_LEVELS else 0)

        c1, c2, c3, c4 = st.columns(4)
        salary_min = c1.number_input("Min Salary (₹)", min_value=0, step=10000, value=int(j.get("salary_min", 0) or 0))
        salary_max = c2.number_input("Max Salary (₹)", min_value=0, step=10000, value=int(j.get("salary_max", 0) or 0))
        openings = c3.number_input("Openings", min_value=1, step=1, value=j.get("openings", 1))
        deadline_val = j.get("deadline")
        deadline = c4.date_input("Application Deadline", value=deadline_val if isinstance(deadline_val, date) else None)

        c1, c2 = st.columns(2)
        posted_by = c1.text_input("Posted By", value=j.get("posted_by", ""))
        status = c2.selectbox("Status", JOB_STATUSES, index=JOB_STATUSES.index(j["status"]) if j.get("status") in JOB_STATUSES else 0)

        st.divider()
        description = st.text_area("Job Description", value=j.get("description", ""), height=130)
        responsibilities = st.text_area("Key Responsibilities", value=j.get("responsibilities", ""), height=110)
        requirements = st.text_area("Requirements", value=j.get("requirements", ""), height=110)
        skills_required = st.text_area("Skills Required", value=j.get("skills_required", ""), height=80)
        certification = st.text_area("Certification (Optional)", value=j.get("certification", ""), height=50)
        benefits = st.text_area("Benefits & Perks", value=j.get("benefits", ""), height=80)

        if replace_mode:
            button_label = "♻️ Replace Job"
        else:
            button_label = "💾 Save Changes"
        submitted = st.form_submit_button(button_label, type="primary", use_container_width=True)

    if submitted:
        # Helper to compare values safely, accounting for type differences (e.g., int vs Decimal)
        def _is_changed(key: str, new_value: object) -> bool:
            old_value = j.get(key)
            if old_value is None and new_value is None:
                return False
            # Handle date comparison separately, as old_value might be a string
            if key == 'deadline':
                old_date = pd.to_datetime(old_value).date() if old_value else None
                return new_value != old_date
            if isinstance(new_value, (int, float)) and old_value is not None:
                # Compare numeric values without type mismatch issues
                return float(new_value) != float(old_value)
            if isinstance(new_value, date) and old_value is not None:
                return new_value != old_value
            # Default to string comparison for everything else
            return str(new_value) != str(old_value)

        updated_data = {
            "job_title": job_title.strip(),
            "department": department,
            "location": location.strip(),
            "job_type": job_type,
            "experience_level": experience_level,
            "salary_min": salary_min or None,
            "salary_max": salary_max or None,
            "description": description.strip(),
            "requirements": requirements.strip(),
            "responsibilities": responsibilities.strip(),
            "skills_required": skills_required.strip(),
            "certification": certification.strip(),
            "benefits": benefits.strip(),
            "status": status,
            "openings": openings,
            "posted_by": posted_by.strip(),
            "deadline": deadline,
        }

        # Filter out any fields that haven't changed
        changed_data = {k: v for k, v in updated_data.items() if _is_changed(k, v)}

        if replace_mode:
            # REPLACE INTO: send full payload — old row is deleted and re-inserted
            ok, msg = service.replace_job(job_id, updated_data)
            if ok:
                st.success(f"✅ {msg}")
                st.session_state[f"replace_form_{job_id}"] = False
                st.rerun()
            else:
                st.error(f"❌ {msg}")
        else:
            # For update, we only send changed fields
            if not changed_data:
                st.toast("No changes detected.")
            else:
                ok, msg = service.update_job(job_id, changed_data)
                if ok:
                    st.success(f"✅ {msg}")
                    st.session_state[f"edit_form_{job_id}"] = False
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
