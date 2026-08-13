"""Unified Login Page — Recruiter and Candidate authentication."""

import streamlit as st

from database.candidate_auth import init_candidate_auth_schema, register_candidate, verify_login
from database.recruiter_auth import init_recruiter_auth_schema, register_recruiter, verify_recruiter_login


def render() -> None:
    init_recruiter_auth_schema()
    init_candidate_auth_schema()

    st.html("""
        <div style="max-width:480px;margin:48px auto 0;text-align:center">
            <div style="width:64px;height:64px;border-radius:18px;
                        background:linear-gradient(135deg,#7c3aed,#2563eb);
                        display:flex;align-items:center;justify-content:center;
                        font-size:1.8rem;margin:0 auto 20px;
                        box-shadow:0 0 30px rgba(124,58,237,0.5)">🤖</div>
            <h1 style="font-size:1.9rem;font-weight:900;margin:0;
                       background:linear-gradient(135deg,#a78bfa,#60a5fa);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                TalentAI</h1>
            <p style="color:#94a3b8;font-size:0.88rem;margin-top:8px">
                AI Recruitment &amp; Talent Management Copilot</p>
        </div>
    """)

    st.markdown("<div style='max-width:480px;margin:28px auto 0'>", unsafe_allow_html=True)

    role_tab, cand_tab = st.tabs(["🧑‍💼 Recruiter / Admin", "🎓 Candidate"])

    with role_tab:
        _recruiter_panel()

    with cand_tab:
        _candidate_panel()

    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════
#  RECRUITER PANEL
# ══════════════════════════════════════════════

def _recruiter_panel() -> None:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    login_tab, reg_tab = st.tabs(["🔑 Login", "📝 Register"])

    with login_tab:
        email    = st.text_input("Email", placeholder="recruiter@company.com", key="rec_login_email")
        password = st.text_input("Password", type="password", key="rec_login_pw")

        if st.button("Login as Recruiter", type="primary", use_container_width=True, key="rec_login_btn"):
            if not email.strip() or not password:
                st.error("Enter email and password.")
                return
            result = verify_recruiter_login(email, password)
            if result["success"]:
                st.session_state.role           = "recruiter"
                st.session_state.recruiter_name  = result["name"]
                st.session_state.recruiter_email = result["email"]
                st.rerun()
            else:
                st.error(result["message"])

    with reg_tab:
        st.caption("Create a recruiter account to access the full platform.")
        name     = st.text_input("Full Name", placeholder="Jane Smith", key="rec_reg_name")
        email    = st.text_input("Email", placeholder="recruiter@company.com", key="rec_reg_email")
        password = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="rec_reg_pw")
        confirm  = st.text_input("Confirm Password", type="password", key="rec_reg_confirm")

        if st.button("Create Recruiter Account", type="primary", use_container_width=True, key="rec_reg_btn"):
            if not name.strip() or not email.strip() or not password:
                st.error("All fields are required.")
                return
            if password != confirm:
                st.error("Passwords do not match.")
                return
            result = register_recruiter(name, email, password)
            if result["success"]:
                st.success(f"✅ {result['message']}")
            else:
                st.error(result["message"])


# ══════════════════════════════════════════════
#  CANDIDATE PANEL
# ══════════════════════════════════════════════

def _candidate_panel() -> None:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    login_tab, reg_tab = st.tabs(["🔑 Login", "📝 Register"])

    with login_tab:
        email    = st.text_input("Email", placeholder="you@example.com", key="cand_login_email")
        password = st.text_input("Password", type="password", key="cand_login_pw")

        if st.button("Login as Candidate", type="primary", use_container_width=True, key="cand_login_btn"):
            if not email.strip() or not password:
                st.error("Enter email and password.")
                return
            result = verify_login(email, password)
            if result["success"]:
                st.session_state.role            = "candidate"
                st.session_state.candidate_email = result["email"]
                st.session_state.candidate_name  = result["name"]
                st.session_state.candidate_id    = result["candidate_id"]
                st.rerun()
            else:
                st.error(result["message"])

    with reg_tab:
        st.caption("Your email must match the one your recruiter used when uploading your resume.")
        email    = st.text_input("Email", placeholder="you@example.com", key="cand_reg_email")
        password = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="cand_reg_pw")
        confirm  = st.text_input("Confirm Password", type="password", key="cand_reg_confirm")

        if st.button("Create Candidate Account", type="primary", use_container_width=True, key="cand_reg_btn"):
            if not email.strip() or not password:
                st.error("All fields are required.")
                return
            if password != confirm:
                st.error("Passwords do not match.")
                return
            result = register_candidate(email, password)
            if result["success"]:
                st.success(f"✅ {result['message']}")
            else:
                st.error(result["message"])
