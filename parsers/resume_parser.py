"""Raw text extraction from PDF and DOCX resume files."""

import logging
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document

from config.settings import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


class ResumeParser:
    """Extracts plain text from PDF or DOCX resume files."""

    def parse(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {suffix}")
        if suffix == ".pdf":
            return self._parse_pdf(file_path)
        return self._parse_docx(file_path)

    def _parse_pdf(self, path: Path) -> str:
        text_parts: list[str] = []
        with fitz.open(str(path)) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        text = "\n".join(text_parts).strip()
        logger.debug("PDF parsed: %s (%d chars)", path.name, len(text))
        return text

    def _parse_docx(self, path: Path) -> str:
        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        logger.debug("DOCX parsed: %s (%d chars)", path.name, len(text))
        return text
