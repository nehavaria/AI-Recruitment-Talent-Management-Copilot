"""Candidate Login & Registration page."""

import streamlit as st

from database.candidate_auth import init_candidate_auth_schema, register_candidate, verify_login


def render() -> None:
    init_candidate_auth_schema()

    st.html(
        """
        <div style="max-width:460px;margin:40px auto 0;text-align:center">
            <div style="width:64px;height:64px;border-radius:18px;
                        background:linear-gradient(135deg,#7c3aed,#2563eb);
                        display:flex;align-items:center;justify-content:center;
                        font-size:1.8rem;margin:0 auto 20px;
                        box-shadow:0 0 30px rgba(124,58,237,0.5)">🎓</div>
            <h1 style="font-size:1.8rem;font-weight:900;margin:0;
                       background:linear-gradient(135deg,#a78bfa,#60a5fa);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                Candidate Portal</h1>
            <p style="color:#94a3b8;font-size:0.9rem;margin-top:8px">
                Log in or create an account to view your profile and application status.</p>
        </div>
        """
    )

    st.markdown("<div style='max-width:460px;margin:24px auto 0'>", unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register"])

    with tab_login:
        _login_form()

    with tab_register:
        _register_form()

    st.markdown("</div>", unsafe_allow_html=True)


# ── Login form ─────────────────────────────────────────────────────────────

def _login_form() -> None:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    email    = st.text_input("Email address", placeholder="you@example.com", key="login_email")
    password = st.text_input("Password", type="password", placeholder="Your password", key="login_password")

    if st.button("🔑 Log In", type="primary", use_container_width=True, key="login_btn"):
        if not email.strip() or not password:
            st.error("Please enter both email and password.")
            return

        result = verify_login(email.strip(), password)
        if result["success"]:
            st.session_state.role             = "candidate"
            st.session_state.candidate_email  = result["email"]
            st.session_state.candidate_name   = result["name"]
            st.session_state.candidate_id     = result["candidate_id"]
            st.success(result["message"])
            st.rerun()
        else:
            st.error(result["message"])


# ── Register form ──────────────────────────────────────────────────────────

def _register_form() -> None:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.caption("Your email must match the one your recruiter used when uploading your resume.")

    email    = st.text_input("Email address", placeholder="you@example.com", key="reg_email")
    password = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="reg_password")
    confirm  = st.text_input("Confirm password", type="password", placeholder="Repeat password", key="reg_confirm")

    if st.button("📝 Create Account", type="primary", use_container_width=True, key="reg_btn"):
        if not email.strip() or not password or not confirm:
            st.error("Please fill in all fields.")
            return
        if password != confirm:
            st.error("Passwords do not match.")
            return

        result = register_candidate(email.strip(), password)
        if result["success"]:
            st.success(f"✅ {result['message']} You can now log in.")
        else:
            st.error(result["message"])
