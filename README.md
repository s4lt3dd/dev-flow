# DevFlow AI

Turn meeting transcripts and audio recordings into Jira-ready user stories using a multi-model AI pipeline.

## Overview

DevFlow AI listens to your requirements discussions and automatically generates structured user stories in the Connextra format, assigns priorities, estimates story points, evaluates story quality using the QUS framework, and optionally exports directly to Jira.

**Pipeline:**
1. **Transcription** — OpenAI Whisper converts audio to text
2. **Sentiment Analysis** — detects urgency and tone signals
3. **Priority Detection** — ensemble model assigns High / Medium / Low
4. **Story Generation** — Llama 3.2 via Ollama generates structured user stories
5. **QUS Evaluation** — scores each story against 6 quality criteria (Well-formed, Atomic, Minimal, Complete, Testable, Estimable)
6. **Jira Export** — pushes stories to your Jira project

## Features

- Generate user stories from typed transcripts or live audio recordings
- Per-story QUS quality scores with criterion-level breakdown
- Dashboard with priority analytics, session history, and quality trends
- Jira integration with automatic issue creation
- Auth0-based authentication with per-workspace isolation

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| AI Models | Llama 3.2 (Ollama), OpenAI Whisper, HuggingFace Transformers |
| Database | SQLite + SQLAlchemy + Alembic |
| Auth | Auth0 (JWT) |
| Frontend | Vanilla HTML / CSS / JS (SPA) |

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with `llama3.2` pulled
- Auth0 account (free tier works)
- Jira account (optional)

## Setup

**1. Clone and create a virtual environment**

```bash
git clone <repo-url>
cd devflow
python -m venv env
source env/bin/activate        # Windows: env\Scripts\activate
pip install -r requirements.txt
```

**2. Configure environment variables**

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
# Auth0
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_AUDIENCE=https://your-api-identifier

# Encryption key for storing Jira credentials (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=

# Jira (optional — can also be configured per-workspace in the UI)
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=PROJ
```

**3. Pull the Ollama model**

```bash
ollama pull llama3.2
```

**4. Run database migrations**

```bash
alembic upgrade head
```

**5. Start the server**

```bash
uvicorn api.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## Project Structure

```
devflow/
├── api/                  # FastAPI app
│   ├── main.py           # Entry point, static file serving
│   ├── dependencies.py   # Auth0 JWT validation
│   └── routes/
│       ├── stories.py    # POST /stories/from-text, /from-audio
│       ├── dashboard.py  # GET /dashboard/stats, /stories, /sessions
│       ├── auth.py       # Auth0 config + user registration
│       └── workspaces.py # Workspace & Jira config
├── src/                  # AI pipeline modules
│   ├── pipeline.py       # MultiModelPipeline orchestrator
│   ├── transcriber.py    # Whisper wrapper
│   ├── sentiment_analyzer.py
│   ├── advanced_priority_detector.py
│   ├── story_generator.py
│   ├── evaluation.py     # QUS framework (StoryEvaluator)
│   └── jira_exporter.py
├── db/
│   ├── models.py         # SQLAlchemy ORM models
│   ├── session.py        # DB connection
│   └── migrations/       # Alembic migrations
├── frontend/             # Single-page app
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/                # Pytest unit tests
├── demo.py               # Interactive CLI demo
└── requirements.txt
```

## Running Tests

```bash
pytest
```

## QUS Framework

Each generated story is scored against the [Quality User Story (QUS) framework](https://doi.org/10.1007/s10270-016-0541-x) (Lucassen et al., 2016):

| Criterion | Description |
|---|---|
| **Well-formed** | Follows "As a… I want… So that…" Connextra format |
| **Atomic** | Addresses a single feature (no compound requirements) |
| **Minimal** | Concise — ideally 15–30 words |
| **Complete** | Has role, goal, benefit, and ≥ 3 acceptance criteria |
| **Testable** | Acceptance criteria are measurable and verifiable |
| **Estimable** | Story points use Fibonacci scale and match complexity |

Scores are displayed per-story on generated cards and aggregated on the dashboard.
