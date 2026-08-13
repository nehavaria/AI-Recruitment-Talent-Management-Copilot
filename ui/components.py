"""Reusable Streamlit UI components."""

import html as _html
import streamlit as st

_BADGE_PALETTES = [
    ("rgba(139,92,246,0.25)",  "#c4b5fd", "rgba(139,92,246,0.5)"),
    ("rgba(59,130,246,0.25)",  "#93c5fd", "rgba(59,130,246,0.5)"),
    ("rgba(6,182,212,0.25)",   "#67e8f9", "rgba(6,182,212,0.5)"),
    ("rgba(16,185,129,0.25)",  "#6ee7b7", "rgba(16,185,129,0.5)"),
    ("rgba(245,158,11,0.25)",  "#fcd34d", "rgba(245,158,11,0.5)"),
    ("rgba(239,68,68,0.25)",   "#fca5a5", "rgba(239,68,68,0.5)"),
    ("rgba(236,72,153,0.25)",  "#f9a8d4", "rgba(236,72,153,0.5)"),
    ("rgba(20,184,166,0.25)",  "#5eead4", "rgba(20,184,166,0.5)"),
]

_STAT_GRADIENTS = [
    ("linear-gradient(135deg,#8b5cf6,#6366f1)", "rgba(139,92,246,0.3)"),
    ("linear-gradient(135deg,#3b82f6,#06b6d4)", "rgba(59,130,246,0.3)"),
    ("linear-gradient(135deg,#10b981,#06b6d4)", "rgba(16,185,129,0.3)"),
    ("linear-gradient(135deg,#f59e0b,#ef4444)", "rgba(245,158,11,0.3)"),
]

_CARD_ACCENTS = [
    ("linear-gradient(135deg,#8b5cf6,#6366f1)", "rgba(139,92,246,0.15)", "#c4b5fd"),
    ("linear-gradient(135deg,#3b82f6,#06b6d4)", "rgba(59,130,246,0.15)", "#93c5fd"),
    ("linear-gradient(135deg,#10b981,#059669)", "rgba(16,185,129,0.15)", "#6ee7b7"),
    ("linear-gradient(135deg,#f59e0b,#ef4444)", "rgba(245,158,11,0.15)", "#fcd34d"),
    ("linear-gradient(135deg,#ec4899,#8b5cf6)", "rgba(236,72,153,0.15)", "#f9a8d4"),
    ("linear-gradient(135deg,#14b8a6,#3b82f6)", "rgba(20,184,166,0.15)", "#5eead4"),
]


def page_header(title: str, subtitle: str = "") -> None:
    sub_html = (
        f'<p style="font-size:0.95rem;color:#94a3b8;margin:6px 0 0;font-weight:400">{subtitle}</p>'
        if subtitle else ""
    )
    st.html(
        f"""
        <div style="margin-bottom:32px;padding:32px 36px;
                    background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));
                    border-radius:20px;border:1px solid rgba(124,58,237,0.2);
                    backdrop-filter:blur(10px)">
            <h1 style="font-size:2rem;font-weight:900;color:#ffffff;
                       margin:0;letter-spacing:-1px;
                       background:linear-gradient(135deg,#a78bfa,#60a5fa);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                {title}</h1>
            {sub_html}
        </div>
        """
    )


def section_title(text: str) -> None:
    st.html(
        f"""
        <div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;
                    margin:24px 0 14px;letter-spacing:-0.2px;
                    display:flex;align-items:center;gap:8px">
            <div style="width:3px;height:18px;border-radius:2px;
                        background:linear-gradient(135deg,#7c3aed,#2563eb)"></div>
            {text}
        </div>
        """
    )


def stat_strip(stats: list[tuple[str, str, str]]) -> None:
    cols = st.columns(len(stats))
    for i, (col, (label, value, icon)) in enumerate(zip(cols, stats)):
        grad, glow = _STAT_GRADIENTS[i % len(_STAT_GRADIENTS)]
        with col:
            st.html(
                f"""
                <div style="background:rgba(255,255,255,0.06);border-radius:20px;
                            padding:24px;border:1px solid rgba(255,255,255,0.12);
                            backdrop-filter:blur(10px);
                            box-shadow:0 4px 24px {glow};
                            transition:all 0.3s;position:relative;overflow:hidden">
                    <div style="position:absolute;top:-20px;right:-20px;width:80px;height:80px;
                                border-radius:50%;background:{grad};opacity:0.4;
                                filter:blur(20px)"></div>
                    <div style="font-size:0.7rem;font-weight:700;color:#cbd5e1;
                                text-transform:uppercase;letter-spacing:0.1em;
                                margin-bottom:12px">{icon} {label}</div>
                    <div style="font-size:2.2rem;font-weight:900;
                                background:{grad};
                                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                                letter-spacing:-2px;line-height:1">{value}</div>
                </div>
                """
            )


