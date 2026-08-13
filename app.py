"""AI Recruitment & Talent Management Copilot — Streamlit entry point."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import APP_ICON, APP_TITLE, LOG_PATH
from services.candidate_service import CandidateService
from ui.pages import dashboard_page, hiring_score_page, jobs_page, matching_page, ranking_page, recruiter_dashboard_page, settings_page, skill_gap_page, upload_page
from milestone3 import interview_questions, ats_dashboard, interview_scheduling, interview_simulator, interview_report, candidate_search, recruiter_feedback, candidate_timeline
from milestone4 import recruitment_analytics, voice_screening
from ui.pages import candidate_login_page, candidate_portal_page, login_page


def _configure_logging() -> None:
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


@st.cache_resource(ttl=0)
def _get_service() -> CandidateService:
    logging.getLogger(__name__).info("Initialising CandidateService")
    return CandidateService()


_PAGES = {
    "📋 Recruiter Dashboard": recruiter_dashboard_page,
    "📄 Upload Resume":       upload_page,
    "👥 Candidate Dashboard": dashboard_page,
    "💼 Job Postings":        jobs_page,
    "🎯 Candidate Matching":  matching_page,
    "🏆 Hiring Score":        hiring_score_page,
    "📊 Candidate Ranking":   ranking_page,
    "🔍 Skill Gap Analysis":  skill_gap_page,
    "⚙️ Settings":            settings_page,
    # ── Milestone 3 ──────────────────────────
    "❓ Interview Questions":  interview_questions,
    "🗂️ ATS Dashboard":        ats_dashboard,
    "📅 Interview Scheduling":  interview_scheduling,
    "🤖 AI Interview Simulator": interview_simulator,
    "📄 Interview Report":     interview_report,
    "🔎 Candidate Search":     candidate_search,
    "⭐ Recruiter Feedback":   recruiter_feedback,
    "🕐 Activity Timeline":    candidate_timeline,
    # ── Milestone 4 ──────────────────────────
    "📊 Recruitment Analytics": recruitment_analytics,
    "🎤 Voice Screening":        voice_screening,
}

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── Base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important;
    min-height: 100vh;
}
[data-testid="stMain"] { background: transparent !important; }
.main .block-container {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 24px !important;
    padding: 2.5rem 3rem 3rem !important;
    max-width: 1400px !important;
    backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    margin-top: 1rem !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #1a1650 !important;
    border-right: 1px solid rgba(139,92,246,0.3) !important;
    box-shadow: 4px 0 32px rgba(0,0,0,0.5) !important;
    transform: none !important;
    visibility: visible !important;
    display: block !important;
    width: 280px !important;
    min-width: 280px !important;
    max-width: 280px !important;
    left: 0 !important;
    position: relative !important;
}
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.1) !important; }
[data-testid="stSidebar"] .stRadio label {
    padding: 12px 16px !important;
    border-radius: 12px !important;
    transition: all 0.25s ease !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    margin-bottom: 3px !important;
    border: 1px solid transparent !important;
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(139,92,246,0.15) !important;
    border-color: rgba(139,92,246,0.3) !important;
}

/* ── Typography ── */
h1 { font-weight: 900 !important; letter-spacing: -1px !important; color: #ffffff !important; }
h2 { font-weight: 700 !important; color: #f1f5f9 !important; }
h3 { font-weight: 600 !important; color: #e2e8f0 !important; }
p, li, span { color: #cbd5e1 !important; }
.stCaption { color: #64748b !important; font-size: 0.82rem !important; }

/* ── Primary buttons ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7c3aed 0%, #2563eb 100%) !important;
    border: none !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    padding: 0.65rem 1.8rem !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.5) !important;
    letter-spacing: 0.02em !important;
    text-transform: uppercase !important;
    font-size: 0.78rem !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-3px) scale(1.02) !important;
    box-shadow: 0 10px 30px rgba(124,58,237,0.6) !important;
}

/* ── Secondary buttons ── */
.stButton > button[kind="secondary"] {
    border-radius: 12px !important;
    font-weight: 500 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    background: rgba(255,255,255,0.05) !important;
    color: #e2e8f0 !important;
    transition: all 0.2s !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: rgba(139,92,246,0.5) !important;
    background: rgba(139,92,246,0.1) !important;
    transform: translateY(-1px) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    background: rgba(255,255,255,0.05) !important;
    border-radius: 14px !important;
    padding: 5px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 8px 18px !important;
    color: #94a3b8 !important;
    transition: all 0.2s !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg,#7c3aed,#2563eb) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 12px rgba(124,58,237,0.4) !important;
}

/* ── Inputs ── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    font-size: 0.9rem !important;
    padding: 10px 14px !important;
    background: #1e1b3a !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    transition: all 0.2s !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.2) !important;
    background: #231f4a !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder { color: #64748b !important; }

/* ── Selectbox / Multiselect ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    background: #1e1b3a !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}
/* Selectbox dropdown options */
[data-baseweb="select"] input,
[data-baseweb="select"] [data-testid="stMarkdownContainer"] p {
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    border-radius: 20px !important;
    border: 2px dashed rgba(124,58,237,0.4) !important;
    background: rgba(124,58,237,0.05) !important;
    transition: all 0.3s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(124,58,237,0.8) !important;
    background: rgba(124,58,237,0.1) !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border-radius: 16px !important;
    overflow: hidden !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(255,255,255,0.03) !important;
    overflow: hidden !important;
}

/* ── Containers with border ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-radius: 20px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(255,255,255,0.04) !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.2) !important;
    padding: 20px !important;
    transition: all 0.3s !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: rgba(124,58,237,0.3) !important;
    box-shadow: 0 8px 32px rgba(124,58,237,0.15) !important;
    transform: translateY(-2px) !important;
}

/* ── Alerts ── */
[data-testid="stAlert"] {
    border-radius: 14px !important;
    font-size: 0.88rem !important;
    backdrop-filter: blur(10px) !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.05) !important;
    border-radius: 16px !important;
    padding: 20px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}
[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 800 !important; }
[data-testid="stMetricLabel"] { color: #94a3b8 !important; }

/* ── Divider ── */
hr { border-color: rgba(255,255,255,0.07) !important; margin: 1.5rem 0 !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: #7c3aed !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); border-radius: 10px; }
::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.4); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: rgba(124,58,237,0.7); }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }

/* ── Hide sidebar collapse arrow ── */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* ── Kill white top bar ── */
[data-testid="stHeader"] {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important;
    border-bottom: 1px solid rgba(124,58,237,0.2) !important;
}
[data-testid="stHeader"]::after {
    content: "🤖  TalentAI · AI Recruitment Copilot";
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    top: 50%;
    transform: translate(-50%, -50%);
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: rgba(139,92,246,0.7);
    text-transform: uppercase;
    pointer-events: none;
}
</style>
"""


