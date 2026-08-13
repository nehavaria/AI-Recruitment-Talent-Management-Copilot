"""
AI Interview Simulator — Voice + Text input, Gemini evaluation, transcript.
10 questions · Chat history · Live timer · Progress bar · 6-score evaluation.
"""

import html
import io
import time
import speech_recognition as sr
import google.genai as genai
import streamlit as st
from groq import Groq

from config.settings import GROQ_API_KEY, GEMINI_API_KEY
from services.candidate_service import CandidateService
from ui.components import page_header, empty_state
from milestone3.interview_db import init_db, save_report

_GROQ_CLIENT = None
_TOTAL = 10


def _groq():
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        from config.settings import GROQ_API_KEY as _KEY
        _GROQ_CLIENT = Groq(api_key=_KEY)
    return _GROQ_CLIENT


def _use_gemini() -> bool:
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())


def _gemini_generate(prompt: str) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    return client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text.strip()


def _transcribe(audio_bytes: bytes) -> str:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as src:
            audio = recognizer.record(src)
        return recognizer.recognize_google(audio)
    except Exception:
        return ""


def _generate_question(candidate: dict, job: dict, history: list[dict], q_num: int) -> str:
    skills    = candidate.get("skills") or "general"
    job_title = job.get("job_title") or "Software Engineer"
    prev      = "\n".join(f"Q: {h['question']}" for h in history[-3:]) if history else "None yet."
    system = (
        f"You are a senior technical interviewer for the role of {job_title}. "
        f"Candidate skills: {skills}. "
        f"Ask ONE concise interview question (question {q_num} of {_TOTAL}). "
        f"Vary types: technical, behavioural, situational. No repeats. "
        f"Previous questions:\n{prev}\nReply with ONLY the question."
    )
    resp = _groq().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}],
        max_tokens=200,
    )
    return resp.choices[0].message.content.strip()


def _evaluate(question: str, answer: str, job_title: str) -> dict:
    empty = {
        "score": 0, "level": "No Answer", "color": "#ef4444",
        "feedback": "No answer provided.", "improvements": [],
        "technical": 0, "communication": 0, "confidence": 0,
        "problem_solving": 0, "grammar": 0,
        "technical_why": "", "communication_why": "", "confidence_why": "",
        "problem_solving_why": "", "grammar_why": "",
    }
    if not answer.strip():
        return empty

    prompt = (
        f"You are an expert interview evaluator for the role of {job_title}.\n"
        f"Question: {question}\nAnswer: {answer}\n\n"
        "Evaluate across 5 dimensions and give an overall score.\n"
        "Reply in this EXACT format only:\n"
        "TECHNICAL: <0-100>\n"
        "TECHNICAL_WHY: <one sentence>\n"
        "COMMUNICATION: <0-100>\n"
        "COMMUNICATION_WHY: <one sentence>\n"
        "CONFIDENCE: <0-100>\n"
        "CONFIDENCE_WHY: <one sentence>\n"
        "PROBLEM_SOLVING: <0-100>\n"
        "PROBLEM_SOLVING_WHY: <one sentence>\n"
        "GRAMMAR: <0-100>\n"
        "GRAMMAR_WHY: <one sentence>\n"
        "OVERALL: <0-100>\n"
        "LEVEL: <Excellent|Good|Average|Needs Improvement|Weak>\n"
        "FEEDBACK: <2-3 sentence overall feedback>\n"
        "IMPROVEMENT1: <first improvement suggestion>\n"
        "IMPROVEMENT2: <second improvement suggestion>\n"
        "IMPROVEMENT3: <third improvement suggestion>"
    )

    try:
        if _use_gemini():
            try:
                raw = _gemini_generate(prompt)
            except Exception:
                raw = _groq().chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=600,
                ).choices[0].message.content.strip()
        else:
            raw = _groq().chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
            ).choices[0].message.content.strip()
    except Exception as e:
        return {**empty, "score": 50, "level": "Average", "color": "#f59e0b",
                "feedback": f"Evaluation error: {e}",
                "technical": 50, "communication": 50, "confidence": 50,
                "problem_solving": 50, "grammar": 50}

    def _int(val):
        try: return max(0, min(100, int(val.strip())))
        except: return 50

    result = {
        "score": 50, "level": "Average", "color": "#f59e0b", "feedback": "",
        "improvements": [],
        "technical": 50, "communication": 50, "confidence": 50,
        "problem_solving": 50, "grammar": 50,
        "technical_why": "", "communication_why": "", "confidence_why": "",
        "problem_solving_why": "", "grammar_why": "",
    }
    for line in raw.splitlines():
        line = line.strip()
        if   line.startswith("TECHNICAL:"):           result["technical"]           = _int(line.split(":",1)[1])
        elif line.startswith("TECHNICAL_WHY:"):       result["technical_why"]       = line.split(":",1)[1].strip()
        elif line.startswith("COMMUNICATION:"):       result["communication"]        = _int(line.split(":",1)[1])
        elif line.startswith("COMMUNICATION_WHY:"):   result["communication_why"]   = line.split(":",1)[1].strip()
        elif line.startswith("CONFIDENCE:"):          result["confidence"]           = _int(line.split(":",1)[1])
        elif line.startswith("CONFIDENCE_WHY:"):      result["confidence_why"]       = line.split(":",1)[1].strip()
        elif line.startswith("PROBLEM_SOLVING:"):     result["problem_solving"]      = _int(line.split(":",1)[1])
        elif line.startswith("PROBLEM_SOLVING_WHY:"): result["problem_solving_why"] = line.split(":",1)[1].strip()
        elif line.startswith("GRAMMAR:"):             result["grammar"]              = _int(line.split(":",1)[1])
        elif line.startswith("GRAMMAR_WHY:"):         result["grammar_why"]          = line.split(":",1)[1].strip()
        elif line.startswith("OVERALL:"):             result["score"]                = _int(line.split(":",1)[1])
        elif line.startswith("LEVEL:"):               result["level"]                = line.split(":",1)[1].strip()
        elif line.startswith("FEEDBACK:"):            result["feedback"]             = line.split(":",1)[1].strip()
        elif line.startswith("IMPROVEMENT"):          result["improvements"].append(line.split(":",1)[1].strip())

    s = result["score"]
    result["color"] = "#10b981" if s >= 70 else "#f59e0b" if s >= 40 else "#ef4444"
    return result


