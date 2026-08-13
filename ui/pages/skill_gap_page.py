"""Skill Gap Analysis page — detailed skill gap with learning recommendations."""

import html
import streamlit as st

from reports.report_generator import skill_gap_csv, skill_gap_pdf

from services.candidate_service import CandidateService
from ui.components import empty_state, page_header


# ══════════════════════════════════════════════
#  SKILL RECOMMENDATIONS DATABASE
# ══════════════════════════════════════════════

_RECOMMENDATIONS: dict[str, dict] = {
    # Cloud
    "aws":            {"course": "AWS Cloud Practitioner",          "platform": "AWS Training",    "level": "Beginner",      "link": "https://aws.amazon.com/training/", "icon": "☁️"},
    "azure":          {"course": "Azure Fundamentals AZ-900",       "platform": "Microsoft Learn", "level": "Beginner",      "link": "https://learn.microsoft.com/",     "icon": "☁️"},
    "gcp":            {"course": "Google Cloud Fundamentals",       "platform": "Google Cloud",   "level": "Beginner",      "link": "https://cloud.google.com/training","icon": "☁️"},
    # DevOps
    "docker":         {"course": "Docker Fundamentals",             "platform": "Docker Docs",    "level": "Beginner",      "link": "https://docs.docker.com/",         "icon": "🐳"},
    "kubernetes":     {"course": "Kubernetes Basics",               "platform": "Kubernetes.io",  "level": "Intermediate",  "link": "https://kubernetes.io/docs/",      "icon": "⚙️"},
    "terraform":      {"course": "Terraform Getting Started",       "platform": "HashiCorp",      "level": "Intermediate",  "link": "https://developer.hashicorp.com/", "icon": "🏗️"},
    "ansible":        {"course": "Ansible for Beginners",           "platform": "Red Hat",        "level": "Beginner",      "link": "https://www.ansible.com/",         "icon": "🔧"},
    "jenkins":        {"course": "Jenkins CI/CD Pipeline",          "platform": "Jenkins Docs",   "level": "Intermediate",  "link": "https://www.jenkins.io/doc/",      "icon": "🔄"},
    "ci/cd":          {"course": "CI/CD Pipeline Fundamentals",     "platform": "GitLab Learn",   "level": "Intermediate",  "link": "https://about.gitlab.com/",        "icon": "🔄"},
    "github actions": {"course": "GitHub Actions Quickstart",       "platform": "GitHub Docs",    "level": "Beginner",      "link": "https://docs.github.com/actions",  "icon": "🐙"},
    # Languages
    "python":         {"course": "Python for Everybody",            "platform": "Coursera",       "level": "Beginner",      "link": "https://www.coursera.org/",        "icon": "🐍"},
    "java":           {"course": "Java Programming Masterclass",    "platform": "Udemy",          "level": "Beginner",      "link": "https://www.udemy.com/",           "icon": "☕"},
    "javascript":     {"course": "JavaScript: The Complete Guide",  "platform": "Udemy",          "level": "Beginner",      "link": "https://www.udemy.com/",           "icon": "🟨"},
    "typescript":     {"course": "TypeScript Fundamentals",         "platform": "Pluralsight",    "level": "Intermediate",  "link": "https://www.pluralsight.com/",     "icon": "🔷"},
    "go":             {"course": "Go Programming Language",         "platform": "Tour of Go",     "level": "Intermediate",  "link": "https://go.dev/tour/",             "icon": "🐹"},
    "rust":           {"course": "The Rust Programming Language",   "platform": "Rust Book",      "level": "Advanced",      "link": "https://doc.rust-lang.org/book/",  "icon": "🦀"},
    # Web
    "react":          {"course": "React - The Complete Guide",      "platform": "Udemy",          "level": "Intermediate",  "link": "https://www.udemy.com/",           "icon": "⚛️"},
    "angular":        {"course": "Angular - The Complete Guide",    "platform": "Udemy",          "level": "Intermediate",  "link": "https://www.udemy.com/",           "icon": "🅰️"},
    "vue":            {"course": "Vue.js Essentials",               "platform": "Vue Mastery",    "level": "Beginner",      "link": "https://www.vuemastery.com/",      "icon": "💚"},
    "node.js":        {"course": "Node.js Complete Course",         "platform": "Udemy",          "level": "Intermediate",  "link": "https://www.udemy.com/",           "icon": "🟩"},
    "django":         {"course": "Django for Beginners",            "platform": "Django Docs",    "level": "Intermediate",  "link": "https://docs.djangoproject.com/",  "icon": "🎸"},
    "flask":          {"course": "Flask Web Development",           "platform": "Flask Docs",     "level": "Beginner",      "link": "https://flask.palletsprojects.com/","icon": "🌶️"},
    "fastapi":        {"course": "FastAPI Tutorial",                "platform": "FastAPI Docs",   "level": "Intermediate",  "link": "https://fastapi.tiangolo.com/",    "icon": "⚡"},
    # Data / ML
    "sql":            {"course": "SQL for Data Analysis",           "platform": "Mode Analytics", "level": "Beginner",      "link": "https://mode.com/sql-tutorial/",   "icon": "🗄️"},
    "postgresql":     {"course": "PostgreSQL Tutorial",             "platform": "PostgreSQL.org", "level": "Beginner",      "link": "https://www.postgresql.org/docs/", "icon": "🐘"},
    "mongodb":        {"course": "MongoDB Basics",                  "platform": "MongoDB Univ.",  "level": "Beginner",      "link": "https://university.mongodb.com/",  "icon": "🍃"},
    "pandas":         {"course": "Pandas for Data Analysis",        "platform": "Kaggle",         "level": "Beginner",      "link": "https://www.kaggle.com/learn/",    "icon": "🐼"},
    "numpy":          {"course": "NumPy Fundamentals",              "platform": "NumPy Docs",     "level": "Beginner",      "link": "https://numpy.org/learn/",         "icon": "🔢"},
    "tensorflow":     {"course": "TensorFlow Developer Certificate","platform": "Google",         "level": "Advanced",      "link": "https://www.tensorflow.org/learn", "icon": "🧠"},
    "pytorch":        {"course": "PyTorch Deep Learning",           "platform": "fast.ai",        "level": "Advanced",      "link": "https://www.fast.ai/",             "icon": "🔥"},
    "scikit-learn":   {"course": "Scikit-learn ML Course",          "platform": "Kaggle",         "level": "Intermediate",  "link": "https://www.kaggle.com/learn/",    "icon": "🤖"},
    "spark":          {"course": "Apache Spark Fundamentals",       "platform": "Databricks",     "level": "Advanced",      "link": "https://www.databricks.com/",      "icon": "✨"},
    # Tools
    "git":            {"course": "Git & GitHub Crash Course",       "platform": "freeCodeCamp",   "level": "Beginner",      "link": "https://www.freecodecamp.org/",    "icon": "📦"},
    "linux":          {"course": "Linux Command Line Basics",       "platform": "edX",            "level": "Beginner",      "link": "https://www.edx.org/",             "icon": "🐧"},
    "tableau":        {"course": "Tableau Desktop Specialist",      "platform": "Tableau",        "level": "Intermediate",  "link": "https://www.tableau.com/learn/",   "icon": "📊"},
    "power bi":       {"course": "Power BI Data Analyst",           "platform": "Microsoft Learn","level": "Intermediate",  "link": "https://learn.microsoft.com/",     "icon": "📈"},
    "redis":          {"course": "Redis University",                "platform": "Redis",          "level": "Intermediate",  "link": "https://university.redis.com/",    "icon": "🔴"},
    "elasticsearch":  {"course": "Elasticsearch Fundamentals",      "platform": "Elastic",        "level": "Intermediate",  "link": "https://www.elastic.co/training/", "icon": "🔍"},
    "kafka":          {"course": "Apache Kafka Fundamentals",       "platform": "Confluent",      "level": "Advanced",      "link": "https://developer.confluent.io/",  "icon": "📨"},
    "graphql":        {"course": "GraphQL Full Course",             "platform": "freeCodeCamp",   "level": "Intermediate",  "link": "https://www.freecodecamp.org/",    "icon": "🔗"},
    "rest":           {"course": "REST API Design",                 "platform": "Postman",        "level": "Beginner",      "link": "https://learning.postman.com/",    "icon": "🌐"},
    "agile":          {"course": "Agile Fundamentals",              "platform": "Scrum.org",      "level": "Beginner",      "link": "https://www.scrum.org/",           "icon": "🔁"},
    "scrum":          {"course": "Professional Scrum Master",       "platform": "Scrum.org",      "level": "Beginner",      "link": "https://www.scrum.org/",           "icon": "🏃"},
}