_LIGHT_CSS = """
<style>
/* ── Backgrounds ── */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #f0f4ff 0%, #e8eaf6 50%, #f3e5f5 100%) !important;
}
[data-testid="stHeader"] {
    background: linear-gradient(135deg, #f0f4ff 0%, #e8eaf6 100%) !important;
    border-bottom: 1px solid rgba(124,58,237,0.15) !important;
}
[data-testid="stHeader"]::after { color: rgba(109,40,217,0.8) !important; }
.main .block-container {
    background: rgba(255,255,255,0.85) !important;
    border: 1px solid rgba(124,58,237,0.15) !important;
}
[data-testid="stSidebar"] {
    background: #ede9fe !important;
    border-right: 1px solid rgba(124,58,237,0.2) !important;
    box-shadow: 4px 0 24px rgba(124,58,237,0.1) !important;
}
[data-testid="stSidebar"] hr { border-color: rgba(124,58,237,0.2) !important; }
[data-testid="stSidebar"] .stRadio label { color: #1e1b4b !important; }

/* ── Force ALL text dark everywhere — catches inline style="color:#fff" etc. ── */
[data-testid="stMain"] *:not(button):not([class*="stButton"]),
[data-testid="stSidebar"] *:not(button):not([class*="stButton"]) {
    color: #1f2937 !important;
    -webkit-text-fill-color: #1f2937 !important;
}

/* ── Sidebar nav label stays dark indigo ── */
[data-testid="stSidebar"] .stRadio label {
    color: #1e1b4b !important;
    -webkit-text-fill-color: #1e1b4b !important;
}

/* ── Restore gradient text on headings ── */
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3 {
    color: #1e1b4b !important;
    -webkit-text-fill-color: #1e1b4b !important;
}

/* ── Keep primary button text white ── */
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* ── Keep skill badge text readable ── */
[data-testid="stMain"] span[style*="border-radius:20px"] {
    -webkit-text-fill-color: unset !important;
}

/* ── Inputs ── */
.stTextInput input { background: #ffffff !important; border: 1px solid rgba(124,58,237,0.3) !important; }
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div { background: #ffffff !important; border: 1px solid rgba(124,58,237,0.25) !important; }

/* ── Cards / containers ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: rgba(255,255,255,0.85) !important;
    border: 1px solid rgba(124,58,237,0.15) !important;
    box-shadow: 0 4px 16px rgba(124,58,237,0.08) !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: rgba(124,58,237,0.35) !important;
    box-shadow: 0 8px 24px rgba(124,58,237,0.15) !important;
}
[data-testid="stExpander"] { background: rgba(255,255,255,0.7) !important; border: 1px solid rgba(124,58,237,0.15) !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: rgba(124,58,237,0.08) !important; border: 1px solid rgba(124,58,237,0.15) !important; }
.stTabs [aria-selected="true"],
.stTabs [aria-selected="true"] * { color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }

/* ── Metrics ── */
[data-testid="stMetric"] { background: rgba(124,58,237,0.08) !important; border: 1px solid rgba(124,58,237,0.2) !important; }

/* ── Misc ── */
hr { border-color: rgba(124,58,237,0.15) !important; }
[data-testid="stFileUploader"] { border-color: rgba(124,58,237,0.35) !important; background: rgba(124,58,237,0.04) !important; }
</style>
"""


