"""
API routes for system settings, hardware info, and runtime configuration.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.system_info import SystemInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# =====================================================================
# System Info
# =====================================================================


@router.get("/system-info")
async def get_system_info():
    """Return full system information (CPU, Memory, GPU, Disk, Python, Models)."""
    try:
        return SystemInfo.get_full_info()
    except Exception as exc:
        logger.exception("Failed to get system info")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/hardware")
async def get_hardware_info():
    """Return GPU and CPU hardware info."""
    try:
        return {
            "gpu": SystemInfo.get_gpu_info(),
            "cpu": SystemInfo.get_cpu_info(),
        }
    except Exception as exc:
        logger.exception("Failed to get hardware info")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/models")
async def get_model_info():
    """Return AI model configuration info."""
    return SystemInfo.get_model_info()


# =====================================================================
# Detection Config (runtime update)
# =====================================================================


class DetectionConfigUpdate(BaseModel):
    detection_interval: Optional[float] = Field(
        None, ge=0.5, le=30.0, description="Seconds between detection runs"
    )
    frame_fps: Optional[int] = Field(
        None, ge=1, le=30, description="Frame broadcast FPS"
    )
    deepface_model: Optional[str] = Field(
        None, description="DeepFace recognition model name"
    )


@router.put("/detection-config")
async def update_detection_config(body: DetectionConfigUpdate):
    """Update runtime detection configuration (in-memory, not persisted to file)."""
    valid_models = {"VGG-Face", "Facenet", "OpenFace", "DeepID", "ArcFace", "Dlib"}

    if body.deepface_model and body.deepface_model not in valid_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Choose from: {', '.join(sorted(valid_models))}",
        )

    if body.detection_interval is not None:
        settings.DETECTION_INTERVAL_SECONDS = body.detection_interval
        logger.info("Updated DETECTION_INTERVAL_SECONDS → %s", body.detection_interval)

    if body.frame_fps is not None:
        settings.FRAME_BROADCAST_FPS = body.frame_fps
        logger.info("Updated FRAME_BROADCAST_FPS → %s", body.frame_fps)

    if body.deepface_model is not None:
        settings.DEEPFACE_MODEL = body.deepface_model
        logger.info("Updated DEEPFACE_MODEL → %s", body.deepface_model)

    return {
        "detection_interval": settings.DETECTION_INTERVAL_SECONDS,
        "frame_fps": settings.FRAME_BROADCAST_FPS,
        "deepface_model": settings.DEEPFACE_MODEL,
    }


# =====================================================================
# Health Check
# =====================================================================


@router.get("/health")
async def health_check():
    """Return system health: API status, Supabase connectivity, active streams, uptime."""
    from app.services.detection import detection_engine

    # Check Supabase connectivity
    supabase_ok = False
    try:
        from app.db.detections import _sb

        # Simple ping — attempt to read from a table
        _sb.table("detections").select("id").limit(1).execute()
        supabase_ok = True
    except Exception:
        pass

    active_streams = len(detection_engine.active_cameras)

    return {
        "api_status": "healthy",
        "supabase_connected": supabase_ok,
        "active_streams": active_streams,
        "uptime_seconds": SystemInfo.get_uptime_seconds(),
        "version": "1.0.0",
    }
