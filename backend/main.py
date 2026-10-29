"""
Problem2Project AI — Main FastAPI Application
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME}")
    settings.setup_directories()
    await init_db()
    logger.info("Database initialized")
    logger.info(f"AI configured: {settings.ai_configured} ({settings.AI_PROVIDER})")
    logger.info(f"Search configured: {settings.search_configured} ({settings.SEARCH_PROVIDER})")
    logger.info(f"GitHub configured: {settings.github_configured}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI platform that discovers real-world problems and helps build solutions",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ──────────────────────────────────────────────────────────────
from backend.routers import auth, research, projects, approvals, discover

app.include_router(auth.router)
app.include_router(research.router)
app.include_router(discover.router)
app.include_router(projects.router)
app.include_router(approvals.router)


# ── API Health Check ─────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "integrations": {
            "ai": {"configured": settings.ai_configured, "provider": settings.AI_PROVIDER},
            "search": {"configured": settings.search_configured, "provider": settings.SEARCH_PROVIDER},
            "github": {"configured": settings.github_configured},
        },
    }


# ── Static Files (Frontend) ─────────────────────────────────────────────────
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for all non-API routes."""
        # Check if a static file exists
        file_path = frontend_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Fall back to index.html for SPA routing
        return FileResponse(str(frontend_dir / "index.html"))