# ── UI helpers ─────────────────────────────────────────────────────────────

def _progress_bar(idx: int, total: int, cand: str, job: str, elapsed: int) -> None:
    pct        = int((idx / total) * 100)
    mins, secs = elapsed // 60, elapsed % 60
    st.markdown(
        f"<div style='margin-bottom:18px'>"
        f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;color:#94a3b8;margin-bottom:6px'>"
        f"<span>🎤 <b style='color:#e2e8f0'>{html.escape(cand)}</b> — {html.escape(job)}</span>"
        f"<span style='display:flex;gap:14px'><span>❓ {idx}/{total}</span><span>⏱️ {mins:02d}:{secs:02d}</span></span>"
        f"</div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:8px;overflow:hidden'>"
        f"<div style='background:linear-gradient(90deg,#7c3aed,#2563eb);height:100%;width:{pct}%;border-radius:20px;transition:width 0.4s ease'></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _chat_bubble(role: str, text: str, score: int | None = None, via: str = "") -> None:
    if role == "ai":
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
    else:
        clr       = "#10b981" if score and score >= 70 else "#f59e0b" if score and score >= 40 else "#94a3b8"
        badge     = f"<span style='font-size:0.65rem;background:{clr}20;color:{clr};padding:2px 8px;border-radius:10px;margin-left:6px;font-weight:700'>{score}%</span>" if score is not None else ""
        via_badge = f"<span style='font-size:0.6rem;background:rgba(14,165,233,0.15);color:#38bdf8;padding:1px 7px;border-radius:8px;margin-left:4px'>{'🎙 voice' if via=='voice' else '⌨ text'}</span>" if via else ""
        st.markdown(
            f"<div style='display:flex;gap:10px;margin-bottom:6px;flex-direction:row-reverse'>"
            f"<div style='width:36px;height:36px;border-radius:10px;flex-shrink:0;"
            f"background:linear-gradient(135deg,#0ea5e9,#10b981);"
            f"display:flex;align-items:center;justify-content:center;font-size:1.1rem'>👤</div>"
            f"<div style='background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.2);"
            f"border-radius:14px 0 14px 14px;padding:12px 16px;max-width:85%;text-align:right'>"
            f"<div style='font-size:0.93rem;color:#f1f5f9;line-height:1.6'>{html.escape(text)}{badge}{via_badge}</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )


def _score_bar(label: str, score: int, why: str) -> str:
    clr      = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    why_html = f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:3px'>{html.escape(why)}</div>" if why else ""
    return (
        f"<div style='margin-bottom:12px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px'>"
        f"<span style='font-size:0.8rem;font-weight:600;color:#e2e8f0'>{label}</span>"
        f"<span style='font-size:0.8rem;font-weight:800;color:{clr}'>{score}%</span>"
        f"</div>"
        f"<div style='background:rgba(255,255,255,0.08);border-radius:20px;height:6px;overflow:hidden'>"
        f"<div style='background:{clr};height:100%;width:{score}%;border-radius:20px'></div>"
        f"</div>{why_html}</div>"
    )


def _feedback_card(ev: dict) -> None:
    clr    = ev["color"]
    engine = "🔮 Gemini" if _use_gemini() else "🤖 Groq"

    bars = (
        _score_bar("🛠 Technical",       ev.get("technical", 0),       ev.get("technical_why", "")) +
        _score_bar("🗣 Communication",   ev.get("communication", 0),   ev.get("communication_why", "")) +
        _score_bar("💪 Confidence",      ev.get("confidence", 0),      ev.get("confidence_why", "")) +
        _score_bar("🧩 Problem Solving", ev.get("problem_solving", 0), ev.get("problem_solving_why", "")) +
        _score_bar("✍️ Grammar",         ev.get("grammar", 0),         ev.get("grammar_why", ""))
    )

    improvements = [i for i in ev.get("improvements", []) if i]
    imp_html = ""
    if improvements:
        items    = "".join(f"<li style='margin-bottom:5px'>{html.escape(i)}</li>" for i in improvements)
        imp_html = (
            f"<div style='margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08)'>"
            f"<div style='font-size:0.72rem;font-weight:700;color:#a78bfa;text-transform:uppercase;"
            f"letter-spacing:0.08em;margin-bottom:8px'>💡 Improvement Suggestions</div>"
            f"<ul style='margin:0;padding-left:18px;font-size:0.82rem;color:#cbd5e1;line-height:1.7'>{items}</ul></div>"
        )

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.03);border-radius:14px;padding:18px 20px;"
        f"border-left:4px solid {clr};border:1px solid {clr}30;margin:6px 0 18px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'>"
        f"<span style='font-size:0.7rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em'>{engine} Evaluation</span>"
        f"<span style='background:{clr}20;color:{clr};font-weight:800;font-size:0.82rem;padding:4px 14px;border-radius:20px;border:1px solid {clr}40'>"
        f"Overall {ev['score']}% — {ev['level']}</span></div>"
        f"{bars}"
        f"<div style='margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08)'>"
        f"<div style='font-size:0.72rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px'>📝 Overall Feedback</div>"
        f"<div style='font-size:0.85rem;color:#cbd5e1;line-height:1.6'>{html.escape(ev.get('feedback', ''))}</div></div>"
        f"{imp_html}</div>",
        unsafe_allow_html=True,
    )


