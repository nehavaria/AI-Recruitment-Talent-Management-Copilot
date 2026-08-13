"""
Milestone 4 — Voice-Based Candidate Screening

Workflow:
  AI question (reuses _generate_question from interview_simulator)
    → candidate records voice answer
    → audio saved to data/uploads/voice/ (file reference stored, not binary)
    → speech-to-text transcription (speech_recognition, same as simulator)
    → transcript stored in voice_screening_answers (new table, minimal schema)
    → evaluation via _evaluate (reused from interview_simulator)
    → full report saved via save_report → interview_sessions (existing table)

New table: voice_screening_answers
  Links session_id (FK → interview_sessions) + candidate_id + question_index
  Stores: question text, audio_path, transcript, evaluation JSON
  Reason: interview_sessions.report_json is a blob; per-question queryable rows
  are needed for audit, replay and incremental saves.
"""

import html
import io
import json
import logging
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import mysql.connector
import speech_recognition as sr
import streamlit as st

from config.settings import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
    UPLOAD_DIR,
)
from milestone3.interview_db import init_db as _init_sessions_table, save_report
from milestone3.interview_simulator import _generate_question, _evaluate, _use_gemini
from services.candidate_service import CandidateService
from ui.components import page_header

logger = logging.getLogger(__name__)

_VOICE_DIR = UPLOAD_DIR / "voice"
_VOICE_DIR.mkdir(parents=True, exist_ok=True)

_TOTAL = 5  # questions per voice screening session

_CFG = dict(
    host=MYSQL_HOST, port=MYSQL_PORT, database=MYSQL_DATABASE,
    user=MYSQL_USER, password=MYSQL_PASSWORD,
    autocommit=False, charset="utf8mb4", collation="utf8mb4_unicode_ci",
)


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


def _init_voice_table() -> None:
    """Create voice_screening_answers only if it does not exist."""
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voice_screening_answers (
                answer_id      INT          NOT NULL AUTO_INCREMENT,
                session_id     INT          NOT NULL DEFAULT 0
                                            COMMENT 'FK → interview_sessions.session_id (set after session saved)',
                candidate_id   INT          NOT NULL,
                job_id         INT          NOT NULL DEFAULT 0,
                question_index TINYINT      NOT NULL,
                question_text  TEXT         NOT NULL,
                audio_path     VARCHAR(500) NOT NULL DEFAULT '',
                transcript     TEXT         NOT NULL,
                evaluation     JSON         NOT NULL,
                created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (answer_id),
                INDEX idx_vsa_candidate (candidate_id),
                INDEX idx_vsa_session   (session_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.close()


def _save_answer(candidate_id: int, job_id: int, q_index: int,
                 question: str, audio_path: str,
                 transcript: str, evaluation: dict) -> int:
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO voice_screening_answers
               (candidate_id, job_id, question_index, question_text,
                audio_path, transcript, evaluation)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (candidate_id, job_id, q_index, question,
             audio_path, transcript, json.dumps(evaluation, default=str)),
        )
        aid = cur.lastrowid
        cur.close()
    return aid


def _backfill_session_id(candidate_id: int, job_id: int, session_id: int) -> None:
    """After saving the full report, link all answer rows to the session."""
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE voice_screening_answers SET session_id = %s "
            "WHERE candidate_id = %s AND job_id = %s AND session_id = 0",
            (session_id, candidate_id, job_id),
        )
        cur.close()


def _load_session_answers(session_id: int) -> list[dict]:
    with _db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM voice_screening_answers "
            "WHERE session_id = %s ORDER BY question_index",
            (session_id,),
        )
        rows = cur.fetchall()
        cur.close()
    for r in rows:
        if isinstance(r.get("evaluation"), str):
            try:
                r["evaluation"] = json.loads(r["evaluation"])
            except Exception:
                r["evaluation"] = {}
    return rows


# ── Audio helpers ──────────────────────────────────────────────────────────