_LEVEL_COLOR = {
    "Beginner":     ("#10b981", "rgba(16,185,129,0.15)"),
    "Intermediate": ("#f59e0b", "rgba(245,158,11,0.15)"),
    "Advanced":     ("#ef4444", "rgba(239,68,68,0.15)"),
}

_DEFAULT_REC = {
    "course": "Search on Udemy / Coursera",
    "platform": "Online Learning",
    "level": "Beginner",
    "link": "https://www.udemy.com/",
    "icon": "📚",
}


# ══════════════════════════════════════════════
#  SKILL LOGIC
# ══════════════════════════════════════════════

def _normalize(raw: str) -> set[str]:
    return {s.strip().lower() for s in (raw or "").split(",") if s.strip()}


def _analyze(candidate_skills: str, job_skills: str) -> dict:
    resume  = _normalize(candidate_skills)
    jd      = _normalize(job_skills)
    matched = sorted(resume & jd)
    missing = sorted(jd - resume)
    extra   = sorted(resume - jd)
    total   = len(jd) or 1
    gap_pct = round((len(missing) / total) * 100, 1)
    match_pct = round((len(matched) / total) * 100, 1)
    return {
        "matched":   matched,
        "missing":   missing,
        "extra":     extra,
        "gap_pct":   gap_pct,
        "match_pct": match_pct,
        "total_jd":  len(jd),
        "total_resume": len(resume),
    }


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════

