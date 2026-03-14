"""
DevFlow AI — FastAPI application entry point.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # load .env before anything reads os.getenv()

# Ensure src/ flat imports (from sentiment_analyzer import ...) resolve correctly.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import stories, health
from api.routes.auth import router as auth_router
from api.routes.workspaces import router as workspaces_router
from api.routes.dashboard import router as dashboard_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist (creates them on first run; Alembic handles
    # subsequent migrations in production).
    from db.models import Base
    from db.session import engine
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified.")

    from pipeline import MultiModelPipeline
    logger.info("Loading pipeline — Whisper + priority detector + story generator...")
    # Jira export is handled per-request using each workspace's DB credentials,
    # so we do NOT load a shared exporter at startup.
    app.state.pipeline = MultiModelPipeline.create(enable_jira=False, load_transcriber=True)
    logger.info("Pipeline ready. Server accepting requests.")
    yield


app = FastAPI(title="DevFlow AI", version="0.1.0", lifespan=lifespan)

app.include_router(stories.router, prefix="/stories", tags=["stories"])
app.include_router(health.router, tags=["health"])
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(dashboard_router)

_frontend = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(_frontend / "index.html"))