def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)

    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if "light_mode" not in st.session_state:
        st.session_state.light_mode = False

    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    if st.session_state.light_mode:
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)

    # ── Role gate ──────────────────────────────────────────────────────────
    role = st.session_state.get("role")  # None | "recruiter" | "candidate" | "candidate_login"

    if role is None:
        login_page.render()
        return

    if role == "candidate_login":
        login_page.render()
        return

    if role == "candidate":
        _render_candidate_shell()
        return

    # ── Recruiter / Admin shell ────────────────────────────────────────────
    # Migrate legacy rows to varianeha60100@gmail.com only (one-time, on their login)
    rec_email = st.session_state.get("recruiter_email", "")
    if rec_email == "varianeha60100@gmail.com" and not st.session_state.get("_pipeline_migrated"):
        try:
            import mysql.connector as _mc
            from config.settings import MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
            _conn = _mc.connect(
                host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
                user=MYSQL_USER, password=MYSQL_PASSWORD, autocommit=True,
            )
            _cur = _conn.cursor()
            for _tbl in ("candidates", "jobs", "ats_pipeline"):
                try:
                    _cur.execute(f"UPDATE {_tbl} SET recruiter_email = %s WHERE recruiter_email = ''", (rec_email,))
                except Exception:
                    pass
            _cur.close()
            _conn.close()
        except Exception:
            pass
        st.session_state["_pipeline_migrated"] = True

    service = _get_service()
    total   = len(service.get_all_candidates(rec_email))

    with st.sidebar:
        rec_name = st.session_state.get("recruiter_name", "Recruiter")
        st.html(
            f"""
            <div style="padding:28px 12px 16px">
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="width:48px;height:48px;border-radius:14px;
                                background:linear-gradient(135deg,#7c3aed,#2563eb);
                                display:flex;align-items:center;justify-content:center;
                                font-size:1.5rem;flex-shrink:0;
                                box-shadow:0 0 20px rgba(124,58,237,0.6)">🤖</div>
                    <div>
                        <div style="font-weight:900;font-size:1.1rem;color:#f8fafc;
                                    letter-spacing:-0.5px">TalentAI</div>
                        <div style="font-size:0.68rem;color:#a78bfa;margin-top:2px;
                                    font-weight:600;letter-spacing:0.04em">
                            👤 {rec_name}</div>
                    </div>
                </div>
            </div>
            """
        )
        st.divider()
        st.html(
            "<div style='font-size:0.65rem;font-weight:700;color:#4c1d95;"
            "letter-spacing:0.12em;padding:0 4px 10px;text-transform:uppercase'>Menu</div>"
        )

        _CORE_PAGES = [
            "📋 Recruiter Dashboard",
            "📄 Upload Resume",
            "👥 Candidate Dashboard",
            "💼 Job Postings",
            "🎯 Candidate Matching",
            "🏆 Hiring Score",
            "📊 Candidate Ranking",
            "🔍 Skill Gap Analysis",
            "⚙️ Settings",
        ]
        _M3_PAGES = [
            "❓ Interview Questions",
            "📌 ATS Management",
            "🎤 Interview Simulator",
            "📄 Interview Report",
        ]

        page_key = st.radio(
            "nav",
            options=list(_PAGES.keys()),
            label_visibility="collapsed",
        )

        st.divider()
        st.html(
            f"""
            <div style="background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.15));
                        border-radius:16px;padding:16px;
                        border:1px solid rgba(124,58,237,0.25);margin-bottom:8px">
                <div style="font-size:0.65rem;color:#7c3aed;font-weight:700;
                            letter-spacing:0.1em;margin-bottom:12px;text-transform:uppercase">
                    📊 Live Stats</div>
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div style="font-size:0.82rem;color:#94a3b8;font-weight:500">Candidates</div>
                    <div style="background:linear-gradient(135deg,#7c3aed,#2563eb);
                                color:#fff;font-weight:800;font-size:0.85rem;
                                padding:4px 14px;border-radius:20px;
                                box-shadow:0 2px 12px rgba(124,58,237,0.5)">{total}</div>
                </div>
            </div>
            """
        )
        st.divider()
        if st.button("🚪 Logout", use_container_width=True, key="recruiter_logout"):
            for k in ["role", "recruiter_name", "recruiter_email", "_pipeline_migrated"]:
                st.session_state.pop(k, None)
            st.rerun()


    logger.debug("Rendering page: %s", page_key)
    _PAGES[page_key].render(service.jobs if page_key == "💼 Job Postings" else service)


