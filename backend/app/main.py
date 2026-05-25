"""
Face Surveillance API — main application entry point.
"""

from __future__ import annotations

import asyncio
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
# Auto-resume helper
# ------------------------------------------------------------------

async def _auto_resume_streams() -> None:
    """Re-start detection for every camera that was live/processing when
    the server last shut down.

    Called during startup after all models are loaded. Cameras that were
    'offline' are left alone — only previously-active streams are resumed.

    Each camera gets a short staggered delay so we don't hammer the
    network / CPU with simultaneous RTSP connects on a Raspberry Pi.
    """
    from app.db.cameras import get_cameras, update_camera_status
    from app.routes.cameras import _probe_rtsp

    try:
        cameras = get_cameras()
    except Exception:
        logger.exception("Auto-resume: failed to fetch cameras from DB")
        return

    resumable = [c for c in cameras if getattr(c, "status", "offline") in ("live", "processing")]

    if not resumable:
        logger.info("Auto-resume: no cameras to resume")
        return

    logger.info("Auto-resume: resuming %d camera(s) …", len(resumable))

    for i, camera in enumerate(resumable):
        # Stagger starts by 2 s each so the Pi isn't overwhelmed
        if i > 0:
            await asyncio.sleep(2)

        camera_id = camera.id
        rtsp_url  = camera.rtsp_url
        name      = camera.name

        # Probe before connecting — mark offline immediately if unreachable
        reachable, probe_msg = await _probe_rtsp(rtsp_url, timeout=5)
        if not reachable:
            logger.warning(
                "Auto-resume: camera '%s' (%s) is unreachable — marking offline. %s",
                name, camera_id, probe_msg,
            )
            update_camera_status(camera_id, "offline")
            continue

        try:
            detection_engine.start_stream(camera_id, rtsp_url)
            update_camera_status(camera_id, "processing")
            logger.info("Auto-resume: started stream for camera '%s' (%s)", name, camera_id)
        except Exception:
            logger.exception(
                "Auto-resume: failed to start stream for camera '%s' (%s)",
                name, camera_id,
            )
            update_camera_status(camera_id, "offline")


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

    # Auto-migration: ensure 'embedding' column exists in 'snapshots' table
    from app.core.db_client import get_db
    from sqlalchemy import text as sql_text
    db = get_db()
    try:
        db.execute(sql_text("ALTER TABLE snapshots ADD COLUMN embedding LONGBLOB NULL"))
        db.commit()
        logger.info("Database migration completed (embedding column added) ✓")
    except Exception:
        db.rollback()
        logger.info("Database migration check completed (embedding column already exists or skipped) ✓")
    finally:
        db.close()

    # Start the periodic stats broadcaster
    stats_broadcaster.start()

    # Seed default alert rules if none exist
    from app.services.alert_engine import seed_default_rules
    seed_default_rules()

    # Load AI models (YOLO, InsightFace) — once at startup, shared across all workers
    from app.services.model_manager import model_manager
    model_manager.load_models()

    # Load CLIP embedding service model
    from app.services.embedding_service import embedding_service
    embedding_service.load_model()

    # Start GPU health monitor
    from app.services.gpu_monitor import gpu_monitor
    gpu_monitor.start()

    # Start memory profiler in development mode
    from app.services.memory_profiler import memory_profiler
    if os.getenv("ENV", "development").lower() != "production":
        memory_profiler.start()

    # Start the system-info background cache (polls every 60s)
    system_info_cache.start(loop=asyncio.get_running_loop())

    # ----------------------------------------------------------------
    # Auto-resume: restart any camera streams that were running before
    # the last shutdown. Runs after models are loaded so workers have
    # YOLO/InsightFace available immediately.
    # ----------------------------------------------------------------
    await _auto_resume_streams()

    logger.info("API ready ✓")

    yield

    # ---- Shutdown ----
    logger.info("Shutting down …")

    detection_engine.stop_all()
    stats_broadcaster.stop()

    from app.services.gpu_monitor import gpu_monitor
    gpu_monitor.stop()

    from app.services.memory_profiler import memory_profiler
    memory_profiler.stop()

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

# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------
# Build origin list from settings + always include the known LAN IPs.
# The previous config was broken — allow_credentials/methods/headers
# were missing from the middleware call.
# ------------------------------------------------------------------
_settings_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

_extra_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    f"http://{os.getenv('SERVER_IP', '192.168.0.152')}:5173",
    f"http://{os.getenv('SERVER_IP', '192.168.0.152')}:8000",
    f"http://{os.getenv('SERVER_IP', '192.168.0.152')}:3000",
]

# Merge, deduplicate, drop empty strings
_all_origins = list(dict.fromkeys(_settings_origins + _extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_all_origins,
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

from app.routes.cameras import router as cameras_router        # noqa: E402
from app.routes.detections import router as detections_router  # noqa: E402
from app.routes.stats import router as stats_router            # noqa: E402
from app.routes.websocket import router as ws_router           # noqa: E402
from app.routes.debug import router as debug_router            # noqa: E402
from app.routes.alerts import router as alerts_router          # noqa: E402
from app.routes.settings import router as settings_router      # noqa: E402
from app.routes.stream import router as stream_router          # noqa: E402
from app.routes.search import router as search_router          # noqa: E402

app.include_router(cameras_router)
app.include_router(detections_router)
app.include_router(stats_router)
app.include_router(ws_router)
app.include_router(alerts_router)
app.include_router(settings_router)
app.include_router(stream_router)
app.include_router(search_router)

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