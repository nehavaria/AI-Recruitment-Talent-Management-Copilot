"""Centralized application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # loads .env from project root

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
LOG_PATH   = DATA_DIR / "app.log"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Environment ────────────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development | production
IS_PROD     = ENVIRONMENT == "production"

# ── App metadata ───────────────────────────────────────────────────────────
APP_TITLE = "AI Recruitment & Talent Management Copilot"
APP_ICON  = "🤖"

# ──────────────────────────────────────────────────────────────────────────
#  MySQL Configuration  (values loaded from .env / platform secrets)
# ──────────────────────────────────────────────────────────────────────────
MYSQL_HOST     = os.getenv("MYSQL_HOST",     "localhost")
MYSQL_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "myrecruitment")
MYSQL_USER     = os.getenv("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_SSL_CA   = os.getenv("MYSQL_SSL_CA",   "")  # path to CA cert for cloud MySQL
# ──────────────────────────────────────────────────────────────────────────

# ── CORS (comma-separated list of allowed origins) ─────────────────────────
_raw_origins    = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ── Gemini API ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── Groq API ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Parser ─────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx"})
SPACY_MODEL = "en_core_web_sm"

# ── Skill taxonomy (extendable) ────────────────────────────────────────────
KNOWN_SKILLS: frozenset[str] = frozenset({
    # Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "kotlin", "swift", "r", "scala", "php", "ruby",
    # Web
    "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    "html", "css", "rest", "graphql",
    # Data / ML
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "spark", "hadoop", "airflow", "dbt",
    # Cloud / DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "ci/cd", "jenkins", "github actions",
    # Other
    "git", "linux", "agile", "scrum", "jira", "tableau", "power bi",
})