# ── Role selector (shown when no role is set) ──────────────────────────────

def _render_role_selector() -> None:
    st.html(
        """
        <div style="max-width:480px;margin:80px auto 0;text-align:center">
            <div style="font-size:3rem;margin-bottom:16px">🤖</div>
            <h1 style="font-size:2rem;font-weight:900;margin:0;
                       background:linear-gradient(135deg,#a78bfa,#60a5fa);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                TalentAI</h1>
            <p style="color:#94a3b8;font-size:0.95rem;margin-top:10px">
                AI Recruitment &amp; Talent Management Copilot</p>
        </div>
        """
    )
    st.markdown("<div style='max-width:480px;margin:32px auto 0'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        st.html(
            "<div style='background:rgba(124,58,237,0.1);border-radius:16px;padding:24px;"
            "border:1px solid rgba(124,58,237,0.3);text-align:center;margin-bottom:12px'>"
            "<div style='font-size:2rem'>🧑‍💼</div>"
            "<div style='font-weight:700;color:#e2e8f0;margin-top:8px'>Recruiter / Admin</div>"
            "<div style='font-size:0.78rem;color:#94a3b8;margin-top:4px'>Full platform access</div>"
            "</div>"
        )
        if st.button("Enter as Recruiter", type="primary", use_container_width=True, key="role_recruiter"):
            st.session_state.role = "recruiter"
            st.rerun()
    with col2:
        st.html(
            "<div style='background:rgba(37,99,235,0.1);border-radius:16px;padding:24px;"
            "border:1px solid rgba(37,99,235,0.3);text-align:center;margin-bottom:12px'>"
            "<div style='font-size:2rem'>🎓</div>"
            "<div style='font-weight:700;color:#e2e8f0;margin-top:8px'>Candidate</div>"
            "<div style='font-size:0.78rem;color:#94a3b8;margin-top:4px'>View your profile &amp; status</div>"
            "</div>"
        )
        if st.button("Candidate Login", type="primary", use_container_width=True, key="role_candidate"):
            st.session_state.role = "candidate_login"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ── Candidate shell ────────────────────────────────────────────────────────

def _render_candidate_shell() -> None:
    service = _get_service()
    with st.sidebar:
        st.html(
            """
            <div style="padding:28px 12px 16px">
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="width:48px;height:48px;border-radius:14px;
                                background:linear-gradient(135deg,#7c3aed,#2563eb);
                                display:flex;align-items:center;justify-content:center;
                                font-size:1.5rem;flex-shrink:0;
                                box-shadow:0 0 20px rgba(124,58,237,0.6)">🎓</div>
                    <div>
                        <div style="font-weight:900;font-size:1.1rem;color:#f8fafc;
                                    letter-spacing:-0.5px">Candidate Portal</div>
                        <div style="font-size:0.68rem;color:#6d28d9;margin-top:2px;
                                    font-weight:600;letter-spacing:0.08em;
                                    text-transform:uppercase">My Profile</div>
                    </div>
                </div>
            </div>
            """
        )
        st.divider()
        name  = st.session_state.get("candidate_name", "")
        email = st.session_state.get("candidate_email", "")
        st.html(
            f"<div style='padding:12px 8px;background:rgba(124,58,237,0.1);"
            f"border-radius:12px;border:1px solid rgba(124,58,237,0.2);margin-bottom:12px'>"
            f"<div style='font-size:0.8rem;font-weight:700;color:#e2e8f0'>{name}</div>"
            f"<div style='font-size:0.7rem;color:#94a3b8;margin-top:2px'>{email}</div>"
            f"</div>"
        )
        if st.button("🚪 Logout", use_container_width=True, key="candidate_logout"):
            for key in ["role", "candidate_email", "candidate_name", "candidate_id"]:
                st.session_state.pop(key, None)
            st.rerun()

    candidate_portal_page.render(service)


if __name__ == "__main__":
    main()