def skill_badges(skills: list[str], max_show: int = 12) -> None:
    if not skills:
        st.caption("No skills detected.")
        return
    shown = skills[:max_show]
    extra = len(skills) - max_show
    badges = "".join(
        f'<span style="background:{_BADGE_PALETTES[i % len(_BADGE_PALETTES)][0]};'
        f'color:{_BADGE_PALETTES[i % len(_BADGE_PALETTES)][1]};'
        f'padding:5px 13px;border-radius:20px;font-size:0.78rem;'
        f'margin:3px 3px;display:inline-block;font-weight:600;'
        f'border:1px solid {_BADGE_PALETTES[i % len(_BADGE_PALETTES)][2]};'
        f'letter-spacing:0.01em;backdrop-filter:blur(4px)">'
        f'{_html.escape(s)}</span>'
        for i, s in enumerate(shown)
    )
    if extra > 0:
        badges += (
            f'<span style="background:rgba(255,255,255,0.05);color:#64748b;'
            f'padding:5px 13px;border-radius:20px;font-size:0.78rem;'
            f'margin:3px 3px;display:inline-block;font-weight:600;'
            f'border:1px solid rgba(255,255,255,0.1)">+{extra} more</span>'
        )
    st.markdown(
        f'<div style="line-height:2.4;margin:6px 0">{badges}</div>',
        unsafe_allow_html=True,
    )


def candidate_card(c: dict, on_select_label: str = "View Profile") -> bool:
    raw_name = (c.get("name") or "Unknown").splitlines()[0].strip() or "Unknown"
    email    = c.get("email") or "-"
    phone    = c.get("phone") or "-"
    skills   = [s.strip() for s in c.get("skills", "").split(",") if s.strip()]
    edu      = (c.get("education") or "").splitlines()
    exp      = (c.get("experience") or "").splitlines()
    cid      = c.get("candidate_id", 0)
    edu_text = edu[0] if edu else "-"
    exp_raw  = exp[0] if exp else ""
    exp_text = (exp_raw[:50] + "…") if len(exp_raw) > 50 else (exp_raw or "-")
    initials = "".join(w[0].upper() for w in raw_name.split()[:2]) or "?"
    accent   = _CARD_ACCENTS[cid % len(_CARD_ACCENTS)]
    grad, glow_bg, accent_color = accent

    with st.container(border=True):
        st.html(
            f"""
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;width:100%;box-sizing:border-box">
                <div style="width:48px;height:48px;border-radius:14px;flex-shrink:0;
                            background:{grad};
                            display:flex;align-items:center;justify-content:center;
                            color:#fff;font-weight:900;font-size:1.1rem;
                            box-shadow:0 4px 16px {glow_bg}">
                    {_html.escape(initials)}</div>
                <div style="min-width:0;flex:1;overflow:hidden">
                    <div style="font-weight:800;font-size:0.95rem;color:#ffffff;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {_html.escape(raw_name)}</div>
                    <div style="font-size:0.75rem;color:#cbd5e1;margin-top:3px;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        ✉ {_html.escape(email)}</div>
                </div>
                <div style="background:{glow_bg};color:{accent_color};
                            font-size:0.7rem;font-weight:800;padding:3px 10px;
                            border-radius:20px;border:1px solid {accent_color}40;
                            white-space:nowrap;flex-shrink:0">{len(skills)} skills</div>
            </div>
            <div style="background:rgba(255,255,255,0.07);border-radius:10px;
                        padding:9px 12px;border:1px solid rgba(255,255,255,0.1);margin-bottom:6px;width:100%;box-sizing:border-box">
                <div style="font-size:0.6rem;color:{accent_color};font-weight:700;
                            text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px">🎓 Education</div>
                <div style="font-size:0.78rem;color:#f1f5f9;font-weight:500;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                    {_html.escape(edu_text)}</div>
            </div>
            <div style="background:rgba(255,255,255,0.07);border-radius:10px;
                        padding:9px 12px;border:1px solid rgba(255,255,255,0.1);margin-bottom:12px;width:100%;box-sizing:border-box">
                <div style="font-size:0.6rem;color:{accent_color};font-weight:700;
                            text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px">💼 Experience</div>
                <div style="font-size:0.78rem;color:#f1f5f9;font-weight:500;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                    {_html.escape(exp_text)}</div>
            </div>
            """
        )
        skill_badges(skills, max_show=4)
        clicked = st.button(
            on_select_label,
            key=f"card_btn_{cid}",
            use_container_width=True,
            type="primary",
        )
    return clicked


def info_row(label: str, value: str) -> None:
    st.html(
        f"""
        <div style="display:flex;padding:12px 0;
                    border-bottom:1px solid rgba(255,255,255,0.08);
                    align-items:flex-start;gap:16px">
            <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;
                        min-width:130px;padding-top:2px;text-transform:uppercase;
                        letter-spacing:0.06em">{_html.escape(label)}</div>
            <div style="font-size:0.9rem;color:#f8fafc;flex:1;font-weight:500">
                {_html.escape(str(value or "—"))}</div>
        </div>
        """
    )


def empty_state(message: str = "No data found.") -> None:
    st.html(
        f"""
        <div style="text-align:center;padding:80px 20px;
                    background:linear-gradient(135deg,rgba(124,58,237,0.05),rgba(37,99,235,0.05));
                    border-radius:24px;border:2px dashed rgba(124,58,237,0.2);margin:20px 0">
            <div style="font-size:4rem;margin-bottom:20px;filter:grayscale(0.3)">🚀</div>
            <div style="font-size:1.1rem;font-weight:700;color:#e2e8f0;
                        margin-bottom:8px">{_html.escape(message)}</div>
            <div style="font-size:0.85rem;color:#475569;line-height:1.6">
                Upload a resume to get started</div>
        </div>
        """
    )
