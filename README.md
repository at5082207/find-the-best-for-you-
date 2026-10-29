# FIND THE BEST FOR YOU

This folder contains the supplied HTML frontend and a Python FastAPI + SQLite starter backend.

## Project files

- `frontend/index.html` — original supplied frontend.
- `main.py` — FastAPI API and static frontend serving.
- `requirements.txt` — Python dependencies.
- `render.yaml` — starter Render deployment configuration.
- `.gitignore` — excludes virtual environments, local databases, and secrets.

## Run on Windows PowerShell

Open PowerShell in this project folder, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:

- Website: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

If Python 3.12 is not installed, install it first. Python 3.12 is recommended for dependency compatibility.

## API endpoints in this starter

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `GET /api/schemes`
- `POST /api/search`
- `POST /api/emi`
- `POST /api/eligibility`
- `GET/POST /api/saved`
- `DELETE /api/saved/{scheme_id}`
- `GET/POST /api/applications`
- `POST /api/feedback`
- `POST /api/documents/check`

## Important status

The backend is provided as an MVP starter and serves the supplied frontend at `/`. The frontend currently retains many of its own browser-side/localStorage behaviours; its login, saved schemes, applications, feedback, and calculators are **not all wired to these API endpoints yet**. The starter scheme catalogue is limited example data, not a live government database. Document upload currently validates and receives the file but does not save it or run OCR.

Before public production use, review authentication/session handling, restrict CORS, configure persistent database storage, add rate limiting and backups, and verify scheme eligibility/official links. Do not put secrets or real user data in a public repository.

## Deploy on Render

Push this repository to GitHub, then create a Render Web Service from that repository. Build command:

`pip install -r requirements.txt`

Start command:

`uvicorn main:app --host 0.0.0.0 --port $PORT`

For production, configure a persistent database path/storage and review CORS/security settings before collecting real user information.