def _pills(skills: list[str], bg: str, border: str, color: str) -> None:
    if not skills:
        st.caption("None")
        return
    badges = "".join(
        f'<span style="background:{bg};color:{color};border:1px solid {border};'
        f'padding:5px 14px;border-radius:20px;font-size:0.78rem;font-weight:600;'
        f'margin:3px;display:inline-block;letter-spacing:0.01em">'
        f'{html.escape(s)}</span>'
        for s in skills
    )
    st.markdown(f'<div style="line-height:2.6">{badges}</div>', unsafe_allow_html=True)


def _gap_bar(gap_pct: float, match_pct: float) -> None:
    """Visual stacked progress bar — green matched, red gap."""
    st.markdown(
        f"""
        <div style="margin:16px 0 8px">
            <div style="display:flex;justify-content:space-between;
                        font-size:0.72rem;font-weight:600;margin-bottom:6px">
                <span style="color:#10b981">✅ Matched {match_pct}%</span>
                <span style="color:#ef4444">❌ Gap {gap_pct}%</span>
            </div>
            <div style="background:rgba(255,255,255,0.08);border-radius:20px;
                        height:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.06)">
                <div style="display:flex;height:100%">
                    <div style="width:{match_pct}%;background:linear-gradient(90deg,#10b981,#34d399);
                                border-radius:20px 0 0 20px;transition:width 0.5s"></div>
                    <div style="width:{gap_pct}%;background:linear-gradient(90deg,#ef4444,#f87171);
                                border-radius:0 20px 20px 0"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _recommendation_card(skill: str) -> None:
    """Expandable recommendation card for a single missing skill."""
    rec   = _RECOMMENDATIONS.get(skill.lower(), _DEFAULT_REC)
    clr, bg = _LEVEL_COLOR.get(rec["level"], ("#94a3b8", "rgba(148,163,184,0.1)"))

    with st.expander(f"{rec['icon']}  **{skill.title()}**  →  {rec['course']}", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("📚 Course",   rec["course"][:30] + "…" if len(rec["course"]) > 30 else rec["course"])
        c2.metric("🌐 Platform", rec["platform"])
        c3.metric("📊 Level",    rec["level"])

        st.markdown(
            f"""
            <div style="background:{bg};border-radius:12px;padding:14px 18px;
                        border:1px solid {clr}30;margin-top:8px;
                        display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div style="font-size:0.72rem;color:#94a3b8;font-weight:600;
                                text-transform:uppercase;letter-spacing:0.08em">
                        Recommended Resource</div>
                    <div style="font-size:0.88rem;color:#f1f5f9;font-weight:600;
                                margin-top:4px">{rec['course']}</div>
                    <div style="font-size:0.75rem;color:{clr};margin-top:3px">
                        {rec['platform']} · {rec['level']}</div>
                </div>
                <a href="{rec['link']}" target="_blank"
                   style="background:linear-gradient(135deg,#7c3aed,#2563eb);
                          color:#fff;padding:8px 18px;border-radius:10px;
                          font-size:0.78rem;font-weight:700;text-decoration:none;
                          white-space:nowrap;flex-shrink:0">
                    Learn Now →
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════
#  MAIN RENDER
# ══════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "🔍 Skill Gap Analysis",
        "Identify missing skills and get personalized learning recommendations.",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    # ── Selection ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;"
            "margin-bottom:12px'>Select Candidate & Job</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            job_options = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
            sel_job_key = st.selectbox("💼 Job Description",
                                       list(job_options.keys()), key="gap_job")
            sel_job = job_options[sel_job_key]
        with col2:
            cand_options = {
                f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                for c in candidates
            }
            sel_cand_key = st.selectbox("👤 Candidate",
                                        list(cand_options.keys()), key="gap_cand")
            sel_cand = cand_options[sel_cand_key]

        run = st.button("🔍 Analyze Skill Gap", type="primary", use_container_width=True)

    if not run and "gap_result" not in st.session_state:
        st.info("👆 Select a Job and Candidate above, then click **Analyze Skill Gap**.")
        return

    if run:
        analysis = _analyze(
            sel_cand.get("skills", ""),
            sel_job.get("skills_required", "")
        )
        st.session_state.gap_result = {
            "job":      sel_job,
            "candidate": sel_cand,
            "analysis": analysis,
        }

    res      = st.session_state.gap_result
    job      = res["job"]
    cand     = res["candidate"]
    a        = res["analysis"]
    name     = (cand.get("name") or "Unknown").splitlines()[0]
    job_title = job.get("job_title") or "—"

    st.divider()

    # ── Who vs What header ─────────────────────────────────────────────────
    col_c, col_vs, col_j = st.columns([5, 1, 5])
    with col_c:
        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),"
            f"rgba(37,99,235,0.1));border-radius:16px;padding:16px 20px;"
            f"border:1px solid rgba(124,58,237,0.2)'>"
            f"<div style='font-size:0.68rem;color:#94a3b8;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:0.08em'>Candidate</div>"
            f"<div style='font-size:1rem;font-weight:800;color:#f1f5f9;margin-top:4px'>"
            f"{html.escape(name)}</div>"
            f"<div style='font-size:0.75rem;color:#94a3b8;margin-top:2px'>"
            f"🛠 {a['total_resume']} skills in resume</div></div>",
            unsafe_allow_html=True,
        )
    with col_vs:
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:center;"
            "height:100%;font-size:1.5rem;padding-top:16px'>🔍</div>",
            unsafe_allow_html=True,
        )
    with col_j:
        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba(37,99,235,0.15),"
            f"rgba(6,182,212,0.1));border-radius:16px;padding:16px 20px;"
            f"border:1px solid rgba(37,99,235,0.2)'>"
            f"<div style='font-size:0.68rem;color:#94a3b8;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:0.08em'>Job Description</div>"
            f"<div style='font-size:1rem;font-weight:800;color:#f1f5f9;margin-top:4px'>"
            f"{html.escape(job_title)}</div>"
            f"<div style='font-size:0.75rem;color:#94a3b8;margin-top:2px'>"
            f"📋 {a['total_jd']} skills required</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 4 metrics ──────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ Matched Skills",    len(a["matched"]))
    m2.metric("❌ Missing Skills",    len(a["missing"]))
    m3.metric("➕ Additional Skills", len(a["extra"]))
    m4.metric("📉 Skill Gap %",       f"{a['gap_pct']}%")

    # ── Gap bar ────────────────────────────────────────────────────────────
    _gap_bar(a["gap_pct"], a["match_pct"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 3 skill containers ─────────────────────────────────────────────────
    col_a, col_b, col_c2 = st.columns(3)

    with col_a:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:0.72rem;font-weight:700;color:#10b981;"
                f"text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px'>"
                f"✅ Matched Skills ({len(a['matched'])})</div>",
                unsafe_allow_html=True,
            )
            _pills(a["matched"],
                   "rgba(16,185,129,0.15)", "rgba(16,185,129,0.4)", "#6ee7b7")

    with col_b:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:0.72rem;font-weight:700;color:#ef4444;"
                f"text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px'>"
                f"❌ Missing Skills ({len(a['missing'])})</div>",
                unsafe_allow_html=True,
            )
            _pills(a["missing"],
                   "rgba(239,68,68,0.15)", "rgba(239,68,68,0.4)", "#fca5a5")

    with col_c2:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:0.72rem;font-weight:700;color:#60a5fa;"
                f"text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px'>"
                f"➕ Additional Skills ({len(a['extra'])})</div>",
                unsafe_allow_html=True,
            )
            _pills(a["extra"],
                   "rgba(59,130,246,0.15)", "rgba(59,130,246,0.4)", "#93c5fd")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Learning recommendations ───────────────────────────────────────────
    if a["missing"]:
        st.markdown(
            f"<div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;"
            f"margin-bottom:4px'>📚 Learning Recommendations</div>"
            f"<div style='font-size:0.78rem;color:#64748b;margin-bottom:16px'>"
            f"Click each skill to see the recommended course</div>",
            unsafe_allow_html=True,
        )

        # Group by level
        beginner     = [s for s in a["missing"] if _RECOMMENDATIONS.get(s, _DEFAULT_REC)["level"] == "Beginner"]
        intermediate = [s for s in a["missing"] if _RECOMMENDATIONS.get(s, _DEFAULT_REC)["level"] == "Intermediate"]
        advanced     = [s for s in a["missing"] if _RECOMMENDATIONS.get(s, _DEFAULT_REC)["level"] == "Advanced"]
        unknown      = [s for s in a["missing"] if s not in _RECOMMENDATIONS]

        if beginner:
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#10b981;"
                "text-transform:uppercase;letter-spacing:0.08em;"
                "margin:12px 0 8px'>🟢 Beginner Level</div>",
                unsafe_allow_html=True,
            )
            for skill in beginner:
                _recommendation_card(skill)

        if intermediate:
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#f59e0b;"
                "text-transform:uppercase;letter-spacing:0.08em;"
                "margin:12px 0 8px'>🟡 Intermediate Level</div>",
                unsafe_allow_html=True,
            )
            for skill in intermediate:
                _recommendation_card(skill)

        if advanced:
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#ef4444;"
                "text-transform:uppercase;letter-spacing:0.08em;"
                "margin:12px 0 8px'>🔴 Advanced Level</div>",
                unsafe_allow_html=True,
            )
            for skill in advanced:
                _recommendation_card(skill)

        if unknown:
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:700;color:#94a3b8;"
                "text-transform:uppercase;letter-spacing:0.08em;"
                "margin:12px 0 8px'>📌 Other Skills</div>",
                unsafe_allow_html=True,
            )
            for skill in unknown:
                _recommendation_card(skill)

    else:
        st.success("🎉 No skill gaps found! This candidate has all required skills.")

    st.divider()

    # ── Summary box ────────────────────────────────────────────────────────
    if a["gap_pct"] == 0:
        gap_clr, gap_msg = "#10b981", "✅ No skill gap — perfect match!"
    elif a["gap_pct"] <= 30:
        gap_clr, gap_msg = "#f59e0b", "🟡 Small gap — a few skills to learn."
    elif a["gap_pct"] <= 60:
        gap_clr, gap_msg = "#fb923c", "🟠 Moderate gap — upskilling needed."
    else:
        gap_clr, gap_msg = "#ef4444", "🔴 Large gap — significant training required."

    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,0.04);border-radius:16px;
                    padding:20px 24px;border:1px solid {gap_clr}40;text-align:center">
            <div style="font-size:1.05rem;font-weight:800;color:{gap_clr}">{gap_msg}</div>
            <div style="font-size:0.82rem;color:#94a3b8;margin-top:6px">
                <b style="color:#f1f5f9">{html.escape(name)}</b> has
                <b style="color:#10b981">{len(a['matched'])}</b> of
                <b style="color:#f1f5f9">{a['total_jd']}</b> required skills ·
                <b style="color:#ef4444">{len(a['missing'])}</b> skills to learn ·
                Skill Gap: <b style="color:{gap_clr}">{a['gap_pct']}%</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Download Reports ───────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px'>"
            "📥 Download Report</div>",
            unsafe_allow_html=True,
        )
        cand_name = (cand.get("name") or "candidate").split()[0].lower()
        job_slug  = (job.get("job_title") or "job").replace(" ", "_").lower()
        stem      = f"skill_gap_{cand_name}_{job_slug}"

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                label="⬇️ Download CSV",
                data=skill_gap_csv(res),
                file_name=f"{stem}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                label="⬇️ Download PDF",
                data=skill_gap_pdf(res),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