def _transcript_panel(history: list[dict]) -> None:
    lines = []
    for i, h in enumerate(history):
        ev = h.get("evaluation", {})
        lines.append(f"Q{i+1} [{h.get('via','text').upper()}]: {h['question']}")
        lines.append(f"A: {h.get('answer') or '(skipped)'}")
        lines.append(f"Overall: {ev.get('score','—')}% | {ev.get('level','—')}")
        lines.append(f"Technical: {ev.get('technical','—')}% | Communication: {ev.get('communication','—')}% | Confidence: {ev.get('confidence','—')}%")
        lines.append(f"Problem Solving: {ev.get('problem_solving','—')}% | Grammar: {ev.get('grammar','—')}%")
        lines.append(f"Feedback: {ev.get('feedback','')}")
        for imp in ev.get("improvements", []):
            lines.append(f"  - {imp}")
        lines.append("")
    st.download_button(
        "📥 Download Transcript",
        data="\n".join(lines),
        file_name="interview_transcript.txt",
        mime="text/plain",
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════════════════════════════════

def render(service: CandidateService) -> None:
    page_header(
        "🤖 AI Interview Simulator",
        f"Voice + Text · {'Gemini' if _use_gemini() else 'Groq'} evaluation · {_TOTAL} questions · 6-score analysis · Live timer",
    )

    candidates = service.get_all_candidates(st.session_state.get("recruiter_email", ""))
    jobs       = service.jobs.get_all_jobs(st.session_state.get("recruiter_email", ""))

    if not candidates:
        empty_state("No candidates found — upload resumes first.")
        return
    if not jobs:
        empty_state("No jobs found — create a job posting first.")
        return

    ss = st.session_state
    defaults = {
        "ai_active": False, "ai_history": [], "ai_index": 0,
        "ai_done": False, "ai_start_time": None,
        "ai_current_q": None, "ai_awaiting_answer": False,
    }
    for k, v in defaults.items():
        if k not in ss: ss[k] = v

    # ── Setup ──────────────────────────────────────────────────────────────
    if not ss.ai_active:
        with st.container(border=True):
            st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#a78bfa;margin-bottom:16px'>⚙️ Interview Setup</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                job_opts = {f"#{j['job_id']} — {j['job_title']}": j for j in jobs}
                sel_job  = job_opts[st.selectbox("💼 Job Role", list(job_opts.keys()), key="ai_job_sel")]
            with c2:
                cand_opts = {f"#{c['candidate_id']} — {(c.get('name') or 'Unknown').splitlines()[0]}": c for c in candidates}
                sel_cand  = cand_opts[st.selectbox("👤 Candidate", list(cand_opts.keys()), key="ai_cand_sel")]

            engine            = "🔮 Gemini" if _use_gemini() else "🤖 Groq"
            cand_name_display = (sel_cand.get("name") or "Unknown").splitlines()[0]
            st.info(f"**{cand_name_display}** is interviewing for **{sel_job['job_title']}** · {_TOTAL} questions · Engine: {engine} · Each answer scored on 6 dimensions")

            if st.button("🚀 Start AI Interview", type="primary", use_container_width=True):
                ss.ai_active          = True
                ss.ai_history         = []
                ss.ai_index           = 0
                ss.ai_done            = False
                ss.ai_start_time      = time.time()
                ss.ai_candidate       = sel_cand
                ss.ai_job             = sel_job
                ss.ai_current_q       = None
                ss.ai_awaiting_answer = False
                st.rerun()
        return

    cand_name = (ss.ai_candidate.get("name") or "Unknown").splitlines()[0]
    job_title = ss.ai_job.get("job_title") or "Engineer"
    elapsed   = int(time.time() - ss.ai_start_time)

    _progress_bar(ss.ai_index, _TOTAL, cand_name, job_title, elapsed)

    # ── Results ────────────────────────────────────────────────────────────
    if ss.ai_done:
        scores   = [h["evaluation"]["score"] for h in ss.ai_history if h.get("evaluation")]
        avg      = round(sum(scores) / len(scores), 1) if scores else 0
        clr      = "#10b981" if avg >= 70 else "#f59e0b" if avg >= 40 else "#ef4444"
        verdict  = "Strong Performance 🎉" if avg >= 70 else "Good Effort 👍" if avg >= 40 else "Needs More Preparation 📚"
        voice_ct = sum(1 for h in ss.ai_history if h.get("via") == "voice")

        # Avg dimension scores
        def _avg_dim(key):
            vals = [h["evaluation"].get(key, 0) for h in ss.ai_history if h.get("evaluation")]
            return round(sum(vals) / len(vals), 1) if vals else 0

        _report = {
            "candidate": ss.ai_candidate, "job": ss.ai_job,
            "answers": [{"question": h["question"], "answer": h.get("answer",""),
                         "skill": h.get("via","General"), "evaluation": h.get("evaluation",{}), "ideal": ""}
                        for h in ss.ai_history],
            "avg_score": avg, "verdict": verdict,
        }
        st.session_state.sim_last_report = _report
        # ── Persist to SQLite so report survives page refresh ──
        try:
            init_db()
            save_report(_report)
        except Exception as _e:
            pass  # never crash the simulator over a save failure

        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(37,99,235,0.1));"
            f"border-radius:20px;padding:32px;border:1px solid rgba(124,58,237,0.3);text-align:center;margin-bottom:20px'>"
            f"<div style='font-size:3.5rem;font-weight:900;color:{clr}'>{avg}%</div>"
            f"<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-top:8px'>{verdict}</div>"
            f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:6px'>"
            f"⏱️ {elapsed//60:02d}:{elapsed%60:02d} · {_TOTAL} questions · 🎙 {voice_ct} voice · ⌨ {_TOTAL-voice_ct} text"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        # Avg dimension breakdown
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("🛠 Technical",       f"{_avg_dim('technical')}%")
        d2.metric("🗣 Communication",   f"{_avg_dim('communication')}%")
        d3.metric("💪 Confidence",      f"{_avg_dim('confidence')}%")
        d4.metric("🧩 Problem Solving", f"{_avg_dim('problem_solving')}%")
        d5.metric("✍️ Grammar",         f"{_avg_dim('grammar')}%")

        st.divider()
        _transcript_panel(ss.ai_history)
        st.divider()

        st.markdown("<div style='font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:12px'>📋 Full Interview Review</div>", unsafe_allow_html=True)
        for i, h in enumerate(ss.ai_history):
            ev  = h.get("evaluation", {})
            via = "🎙" if h.get("via") == "voice" else "⌨"
            with st.expander(f"{via} Q{i+1}: {h['question'][:65]}… — Overall {ev.get('score','—')}%"):
                if h.get("via") == "voice" and h.get("transcript"):
                    st.markdown(f"**🎙 Voice Transcript:** _{h['transcript']}_")
                st.markdown(f"**Answer:** {h.get('answer') or '_Skipped_'}")
                if ev:
                    _feedback_card(ev)

        if st.button("🔄 New Interview", type="primary", use_container_width=True):
            for k in defaults:
                ss[k] = defaults[k]
            st.rerun()
        return

    # ── Chat history ───────────────────────────────────────────────────────
    for h in ss.ai_history:
        _chat_bubble("ai", h["question"])
        if h.get("answer") is not None:
            _chat_bubble("user", h["answer"] or "_(skipped)_",
                         h.get("evaluation", {}).get("score"), h.get("via", "text"))
            if h.get("evaluation"):
                _feedback_card(h["evaluation"])

    # ── Generate question ──────────────────────────────────────────────────
    if ss.ai_current_q is None:
        with st.spinner("🤖 Generating next question…"):
            ss.ai_current_q = _generate_question(ss.ai_candidate, ss.ai_job, ss.ai_history, ss.ai_index + 1)
        ss.ai_awaiting_answer = True
        st.rerun()

    # ── Answer input ───────────────────────────────────────────────────────
    if ss.ai_awaiting_answer:
        _chat_bubble("ai", ss.ai_current_q)

        input_mode   = st.radio("Answer via:", ["⌨️ Text", "🎙️ Voice"], horizontal=True, key=f"mode_{ss.ai_index}")
        final_answer = ""
        transcript   = ""
        via          = "text"
        ready        = False

        if input_mode == "⌨️ Text":
            text_ans = st.text_area("✍️ Your Answer", placeholder="Type your answer here…", height=130, key=f"ai_ans_{ss.ai_index}")
            c1, c2 = st.columns([4, 1])
            with c1:
                if st.button("✅ Submit Answer", type="primary", use_container_width=True, key=f"sub_{ss.ai_index}"):
                    final_answer = text_ans.strip()
                    via, ready   = "text", True
            with c2:
                if st.button("⏭ Skip", use_container_width=True, key=f"skip_{ss.ai_index}"):
                    via, ready = "text", True
        else:
            st.markdown(
                "<div style='background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);"
                "border-radius:12px;padding:14px 18px;margin-bottom:12px;font-size:0.85rem;color:#c4b5fd'>"
                "🎙️ Record your answer as a <b>WAV file</b> and upload below. It will be transcribed automatically.</div>",
                unsafe_allow_html=True,
            )
            audio_file = st.file_uploader("Upload voice answer (WAV)", type=["wav"], key=f"voice_{ss.ai_index}")
            if audio_file:
                st.audio(audio_file)
                with st.spinner("🎙️ Transcribing…"):
                    transcript = _transcribe(audio_file.read())
                if transcript:
                    st.success(f"📝 Transcript: **{transcript}**")
                    final_answer = transcript
                else:
                    st.warning("Could not transcribe. Type your answer below.")
                    final_answer = st.text_input("Fallback answer:", key=f"fallback_{ss.ai_index}")
                if st.button("✅ Submit Voice Answer", type="primary", use_container_width=True, key=f"vsub_{ss.ai_index}"):
                    via, ready = "voice", True

        if ready:
            with st.spinner(f"{'🔮 Gemini' if _use_gemini() else '🤖 Groq'} evaluating across 6 dimensions…"):
                ev = _evaluate(ss.ai_current_q, final_answer, job_title)
            ss.ai_history.append({
                "question": ss.ai_current_q, "answer": final_answer,
                "transcript": transcript, "via": via, "evaluation": ev,
            })
            ss.ai_index          += 1
            ss.ai_current_q       = None
            ss.ai_awaiting_answer = False
            ss.ai_done            = ss.ai_index >= _TOTAL
            st.rerun()

        time.sleep(1)
        st.rerun()
