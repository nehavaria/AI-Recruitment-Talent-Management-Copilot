"""Resume Upload page."""

import html as _html
import logging

import streamlit as st

from database.db_service import SaveResult, SaveStatus
from parsers.profile_extractor import CandidateProfile
from services.candidate_service import CandidateService
from ui.components import info_row, page_header, skill_badges

logger = logging.getLogger(__name__)


def render(service: CandidateService) -> None:
    page_header(
        "📄 Upload Resume",
        "Parse and store candidate profiles automatically from PDF or DOCX files.",
    )

    st.html(
        """
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:36px">
            <div style="background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(124,58,237,0.05));
                        border-radius:16px;padding:20px;
                        border:1px solid rgba(124,58,237,0.25);backdrop-filter:blur(10px)">
                <div style="font-size:1.8rem;margin-bottom:10px">📂</div>
                <div style="font-weight:700;font-size:0.9rem;color:#e2e8f0">Upload</div>
                <div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;line-height:1.5">Drop PDF or DOCX</div>
            </div>
            <div style="background:linear-gradient(135deg,rgba(37,99,235,0.15),rgba(37,99,235,0.05));
                        border-radius:16px;padding:20px;
                        border:1px solid rgba(37,99,235,0.25);backdrop-filter:blur(10px)">
                <div style="font-size:1.8rem;margin-bottom:10px">🧠</div>
                <div style="font-weight:700;font-size:0.9rem;color:#e2e8f0">Extract</div>
                <div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;line-height:1.5">AI parses skills &amp; info</div>
            </div>
            <div style="background:linear-gradient(135deg,rgba(5,150,105,0.15),rgba(5,150,105,0.05));
                        border-radius:16px;padding:20px;
                        border:1px solid rgba(5,150,105,0.25);backdrop-filter:blur(10px)">
                <div style="font-size:1.8rem;margin-bottom:10px">💾</div>
                <div style="font-weight:700;font-size:0.9rem;color:#e2e8f0">Save</div>
                <div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;line-height:1.5">Stored in database</div>
            </div>
            <div style="background:linear-gradient(135deg,rgba(217,119,6,0.15),rgba(217,119,6,0.05));
                        border-radius:16px;padding:20px;
                        border:1px solid rgba(217,119,6,0.25);backdrop-filter:blur(10px)">
                <div style="font-size:1.8rem;margin-bottom:10px">🔍</div>
                <div style="font-weight:700;font-size:0.9rem;color:#e2e8f0">Search</div>
                <div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;line-height:1.5">Find on Dashboard</div>
            </div>
        </div>
        """
    )

    uploaded = st.file_uploader(
        "Drop your resume here or click to browse",
        type=["pdf", "docx"],
        help="Supported: PDF · DOCX",
    )

    if uploaded is None:
        st.html(
            """
            <div style="border:2px dashed rgba(124,58,237,0.3);border-radius:24px;
                        padding:70px 20px;text-align:center;
                        background:linear-gradient(135deg,rgba(124,58,237,0.05),rgba(37,99,235,0.05));
                        margin-top:8px;backdrop-filter:blur(10px)">
                <div style="font-size:4rem;margin-bottom:16px">📂</div>
                <div style="font-size:1.1rem;font-weight:700;color:#e2e8f0">Drop your resume here</div>
                <div style="font-size:0.85rem;color:#475569;margin-top:10px;line-height:1.7">
                    Supports <b style='color:#a78bfa'>PDF</b> and
                    <b style='color:#60a5fa'>DOCX</b> formats</div>
            </div>
            """
        )
        return

    size_kb   = round(len(uploaded.getvalue()) / 1024, 1)
    ext       = uploaded.name.rsplit(".", 1)[-1].upper()
    ext_color = "#7c3aed" if ext == "PDF" else "#2563eb"
    st.html(
        f"""
        <div style="background:linear-gradient(135deg,rgba(124,58,237,0.1),rgba(37,99,235,0.1));
                    border:1px solid rgba(124,58,237,0.25);border-radius:16px;
                    padding:16px 20px;display:flex;align-items:center;gap:16px;margin-bottom:20px;
                    backdrop-filter:blur(10px)">
            <div style="background:{ext_color};color:#fff;font-weight:800;
                        font-size:0.72rem;padding:6px 12px;border-radius:10px;
                        flex-shrink:0;letter-spacing:0.05em;box-shadow:0 2px 10px rgba(124,58,237,0.4)">{ext}</div>
            <div style="flex:1;min-width:0">
                <div style="font-weight:600;font-size:0.92rem;color:#f1f5f9;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                    {_html.escape(uploaded.name)}</div>
                <div style="font-size:0.75rem;color:#64748b;margin-top:3px">{size_kb} KB</div>
            </div>
            <div style="color:#34d399;font-size:1.3rem">✓</div>
        </div>
        """
    )

    if st.button("⚡ Process Resume", type="primary"):
        _process(service, uploaded)


