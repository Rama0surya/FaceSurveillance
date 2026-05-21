"""
Face Surveillance API — main application entry point.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services.detection import detection_engine
from app.services import stats_broadcaster
from app.services.system_info import system_info_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Lifespan: startup / shutdown hooks
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    # ---- Startup ----
    logger.info("Starting Face Surveillance API …")

    # Ensure local snapshot directory exists
    os.makedirs(settings.SNAPSHOT_LOCAL_DIR, exist_ok=True)

    # Start the periodic stats broadcaster
    stats_broadcaster.start()

    # Seed default alert rules if none exist
    from app.services.alert_engine import seed_default_rules
    seed_default_rules()

    # Load AI models (YOLO, InsightFace) — once at startup, shared across all workers
    from app.services.model_manager import model_manager
    model_manager.load_models()

    # Start the system-info background cache (polls every 60s)
    import asyncio
    system_info_cache.start(loop=asyncio.get_running_loop())

    logger.info("API ready ✓")

    yield

    # ---- Shutdown ----
    logger.info("Shutting down …")

    # Stop all active camera streams
    detection_engine.stop_all()

    # Cancel the stats broadcaster
    stats_broadcaster.stop()

    # Stop system-info polling
    system_info_cache.stop()

    logger.info("Shutdown complete ✓")


# ------------------------------------------------------------------
# App instance
# ------------------------------------------------------------------

app = FastAPI(
    title="Face Surveillance API",
    description="Real-time face detection, emotion/age/gender analysis from RTSP/HLS camera streams",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve local snapshots as static files
snapshots_dir = os.path.abspath(settings.SNAPSHOT_LOCAL_DIR)
os.makedirs(snapshots_dir, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=snapshots_dir), name="snapshots")

# ------------------------------------------------------------------
# Register routers
# ------------------------------------------------------------------

from app.routes.cameras import router as cameras_router      # noqa: E402
from app.routes.detections import router as detections_router  # noqa: E402
from app.routes.stats import router as stats_router            # noqa: E402
from app.routes.websocket import router as ws_router           # noqa: E402
from app.routes.debug import router as debug_router            # noqa: E402
from app.routes.alerts import router as alerts_router          # noqa: E402
from app.routes.settings import router as settings_router      # noqa: E402

app.include_router(cameras_router)
app.include_router(detections_router)
app.include_router(stats_router)
app.include_router(ws_router)
app.include_router(alerts_router)
app.include_router(settings_router)

# Debug routes (mock data) — only in development
if os.getenv("ENV", "development").lower() != "production":
    app.include_router(debug_router)
    logger.info("Debug routes enabled (development mode)")


# ------------------------------------------------------------------
# Health-check root
# ------------------------------------------------------------------

@app.get("/", tags=["health"])
async def root():
    return {
        "message": "Face Surveillance API is running",
        "version": "1.0.0",
    }
