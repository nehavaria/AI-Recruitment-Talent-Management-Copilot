"""Extracts structured candidate profile fields from raw resume text."""

import re
import logging
from dataclasses import dataclass, field
from typing import Any

import spacy

from config.settings import KNOWN_SKILLS, SPACY_MODEL

logger = logging.getLogger(__name__)

# ── Compiled patterns ──────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
)
_SECTION_HEADERS = re.compile(
    r"^(experience|work history|employment|education|skills|summary|objective|"
    r"profile|projects|certifications|achievements)\s*[:\-]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class CandidateProfile:
    """Structured representation of a parsed resume."""

    name:           str       = ""
    email:          str       = ""
    phone:          str       = ""
    location:       str       = ""
    summary:        str       = ""
    skills:         list[str] = field(default_factory=list)
    experience:     list[str] = field(default_factory=list)
    education:      list[str] = field(default_factory=list)
    projects:       list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    resume_path:    str       = ""

    def to_db_dict(self, file_name: str = "", resume_path: str = "") -> dict[str, Any]:
        """Serialize to a flat dict ready for DatabaseManager insertion."""
        return {
            "name":           self.name,
            "email":          self.email.lower(),
            "phone":          self.phone,
            "education":      "\n".join(self.education),
            "skills":         ", ".join(self.skills),
            "experience":     "\n".join(self.experience),
            "projects":       "\n".join(self.projects),
            "certifications": "\n".join(self.certifications),
            "resume_path":    resume_path or self.resume_path or file_name,
        }


# ── Extractor ──────────────────────────────────────────────────────────────

class ProfileExtractor:
    """Uses spaCy NER + regex to extract structured fields from resume text."""

    def __init__(self) -> None:
        try:
            self._nlp = spacy.load(SPACY_MODEL)
        except OSError:
            logger.warning(
                "spaCy model '%s' not found — NER disabled. "
                "Run: python -m spacy download %s",
                SPACY_MODEL, SPACY_MODEL,
            )
            self._nlp = None

    def extract(self, text: str) -> CandidateProfile:
        """Return a CandidateProfile populated from raw resume text."""
        profile = CandidateProfile()
        profile.email  = self._extract_email(text)
        profile.phone  = self._extract_phone(text)
        profile.skills = self._extract_skills(text)

        if self._nlp:
            doc = self._nlp(text[:5000])   # cap for performance
            profile.name     = self._extract_name(doc)
            profile.location = self._extract_location(doc)

        sections = self._split_sections(text)
        profile.summary = sections.get(
            "summary", sections.get("objective", sections.get("profile", ""))
        )[:500]
        profile.experience = self._extract_section_bullets(
            sections.get("experience",
                sections.get("work history",
                    sections.get("employment", "")))
        )
        profile.education      = self._extract_section_bullets(sections.get("education", ""))
        profile.projects       = self._extract_section_bullets(sections.get("projects", ""))
        profile.certifications = self._extract_section_bullets(
            sections.get("certifications", sections.get("achievements", ""))
        )
        return profile

    # ── Private helpers ────────────────────────────────────────────────────

    def _extract_email(self, text: str) -> str:
        m = _EMAIL_RE.search(text)
        return m.group(0).lower() if m else ""

    def _extract_phone(self, text: str) -> str:
        m = _PHONE_RE.search(text)
        return m.group(0).strip() if m else ""

    def _extract_skills(self, text: str) -> list[str]:
        lower = text.lower()
        return sorted({s for s in KNOWN_SKILLS if re.search(rf"\b{re.escape(s)}\b", lower)})

    def _extract_name(self, doc: Any) -> str:
        # Try spaCy PERSON entity — take first line only (guards multi-line matches)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.splitlines()[0].strip()
                if name and len(name.split()) <= 5:
                    return name
        # Fallback: first non-empty short line that has no digits/email/phone
        for line in doc.text.splitlines():
            line = line.strip()
            if (
                line
                and 1 < len(line.split()) <= 4
                and not _EMAIL_RE.search(line)
                and not re.search(r"\d", line)
                and not re.search(
                    r"(engineer|developer|analyst|manager|intern|contact|summary|"
                    r"profile|objective|skills|education|experience|projects)",
                    line, re.IGNORECASE
                )
            ):
                return line
        return ""

    def _extract_location(self, doc: Any) -> str:
        for ent in doc.ents:
            if ent.label_ in {"GPE", "LOC"}:
                return ent.text.strip()
        return ""

    def _split_sections(self, text: str) -> dict[str, str]:
        """Partition resume text into named sections keyed by header."""
        sections: dict[str, str] = {}
        current_key: str | None  = None
        buffer: list[str]        = []

        for line in text.splitlines():
            m = _SECTION_HEADERS.match(line.strip())
            if m:
                if current_key and buffer:
                    sections[current_key] = "\n".join(buffer).strip()
                current_key = m.group(1).lower()
                buffer = []
            elif current_key is not None:
                buffer.append(line)

        if current_key and buffer:
            sections[current_key] = "\n".join(buffer).strip()

        return sections

    def _extract_section_bullets(self, section_text: str) -> list[str]:
        if not section_text:
            return []
        lines = [
            re.sub(r"^[\s•\-\*\u2022]+", "", ln).strip()
            for ln in section_text.splitlines()
            if ln.strip()
        ]
        return [ln for ln in lines if len(ln) > 5][:15]