# ── Processing ─────────────────────────────────────────────────────────────

def _process(service: CandidateService,
             uploaded: st.runtime.uploaded_file_manager.UploadedFile) -> None:
    with st.spinner("🧠 Parsing resume and extracting profile…"):
        try:
            file_path       = service.save_upload(uploaded.read(), uploaded.name)
            recruiter_email = st.session_state.get("recruiter_email", "")
            profile, result = service.process_resume(file_path, recruiter_email)
        except ValueError as exc:
            st.error(f"❌ Unsupported file: {exc}")
            return
        except Exception as exc:
            st.error(f"❌ Processing failed: {exc}")
            logger.exception("upload_page › unexpected error  %s", exc)
            return

    if not _show_save_feedback(result):
        return
    _render_profile_preview(profile)


def _show_save_feedback(result: SaveResult) -> bool:
    if result.status == SaveStatus.CREATED:
        st.success(f"✅ {result.message}")
        return True
    if result.status == SaveStatus.UPDATED:
        st.info(f"🔄 {result.message}")
        return True
    st.error(f"❌ {result.message}")
    for err in result.errors:
        st.caption(f"• {err}")
    return False


# ── Profile preview ────────────────────────────────────────────────────────

def _render_profile_preview(profile: CandidateProfile) -> None:
    st.divider()
    st.html("<h3 style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:16px'>🧾 Extracted Profile</h3>")

    name     = (profile.name or "Unknown").splitlines()[0].strip() or "Unknown"
    initials = "".join(w[0].upper() for w in name.split()[:2]) or "?"

    col_av, col_info = st.columns([1, 6])
    with col_av:
        st.markdown(
            f'<div style="width:60px;height:60px;border-radius:16px;'
            f'background:linear-gradient(135deg,#7c3aed,#2563eb);'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-weight:800;font-size:1.3rem;margin-top:6px">'
            f'{initials}</div>',
            unsafe_allow_html=True,
        )
    with col_info:
        st.markdown(f"### {name}")
        st.caption(f"✉ {profile.email or '—'}  ·  📞 {profile.phone or '—'}" +
                   (f"  ·  📍 {profile.location}" if profile.location else ""))

    tab_info, tab_skills, tab_exp, tab_edu, tab_extra = st.tabs(
        ["📋 Info", "🛠 Skills", "💼 Experience", "🎓 Education", "📁 Projects & Certs"]
    )

    with tab_info:
        info_row("Name",     profile.name)
        info_row("Email",    profile.email)
        info_row("Phone",    profile.phone)
        info_row("Location", profile.location)
        if profile.summary:
            st.html(
                f"""
                <div style="background:rgba(37,99,235,0.1);border-left:3px solid #60a5fa;
                            border-radius:0 8px 8px 0;padding:12px 16px;margin-top:8px">
                    <div style="font-size:0.72rem;font-weight:600;color:#94a3b8;
                                letter-spacing:0.06em;margin-bottom:6px">SUMMARY</div>
                    <div style="font-size:0.85rem;color:#e2e8f0;line-height:1.6">
                        {_html.escape(profile.summary)}</div>
                </div>
                """
            )

    with tab_skills:
        if profile.skills:
            st.html(
                f"""<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
                    <div style="font-size:1.5rem;font-weight:800;color:#60a5fa">{len(profile.skills)}</div>
                    <div style="font-size:0.85rem;color:#94a3b8">skills detected</div>
                </div>"""
            )
            skill_badges(profile.skills, max_show=50)
        else:
            st.caption("No skills detected.")

    with tab_exp:
        _render_lines(profile.experience, "No experience data extracted.")

    with tab_edu:
        _render_lines(profile.education, "No education data extracted.")

    with tab_extra:
        if profile.projects:
            st.html("<div style='font-size:0.72rem;font-weight:600;color:#64748b;letter-spacing:0.06em;margin-bottom:8px'>PROJECTS</div>")
            _render_lines(profile.projects, "")
        if profile.certifications:
            st.html("<div style='font-size:0.72rem;font-weight:600;color:#64748b;letter-spacing:0.06em;margin:12px 0 8px'>CERTIFICATIONS</div>")
            _render_lines(profile.certifications, "")
        if not profile.projects and not profile.certifications:
            st.caption("No projects or certifications extracted.")


def _render_lines(items: list[str], empty_msg: str) -> None:
    if not items:
        st.caption(empty_msg)
        return
    for item in items:
        st.html(
            f"""
            <div style="display:flex;gap:10px;padding:7px 0;
                        border-bottom:1px solid rgba(255,255,255,0.07);align-items:flex-start">
                <div style="color:#818cf8;font-size:0.7rem;margin-top:3px;flex-shrink:0">●</div>
                <div style="font-size:0.85rem;color:#e2e8f0;line-height:1.5">
                    {_html.escape(item)}</div>
            </div>
            """
        )
