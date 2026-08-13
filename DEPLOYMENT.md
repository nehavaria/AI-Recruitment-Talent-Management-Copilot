# Deployment Guide — AI Recruitment & Talent Management Copilot

## Architecture

```
Streamlit Community Cloud          Render / Railway
        ↓                                  ↓
  Streamlit Dashboard  ←────────  FastAPI Backend (main.py)
                                           ↓
                                  MySQL Cloud Database
                                  (PlanetScale / Aiven / Railway MySQL)
```

---

## 1. MySQL Cloud Database

### Recommended providers (free tier available)
| Provider     | Free tier | Notes |
|---|---|---|
| PlanetScale  | 5 GB      | Serverless, requires SSL |
| Aiven        | 1 GB      | Requires SSL CA cert |
| Railway      | 1 GB      | Easiest setup |
| Clever Cloud | 10 MB     | Simple |

### Steps
1. Create a MySQL database on your chosen provider
2. Note the **host, port, database name, user, password**
3. If SSL is required, download the **CA certificate** file
4. Your existing schema is created automatically on first run — no migration needed

---

## 2. FastAPI Backend → Render

### Steps
1. Go to https://render.com → New → Web Service
2. Connect your GitHub repo: `nehavaria/AI-Recruitment-Talent-Management-Copilot`
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
4. Add environment variables (Environment → Add Secret):

```
ENVIRONMENT        = production
MYSQL_HOST         = <your cloud MySQL host>
MYSQL_PORT         = 3306
MYSQL_DATABASE     = <your database name>
MYSQL_USER         = <your MySQL user>
MYSQL_PASSWORD     = <your MySQL password>
MYSQL_SSL_CA       = <path to CA cert, or leave blank>
ALLOWED_ORIGINS    = https://<your-app>.streamlit.app
GROQ_API_KEY       = <your Groq key>
GEMINI_API_KEY     = <your Gemini key>
```

5. Deploy — your API will be live at `https://recruitment-api.onrender.com`
6. Verify: visit `https://recruitment-api.onrender.com/health`

### Alternative: Railway
1. Go to https://railway.app → New Project → Deploy from GitHub
2. Select your repo
3. Add the same environment variables above
4. Railway auto-detects the `Procfile` and deploys

---

## 3. Streamlit Dashboard → Streamlit Community Cloud

### Steps
1. Go to https://share.streamlit.io
2. Click **New app** → Connect GitHub repo
3. Set:
   - **Repository:** `nehavaria/AI-Recruitment-Talent-Management-Copilot`
   - **Branch:** `main`
   - **Main file:** `app.py`
4. Click **Advanced settings** → add secrets in TOML format:

```toml
ENVIRONMENT = "production"

MYSQL_HOST     = "your-cloud-mysql-host"
MYSQL_PORT     = "3306"
MYSQL_DATABASE = "myrecruitment"
MYSQL_USER     = "your-user"
MYSQL_PASSWORD = "your-password"
MYSQL_SSL_CA   = ""

ALLOWED_ORIGINS = "https://your-app.streamlit.app"

GROQ_API_KEY   = "your-groq-key"
GEMINI_API_KEY = "your-gemini-key"
```

5. Deploy — your dashboard will be live at `https://<your-app>.streamlit.app`

---

## 4. Local Development (unchanged)

```bash
# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run Streamlit dashboard
streamlit run app.py

# Run FastAPI backend (separate terminal)
uvicorn main:app --reload
```

Local `.env` file is used automatically — no changes needed.

---

## 5. Environment Variables Reference

| Variable         | Required | Description |
|---|---|---|
| `ENVIRONMENT`    | No       | `development` or `production` (default: development) |
| `MYSQL_HOST`     | Yes      | MySQL server hostname |
| `MYSQL_PORT`     | No       | MySQL port (default: 3306) |
| `MYSQL_DATABASE` | Yes      | Database name |
| `MYSQL_USER`     | Yes      | MySQL username |
| `MYSQL_PASSWORD` | Yes      | MySQL password |
| `MYSQL_SSL_CA`   | No       | Path to SSL CA cert (cloud MySQL only) |
| `ALLOWED_ORIGINS`| No       | Comma-separated CORS origins |
| `GROQ_API_KEY`   | Yes      | Groq API key |
| `GEMINI_API_KEY` | Yes      | Google Gemini API key |

---

## 6. Health Check

FastAPI exposes a health check at `GET /health`:

```json
{
  "status": "ok",
  "environment": "production",
  "database": "connected",
  "timestamp": 1234567890
}
```

Render and Railway use this endpoint to monitor uptime.

---

## 7. Security Notes

- `.env` is gitignored — never committed
- Swagger UI (`/docs`) is disabled in production
- CORS is restricted to `ALLOWED_ORIGINS` only
- MySQL SSL is enabled when `MYSQL_SSL_CA` is set
- All secrets are injected via platform environment variables