def _save_audio_file(audio_bytes: bytes, candidate_id: int, q_index: int) -> str:
    """Save audio bytes to disk; return path relative to UPLOAD_DIR."""
    fname = f"voice_{candidate_id}_q{q_index}_{uuid.uuid4().hex[:8]}.wav"
    dest  = _VOICE_DIR / fname
    dest.write_bytes(audio_bytes)
    return str(dest.relative_to(UPLOAD_DIR.parent))


def _transcribe(audio_bytes: bytes) -> str:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as src:
            audio = recognizer.record(src)
        return recognizer.recognize_google(audio)
    except Exception:
        return ""


# ── UI helpers ─────────────────────────────────────────────────────────────

def _score_color(s: float) -> str:
    return "#10b981" if s >= 70 else "#f59e0b" if s >= 40 else "#ef4444"


def _progress(idx: int, name: str, job: str, elapsed: int) -> None:
    pct = int(idx / _TOTAL * 100)
    m, s = elapsed // 60, elapsed % 60
    st.markdown(
        f"<div style='margin-bottom:16px'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:0.75rem;color:#94a3b8;margin-bottom:6px'>"
        f"<span>🎙 <b style='color:#e2e8f0'>{html.escape(name)}</b> — {html.escape(job)}</span>"
        f"<span>❓ {idx}/{_TOTAL} &nbsp;⏱️ {m:02d}:{s:02d}</span></div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:8px;overflow:hidden'>"
        f"<div style='background:linear-gradient(90deg,#7c3aed,#2563eb);"
        f"height:100%;width:{pct}%;border-radius:20px;transition:width 0.4s'></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _q_bubble(text: str) -> None:
    st.markdown(
        f"<div style='display:flex;gap:10px;margin-bottom:14px'>"
        f"<div style='width:36px;height:36px;border-radius:10px;flex-shrink:0;"
        f"background:linear-gradient(135deg,#7c3aed,#2563eb);"
        f"display:flex;align-items:center;justify-content:center;font-size:1.1rem'>🤖</div>"
        f"<div style='background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.25);"
        f"border-radius:0 14px 14px 14px;padding:12px 16px;max-width:85%'>"
        f"<div style='font-size:0.93rem;color:#f1f5f9;line-height:1.6'>{html.escape(text)}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _a_bubble(transcript: str, score: int) -> None:
    clr = _score_color(score)
    st.markdown(
        f"<div style='display:flex;gap:10px;margin-bottom:6px;flex-direction:row-reverse'>"
        f"<div style='width:36px;height:36px;border-radius:10px;flex-shrink:0;"
        f"background:linear-gradient(135deg,#0ea5e9,#10b981);"
        f"display:flex;align-items:center;justify-content:center;font-size:1.1rem'>🎙</div>"
        f"<div style='background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.2);"
        f"border-radius:14px 0 14px 14px;padding:12px 16px;max-width:85%;text-align:right'>"
        f"<div style='font-size:0.93rem;color:#f1f5f9;line-height:1.6'>{html.escape(transcript)}"
        f"<span style='font-size:0.65rem;background:{clr}20;color:{clr};"
        f"padding:2px 8px;border-radius:10px;margin-left:6px;font-weight:700'>{score}%</span>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )


def _eval_card(ev: dict) -> None:
    clr = _score_color(ev.get("score", 0))
    engine = "🔮 Gemini" if _use_gemini() else "🤖 Groq"
    dims = [
        ("🛠 Technical",       ev.get("technical", 0)),
        ("🗣 Communication",   ev.get("communication", 0)),
        ("💪 Confidence",      ev.get("confidence", 0)),
        ("🧩 Problem Solving", ev.get("problem_solving", 0)),
        ("✍️ Grammar",         ev.get("grammar", 0)),
    ]
    bars = "".join(
        f"<div style='margin-bottom:8px'>"
        f"<div style='display:flex;justify-content:space-between;font-size:0.78rem;"
        f"color:#e2e8f0;margin-bottom:3px'><span>{lbl}</span>"
        f"<span style='color:{_score_color(v)};font-weight:700'>{v}%</span></div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:5px;overflow:hidden'>"
        f"<div style='background:{_score_color(v)};height:100%;width:{v}%;border-radius:20px'></div>"
        f"</div></div>"
        for lbl, v in dims
    )
    st.markdown(
        f"<div style='background:rgba(255,255,255,0.03);border-radius:14px;"
        f"padding:16px 18px;border-left:4px solid {clr};"
        f"border:1px solid {clr}30;margin:6px 0 16px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>"
        f"<span style='font-size:0.68rem;font-weight:700;color:#94a3b8;text-transform:uppercase'>"
        f"{engine}</span>"
        f"<span style='background:{clr}20;color:{clr};font-weight:800;font-size:0.8rem;"
        f"padding:3px 12px;border-radius:20px'>Overall {ev.get('score',0)}% — {ev.get('level','')}</span>"
        f"</div>{bars}"
        f"<div style='font-size:0.82rem;color:#cbd5e1;margin-top:10px;line-height:1.6'>"
        f"{html.escape(ev.get('feedback',''))}</div></div>",
        unsafe_allow_html=True,
    )


# ── Results screen ─────────────────────────────────────────────────────────

def _show_results(ss: dict) -> None:
    history   = ss["vs_history"]
    scores    = [h["evaluation"]["score"] for h in history if h.get("evaluation")]
    avg       = round(sum(scores) / len(scores), 1) if scores else 0
    clr       = _score_color(avg)
    verdict   = ("Strong Performance 🎉" if avg >= 70
                 else "Good Effort 👍" if avg >= 40
                 else "Needs More Preparation 📚")
    elapsed   = int(time.time() - ss["vs_start"])
    cand      = ss["vs_candidate"]
    job       = ss["vs_job"]
    cand_name = (cand.get("name") or "Unknown").splitlines()[0]

    # Build and persist full report into interview_sessions (existing table)
    report = {
        "candidate": cand,
        "job":       job,
        "answers": [
            {
                "question":   h["question"],
                "answer":     h["transcript"],
                "transcript": h["transcript"],
                "via":        "voice",
                "skill":      "Voice Screening",
                "evaluation": h["evaluation"],
                "ideal":      "",
                "audio_path": h.get("audio_path", ""),
            }
            for h in history
        ],
        "avg_score": avg,
        "verdict":   verdict,
        "mode":      "voice_screening",
    }
    st.session_state.sim_last_report = report  # makes it visible in Interview Report page

    try:
        _init_sessions_table()
        session_id = save_report(report)
        _backfill_session_id(cand["candidate_id"], job["job_id"], session_id)
    except Exception as e:
        logger.warning("Failed to persist voice screening report: %s", e)
        session_id = 0

    # Header card
    st.markdown(
        f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),"
        f"rgba(37,99,235,0.1));border-radius:20px;padding:28px 32px;"
        f"border:1px solid {clr}40;text-align:center;margin-bottom:20px'>"
        f"<div style='font-size:3.5rem;font-weight:900;color:{clr}'>{avg}%</div>"
        f"<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-top:8px'>{verdict}</div>"
        f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:6px'>"
        f"⏱️ {elapsed//60:02d}:{elapsed%60:02d} · {_TOTAL} questions · 🎙 all voice"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    def _avg_dim(key):
        vals = [h["evaluation"].get(key, 0) for h in history if h.get("evaluation")]
        return round(sum(vals) / len(vals), 1) if vals else 0

    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("🛠 Technical",       f"{_avg_dim('technical')}%")
    d2.metric("🗣 Communication",   f"{_avg_dim('communication')}%")
    d3.metric("💪 Confidence",      f"{_avg_dim('confidence')}%")
    d4.metric("🧩 Problem Solving", f"{_avg_dim('problem_solving')}%")
    d5.metric("✍️ Grammar",         f"{_avg_dim('grammar')}%")

    st.divider()

    # Per-question review
    st.markdown(
        "<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:12px'>"
        "📋 Full Voice Screening Review</div>",
        unsafe_allow_html=True,
    )
    for i, h in enumerate(history):
        ev = h.get("evaluation", {})
        sc = ev.get("score", 0)
        with st.expander(f"🎙 Q{i+1}: {h['question'][:65]}… — {sc}%"):
            st.markdown(f"**🎙 Transcript:** _{h.get('transcript') or '(no transcript)'}_")
            if h.get("audio_path"):
                audio_full = Path(h["audio_path"])
                if not audio_full.is_absolute():
                    audio_full = UPLOAD_DIR.parent / h["audio_path"]
                if audio_full.exists():
                    st.audio(str(audio_full))
            if ev:
                _eval_card(ev)

    # Download transcript
    lines = []
    for i, h in enumerate(history):
        ev = h.get("evaluation", {})
        lines += [
            f"Q{i+1}: {h['question']}",
            f"Transcript: {h.get('transcript') or '(none)'}",
            f"Score: {ev.get('score','—')}% | {ev.get('level','—')}",
            f"Feedback: {ev.get('feedback','')}",
            "",
        ]
    st.download_button(
        "📥 Download Voice Screening Transcript",
        data="\n".join(lines),
        file_name=f"voice_screening_{cand_name.replace(' ','_')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if st.button("🔄 New Voice Screening", type="primary", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("vs_"):
                del st.session_state[k]
        st.rerun()


# ── Main render ────────────────────────────────────────────────────────────

def render(service: CandidateService) -> None:
    page_header(
        "🎙 Voice Screening",
        f"AI-generated questions · Voice answers · Auto-transcription · "
        f"{'Gemini' if _use_gemini() else 'Groq'} evaluation · {_TOTAL} questions",
    )

    # Init tables once
    if "vs_tables_ready" not in st.session_state:
        try:
            _init_sessions_table()
            _init_voice_table()
            st.session_state["vs_tables_ready"] = True
        except Exception as e:
            st.error(f"Database init failed: {e}")
            return

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        st.info("No candidates found — upload resumes first.")
        return
    if not jobs:
        st.info("No jobs found — create a job posting first.")
        return

    ss = st.session_state

    # ── Setup ──────────────────────────────────────────────────────────────
    if not ss.get("vs_active"):
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#a78bfa;"
                "margin-bottom:16px'>⚙️ Voice Screening Setup</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                job_opts = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
                sel_job  = job_opts[st.selectbox("💼 Job Role", list(job_opts.keys()), key="vs_job_sel")]
            with c2:
                cand_opts = {
                    f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c
                    for c in candidates
                }
                sel_cand = cand_opts[st.selectbox("👤 Candidate", list(cand_opts.keys()), key="vs_cand_sel")]

            engine = "🔮 Gemini" if _use_gemini() else "🤖 Groq"
            st.info(
                f"**{(sel_cand.get('name') or 'Candidate').splitlines()[0]}** · "
                f"**{sel_job['job_title']}** · {_TOTAL} voice questions · {engine} evaluation\n\n"
                "Upload a **WAV file** for each question. Answers are transcribed automatically."
            )

            if st.button("🚀 Start Voice Screening", type="primary", use_container_width=True):
                ss["vs_active"]    = True
                ss["vs_history"]   = []
                ss["vs_index"]     = 0
                ss["vs_done"]      = False
                ss["vs_start"]     = time.time()
                ss["vs_candidate"] = sel_cand
                ss["vs_job"]       = sel_job
                ss["vs_current_q"] = None
                st.rerun()
        return

    # ── Done ───────────────────────────────────────────────────────────────
    if ss.get("vs_done"):
        _show_results(ss)
        return

    # ── Active session ─────────────────────────────────────────────────────
    cand_name = (ss["vs_candidate"].get("name") or "Unknown").splitlines()[0]
    job_title = ss["vs_job"].get("job_title") or "Engineer"
    elapsed   = int(time.time() - ss["vs_start"])

    _progress(ss["vs_index"], cand_name, job_title, elapsed)

    # Replay answered questions
    for h in ss["vs_history"]:
        _q_bubble(h["question"])
        _a_bubble(h.get("transcript") or "(no transcript)", h["evaluation"].get("score", 0))
        _eval_card(h["evaluation"])

    # Generate next question if needed
    if ss["vs_current_q"] is None:
        with st.spinner("🤖 Generating question…"):
            ss["vs_current_q"] = _generate_question(
                ss["vs_candidate"], ss["vs_job"],
                ss["vs_history"], ss["vs_index"] + 1,
            )
        st.rerun()

    _q_bubble(ss["vs_current_q"])

    # ── Voice answer input ─────────────────────────────────────────────────
    st.markdown(
        "<div style='background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);"
        "border-radius:12px;padding:14px 18px;margin-bottom:12px;font-size:0.85rem;color:#c4b5fd'>"
        "🎙️ Record your answer as a <b>WAV file</b> and upload below. "
        "It will be transcribed and evaluated automatically.</div>",
        unsafe_allow_html=True,
    )

    q_key     = f"vs_audio_{ss['vs_index']}"
    audio_file = st.file_uploader(
        "Upload voice answer (WAV)", type=["wav"], key=q_key,
    )

    transcript   = ""
    audio_path   = ""
    final_answer = ""

    if audio_file:
        audio_bytes = audio_file.read()
        st.audio(audio_bytes, format="audio/wav")

        with st.spinner("🎙️ Transcribing…"):
            transcript = _transcribe(audio_bytes)

        if transcript:
            st.success(f"📝 Transcript: **{transcript}**")
            final_answer = transcript
        else:
            st.warning("Could not transcribe audio. Enter answer manually below.")

        # Allow manual override / fallback
        manual = st.text_input(
            "✏️ Edit or enter answer manually (optional):",
            value=transcript,
            key=f"vs_manual_{ss['vs_index']}",
        )
        if manual.strip():
            final_answer = manual.strip()
            transcript   = manual.strip()

        col1, col2 = st.columns([4, 1])
        with col1:
            submit = st.button(
                "✅ Submit Voice Answer", type="primary",
                use_container_width=True, key=f"vs_submit_{ss['vs_index']}",
            )
        with col2:
            skip = st.button("⏭ Skip", use_container_width=True, key=f"vs_skip_{ss['vs_index']}")

        if submit or skip:
            cid = ss["vs_candidate"]["candidate_id"]
            jid = ss["vs_job"]["job_id"]
            q   = ss["vs_current_q"]
            idx = ss["vs_index"]

            # Save audio file (only if submitted with audio)
            if submit and audio_bytes:
                try:
                    audio_path = _save_audio_file(audio_bytes, cid, idx)
                except Exception as e:
                    logger.warning("Audio save failed: %s", e)

            # Evaluate
            with st.spinner(f"{'🔮 Gemini' if _use_gemini() else '🤖 Groq'} evaluating…"):
                ev = _evaluate(q, final_answer, job_title)

            # Persist answer row to voice_screening_answers
            try:
                _save_answer(cid, jid, idx, q, audio_path, transcript, ev)
            except Exception as e:
                logger.warning("voice_screening_answers insert failed: %s", e)

            ss["vs_history"].append({
                "question":   q,
                "transcript": transcript,
                "audio_path": audio_path,
                "evaluation": ev,
            })
            ss["vs_index"]    += 1
            ss["vs_current_q"] = None
            ss["vs_done"]      = ss["vs_index"] >= _TOTAL
            st.rerun()

    else:
        # Skip without audio
        if st.button("⏭ Skip Question", key=f"vs_skip_noaudio_{ss['vs_index']}"):
            cid = ss["vs_candidate"]["candidate_id"]
            jid = ss["vs_job"]["job_id"]
            q   = ss["vs_current_q"]
            idx = ss["vs_index"]
            ev  = _evaluate(q, "", job_title)
            try:
                _save_answer(cid, jid, idx, q, "", "", ev)
            except Exception as e:
                logger.warning("voice_screening_answers insert failed: %s", e)
            ss["vs_history"].append({
                "question":   q,
                "transcript": "",
                "audio_path": "",
                "evaluation": ev,
            })
            ss["vs_index"]    += 1
            ss["vs_current_q"] = None
            ss["vs_done"]      = ss["vs_index"] >= _TOTAL
            st.rerun()
