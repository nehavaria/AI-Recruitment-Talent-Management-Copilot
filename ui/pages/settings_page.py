"""Settings page."""

import streamlit as st

from ui.components import page_header


def render(_service) -> None:
    page_header("⚙️ Settings", "Customize your application preferences.")

    st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#94a3b8;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.08em'>Appearance</div>", unsafe_allow_html=True)

    is_light = st.session_state.get("light_mode", False)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            f"<div style='padding:4px 0'>"
            f"<div style='font-weight:600;font-size:0.95rem;color:#e2e8f0'>Theme</div>"
            f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:3px'>"
            f"Currently: {'☀️ Light Mode' if is_light else '🌙 Dark Mode'}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with col2:
        label = "🌙 Dark" if is_light else "☀️ Light"
        if st.button(label, type="primary", use_container_width=True):
            st.session_state.light_mode = not is_light
            st.rerun()
