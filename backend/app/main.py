import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.cuda_init import register_nvidia_dll_directories
register_nvidia_dll_directories()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import FRONTEND_DIST_DIR, DEFAULT_HOST, DEFAULT_PORT
from app.core.database import init_db
from app.api.health import router as health_router
from app.api.hardware import router as hardware_router
from app.api.models import router as models_router
from app.api.audio import router as audio_router
from app.api.transcription import router as transcription_router
from app.api.conversion import router as conversion_router
from app.api.history import router as history_router
from app.api.exports import router as exports_router
from app.api.benchmark import router as benchmark_router
from app.api.review import router as review_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("verbatim.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Verbatim AI backend...")
    init_db()
    logger.info("Storage & database ready.")
    yield
    # Shutdown
    logger.info("Shutting down Verbatim AI backend.")


app = FastAPI(
    title="Verbatim AI",
    description="Local AI Transcription & Audio Conversion Application — Every Word Matters.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router)
app.include_router(hardware_router)
app.include_router(models_router)
app.include_router(audio_router)
app.include_router(transcription_router)
app.include_router(conversion_router)
app.include_router(history_router)
app.include_router(exports_router)
app.include_router(benchmark_router)
app.include_router(review_router)


# Mount Static Frontend if built
if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Allow API routes to be handled by routers
        if full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        # If a specific static file in dist is requested (favicon, robots, etc.)
        direct_file = FRONTEND_DIST_DIR / full_path
        if full_path and direct_file.is_file():
            return FileResponse(direct_file)

        # Fallback to index.html for client-side routing
        index_file = FRONTEND_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        return JSONResponse(status_code=404, content={"detail": "Frontend not built yet"})
else:
    logger.info("Frontend dist directory not found at %s. API server running in standalone mode.", FRONTEND_DIST_DIR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)
