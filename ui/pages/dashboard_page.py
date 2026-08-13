"""Candidate Dashboard page."""

from __future__ import annotations

import html
import pandas as pd
import streamlit as st

from services.candidate_service import CandidateService
from ui.components import (
    candidate_card,
    empty_state,
    info_row,
    page_header,
    section_title,
    skill_badges,
    stat_strip,
)

_SORT_OPTIONS: dict[str, str] = {
    "Newest first":  "created_date",
    "Oldest first":  "created_date",
    "Name (A → Z)":  "name",
    "Name (Z → A)":  "name",
    "Most skills":   "skill_count",
}


# ── DataFrame helpers ──────────────────────────────────────────────────────

def _to_df(candidates: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candidates)
    if df.empty:
        return df
    df["skill_count"] = df["skills"].fillna("").apply(
        lambda s: len([x for x in s.split(",") if x.strip()])
    )
    df["edu_first"] = df["education"].fillna("").apply(
        lambda s: s.splitlines()[0] if s.strip() else ""
    )
    df["exp_first"] = df["experience"].fillna("").apply(
        lambda s: s.splitlines()[0] if s.strip() else ""
    )
    df["name"]  = df["name"].fillna("Unknown")
    df["email"] = df["email"].fillna("—")
    df["phone"] = df["phone"].fillna("—")
    return df


def _all_skills(df: pd.DataFrame) -> list[str]:
    skills: set[str] = set()
    for cell in df["skills"].dropna():
        skills.update(s.strip() for s in cell.split(",") if s.strip())
    return sorted(skills)


