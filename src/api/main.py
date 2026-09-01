"""
FastAPI application — Call Quality Agent API.

Start with:
    uvicorn src.api.main:app --reload --port 8000

Or from the project root:
    python -m uvicorn src.api.main:app --reload --port 8000

All routes are mounted under /api/*. Interactive docs are available at:
    http://localhost:8000/docs      (Swagger UI)
    http://localhost:8000/redoc     (ReDoc)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import init_db
from src.api.routes import analyze, clean, pipeline, report, stt

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    On startup:
      - Create all DB tables (idempotent).
      - Resume any pipeline jobs that were in-progress when the server last
        stopped (handles server restarts mid-pipeline).

    On shutdown:
      - Nothing to clean up — SQLite handles its own flushing.
    """
    # Startup
    init_db()
    from src.api.routes.pipeline import resume_stuck_pipelines
    resume_stuck_pipelines()

    yield

    # Shutdown (nothing needed)


app = FastAPI(
    title="Call Quality Agent API",
    description=(
        "Sales call QA pipeline for Accredian. "
        "Transcribes audio via Google Cloud STT, cleans transcripts, "
        "analyzes them against course data via OpenRouter LLM, and "
        "generates structured QA reports."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# Allow all origins in development. Restrict to your frontend domain in prod.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(stt.router)
app.include_router(pipeline.router)
app.include_router(clean.router)
app.include_router(analyze.router)
app.include_router(report.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe — returns 200 if the server is up."""
    return {"status": "ok", "version": APP_VERSION}


@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "Call Quality Agent API",
        "version": APP_VERSION,
        "docs": "/docs",
    }