def _skill_counts(df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cell in df["skills"].dropna():
        for s in cell.split(","):
            s = s.strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _all_edu_keywords(df: pd.DataFrame) -> list[str]:
    keywords: set[str] = set()
    for cell in df["education"].dropna():
        for line in cell.splitlines():
            for word in line.split():
                if len(word) > 3:
                    keywords.add(word.strip(".,;:()").title())
    return sorted(keywords)


def _all_exp_keywords(df: pd.DataFrame) -> list[str]:
    keywords: set[str] = set()
    for cell in df["experience"].dropna():
        for line in cell.splitlines():
            if line.strip():
                keywords.add(line.strip()[:60])
    return sorted(keywords)[:60]


def _apply_filters(
    df: pd.DataFrame,
    query: str,
    skill_filter: list[str],
    edu_filter: list[str],
    exp_filter: list[str],
    sort_label: str,
) -> pd.DataFrame:
    if query:
        q = query.lower()
        mask = (
            df["name"].str.lower().str.contains(q, na=False)
            | df["email"].str.lower().str.contains(q, na=False)
            | df["skills"].str.lower().str.contains(q, na=False)
            | df["education"].str.lower().str.contains(q, na=False)
            | df["experience"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]
    for skill in skill_filter:
        df = df[df["skills"].str.lower().str.contains(skill.lower(), na=False)]
    for kw in edu_filter:
        df = df[df["education"].str.lower().str.contains(kw.lower(), na=False)]
    for kw in exp_filter:
        df = df[df["experience"].str.lower().str.contains(kw.lower(), na=False)]
    col = _SORT_OPTIONS.get(sort_label, "created_date")
    asc = "A →" in sort_label or sort_label == "Oldest first"
    if col == "skill_count":
        asc = False
    return df.sort_values(col, ascending=asc, ignore_index=True)


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header(
        "👥 Candidate Dashboard",
        "Browse, search, filter and manage all parsed candidate profiles.",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    if not candidates:
        empty_state("No candidates yet — upload a resume to get started.")
        return

    df_full = _to_df(candidates)

    total         = len(df_full)
    with_skills   = int((df_full["skill_count"] > 0).sum())
    avg_skills    = round(df_full["skill_count"].mean(), 1)
    unique_skills = len(_all_skills(df_full))

    stat_strip([
        ("Total Candidates",    str(total),         "👤"),
        ("With Skills",         str(with_skills),   "🛠️"),
        ("Avg Skills / Person", str(avg_skills),    "📊"),
        ("Unique Skills",       str(unique_skills), "🔖"),
    ])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Inline filters (below stat strip, above results) ──
    with st.expander("🔧 Filters & Sort", expanded=False):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            query = st.text_input("🔍 Search", placeholder="Name, email, skill…", key="dash_search")
        with col2:
            sort_label = st.selectbox("↕ Sort by", list(_SORT_OPTIONS.keys()), key="dash_sort")
        with col3:
            view_mode = st.radio("View", ["🃏 Cards", "📋 Table", "📈 Analytics"],
                                 key="dash_view", horizontal=False)

        col4, col5, col6 = st.columns(3)
        with col4:
            st.markdown("**Filter by Skill**")
            skill_filter = st.multiselect(
                "Skills", options=_all_skills(df_full),
                label_visibility="collapsed", key="dash_skills"
            )
        with col5:
            st.markdown("**Filter by Education**")
            edu_filter = st.multiselect(
                "Education", options=_all_edu_keywords(df_full),
                label_visibility="collapsed", key="dash_edu"
            )
        with col6:
            st.markdown("**Filter by Experience**")
            exp_filter = st.multiselect(
                "Experience", options=_all_exp_keywords(df_full),
                label_visibility="collapsed", key="dash_exp"
            )
        if st.button("🔄 Reset Filters", key="dash_reset"):
            st.rerun()

    df = _apply_filters(df_full, query, skill_filter, edu_filter, exp_filter, sort_label)

    if df.empty:
        empty_state("No candidates match the current filters.")
        return

    # ── Result count badge ──
    active_filters = len(skill_filter) + len(edu_filter) + len(exp_filter) + (1 if query else 0)
    filter_note = f" · {active_filters} filter(s) active" if active_filters else ""
    st.html(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
            <span style="background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.15));
                         border:1px solid rgba(124,58,237,0.25);
                         border-radius:20px;padding:6px 16px;
                         font-size:0.8rem;font-weight:600;color:#a78bfa;
                         backdrop-filter:blur(10px)">
                👤 Showing {len(df)} of {total} candidate(s){filter_note}
            </span>
        </div>
        """
    )

    if view_mode == "🃏 Cards":
        _render_cards(df, service)
    elif view_mode == "📋 Table":
        _render_table(df, service)
    else:
        _render_analytics(df_full)


# ── Card grid ──────────────────────────────────────────────────────────────

def _render_cards(df: pd.DataFrame, service: CandidateService) -> None:
    cols = st.columns(3, gap="medium")
    selected_id: int | None = None
    for i, row in enumerate(df.to_dict("records")):
        with cols[i % 3]:
            if candidate_card(row):
                selected_id = row.get("candidate_id")
    if selected_id:
        st.divider()
        _render_detail(service, selected_id)


# ── Table view ─────────────────────────────────────────────────────────────

def _render_table(df: pd.DataFrame, service: CandidateService) -> None:
    display = df[[
        "candidate_id", "name", "email", "phone",
        "edu_first", "exp_first", "skill_count", "skills",
    ]].rename(columns={
        "candidate_id": "ID",
        "name":         "Name",
        "email":        "Email",
        "phone":        "Phone",
        "edu_first":    "Education",
        "exp_first":    "Experience",
        "skill_count":  "# Skills",
        "skills":       "Skills",
    })

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID":         st.column_config.NumberColumn(width="small"),
            "# Skills":   st.column_config.NumberColumn(width="small"),
            "Skills":     st.column_config.TextColumn(width="large"),
            "Education":  st.column_config.TextColumn(width="medium"),
            "Experience": st.column_config.TextColumn(width="large"),
        },
    )

    st.divider()
    section_title("Candidate Detail")
    id_options  = df["candidate_id"].tolist()
    selected_id = st.selectbox(
        "Select candidate",
        options=id_options,
        format_func=lambda cid: (
            f"#{cid} — {df.loc[df['candidate_id'] == cid, 'name'].values[0]}"
        ),
    )
    if selected_id:
        _render_detail(service, int(selected_id))


# ── Analytics view ─────────────────────────────────────────────────────────

def _render_analytics(df: pd.DataFrame) -> None:
    section_title("📈 Skill Distribution")

    skill_counts = _skill_counts(df)
    if skill_counts:
        top_n = dict(list(skill_counts.items())[:15])
        chart_df = pd.DataFrame({
            "Skill": list(top_n.keys()),
            "Candidates": list(top_n.values()),
        })
        st.bar_chart(chart_df.set_index("Skill"), use_container_width=True, height=320)
    else:
        st.caption("No skill data available.")

    st.divider()
    section_title("📊 Skills per Candidate")

    skills_df = df[["name", "skill_count"]].rename(
        columns={"name": "Candidate", "skill_count": "Skills"}
    )
    st.bar_chart(skills_df.set_index("Candidate"), use_container_width=True, height=280)

    st.divider()
    section_title("🗂 Summary Table")

    summary = df[["name", "email", "skill_count", "edu_first"]].rename(columns={
        "name": "Name", "email": "Email",
        "skill_count": "Skills", "edu_first": "Education",
    })
    st.dataframe(summary, use_container_width=True, hide_index=True)


# ── Detail view ────────────────────────────────────────────────────────────

def _render_detail(service: CandidateService, candidate_id: int) -> None:
    c = service.get_candidate(candidate_id)
    if not c:
        st.error("Candidate not found.")
        return

    _render_detail_header(c)

    tab_info, tab_skills, tab_exp, tab_edu, tab_extra = st.tabs(
        ["📋 Info", "🛠 Skills", "💼 Experience", "🎓 Education", "📁 More"]
    )
    with tab_info:
        _render_tab_info(c)
    with tab_skills:
        _render_tab_skills(c)
    with tab_exp:
        _render_tab_lines(c.get("experience"), "No experience data.")
    with tab_edu:
        _render_tab_lines(c.get("education"), "No education data.")
    with tab_extra:
        _render_tab_extra(c)

    st.html("<div style='margin-top:12px'></div>")
    col_del, col_space = st.columns([1, 5])
    with col_del:
        if st.button("🗑️ Delete", type="secondary", key=f"del_{candidate_id}",
                     use_container_width=True):
            service.delete_candidate(candidate_id)
            st.success(f"Candidate #{candidate_id} deleted.")
            st.rerun()


def _render_detail_header(c: dict) -> None:
    raw_name = (c.get("name") or "Unknown").splitlines()[0].strip() or "Unknown"
    email    = c.get("email") or "—"
    phone    = c.get("phone") or "—"
    initials = "".join(w[0].upper() for w in raw_name.split()[:2]) or "?"
    skills   = [s.strip() for s in c.get("skills", "").split(",") if s.strip()]

    col_av, col_info, col_count = st.columns([1, 5, 2])
    with col_av:
        st.markdown(
            f'<div style="width:64px;height:64px;border-radius:18px;'
            f'background:linear-gradient(135deg,#7c3aed,#2563eb);'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-weight:900;font-size:1.4rem;margin-top:6px;'
            f'box-shadow:0 4px 20px rgba(124,58,237,0.5)">'
            f'{html.escape(initials)}</div>',
            unsafe_allow_html=True,
        )
    with col_info:
        st.markdown(f"### {raw_name}")
        st.caption(f"✉ {email}  ·  📞 {phone}")
    with col_count:
        st.metric("Skills", len(skills))


def _render_tab_info(c: dict) -> None:
    info_row("Candidate ID", str(c.get("candidate_id", "—")))
    info_row("Name",         c.get("name", ""))
    info_row("Email",        c.get("email", ""))
    info_row("Phone",        c.get("phone", ""))
    info_row("Resume File",  c.get("resume_path") or c.get("file_name", ""))
    info_row("Created",      str(c.get("created_date") or c.get("created_at", "")))
    info_row("Updated",      str(c.get("updated_date", "")))


def _render_tab_skills(c: dict) -> None:
    skills = [s.strip() for s in c.get("skills", "").split(",") if s.strip()]
    st.html(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;
                    padding:16px;background:linear-gradient(135deg,rgba(124,58,237,0.1),rgba(37,99,235,0.1));
                    border-radius:14px;border:1px solid rgba(124,58,237,0.2)">
            <div style="font-size:2rem;font-weight:900;
                        background:linear-gradient(135deg,#a78bfa,#60a5fa);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent">{len(skills)}</div>
            <div style="font-size:0.85rem;color:#94a3b8">skills detected</div>
        </div>
        """
    )
    skill_badges(skills, max_show=50)


def _render_tab_lines(field_value: str | None, empty_msg: str) -> None:
    lines = [ln.strip() for ln in (field_value or "").splitlines() if ln.strip()]
    if lines:
        for line in lines:
            st.html(
                f"""
                <div style="display:flex;gap:12px;padding:10px 0;
                            border-bottom:1px solid rgba(255,255,255,0.08);align-items:flex-start">
                    <div style="width:7px;height:7px;border-radius:50%;
                                background:linear-gradient(135deg,#8b5cf6,#3b82f6);
                                margin-top:7px;flex-shrink:0"></div>
                    <div style="font-size:0.88rem;color:#f1f5f9;line-height:1.7;font-weight:400">
                        {html.escape(line)}</div>
                </div>
                """
            )
    else:
        st.caption(empty_msg)


def _render_tab_extra(c: dict) -> None:
    projects = [ln.strip() for ln in (c.get("projects") or "").splitlines() if ln.strip()]
    certs    = [ln.strip() for ln in (c.get("certifications") or "").splitlines() if ln.strip()]

    if projects:
        st.html("<div style='font-size:0.72rem;font-weight:600;color:#64748b;letter-spacing:0.06em;margin-bottom:8px'>PROJECTS</div>")
        _render_tab_lines(c.get("projects"), "")
    if certs:
        st.html("<div style='font-size:0.72rem;font-weight:600;color:#64748b;letter-spacing:0.06em;margin:12px 0 8px'>CERTIFICATIONS</div>")
        _render_tab_lines(c.get("certifications"), "")
    if not projects and not certs:
        st.caption("No projects or certifications data.")
