"""
API routes for system settings, hardware info, and runtime configuration.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.system_info import SystemInfo, system_info_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# =====================================================================
# System Info
# =====================================================================


@router.get("/system-info")
async def get_system_info():
    """Return full system information from background cache.

    Data is refreshed every 60 seconds in a background task.
    This endpoint returns instantly (~0ms) regardless of GPU probe latency.
    """
    try:
        return system_info_cache.get_full_info()
    except Exception as exc:
        logger.exception("Failed to get system info")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/hardware")
async def get_hardware_info():
    """Return GPU and CPU hardware info from background cache."""
    try:
        return system_info_cache.get_hardware()
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
    # ── Tambahan field baru ──
    face_detector: Optional[str] = Field(
        None, description="Detector backend: yolov8, opencv, retinaface, mtcnn, ssd"
    )
    yolo_confidence: Optional[float] = Field(
        None, ge=0.1, le=1.0, description="YOLO detection confidence threshold"
    )
    face_tracker: Optional[str] = Field(
        None, description="Tracker: bytetrack, botsort, none"
    )
    track_reanalyze_ttl: Optional[int] = Field(
        None, ge=10, le=3600, description="Seconds before re-analyzing a tracked face"
    )


@router.put("/detection-config")
async def update_detection_config(body: DetectionConfigUpdate):
    """Update runtime detection configuration (in-memory, not persisted to file)."""
    valid_models = {"VGG-Face", "Facenet", "OpenFace", "DeepID", "ArcFace", "Dlib"}
    valid_detectors = {"yolov8", "opencv", "retinaface", "mtcnn", "ssd", "dlib"}
    valid_trackers = {"bytetrack", "botsort", "none"}

    if body.deepface_model and body.deepface_model not in valid_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Choose from: {', '.join(sorted(valid_models))}",
        )
    if body.face_detector and body.face_detector not in valid_detectors:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid detector. Choose from: {', '.join(sorted(valid_detectors))}",
        )
    if body.face_tracker and body.face_tracker not in valid_trackers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tracker. Choose from: {', '.join(sorted(valid_trackers))}",
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

    # if body.face_detector is not None:
    #     settings.FACE_DETECTOR = body.face_detector
    #     logger.info("Updated FACE_DETECTOR → %s", body.face_detector)
    # Di backend/app/routes/settings.py, setelah validasi face_detector:
    if body.face_detector is not None:
    # Normalize "yolo" → "yolov8" untuk kompatibilitas DeepFace
        normalized = "yolov8" if body.face_detector == "yolo" else body.face_detector
        settings.FACE_DETECTOR = normalized
        logger.info("Updated FACE_DETECTOR → %s", normalized)

    if body.yolo_confidence is not None:
        settings.YOLO_CONFIDENCE = body.yolo_confidence
        logger.info("Updated YOLO_CONFIDENCE → %s", body.yolo_confidence)

    if body.face_tracker is not None:
        settings.FACE_TRACKER = body.face_tracker
        logger.info("Updated FACE_TRACKER → %s", body.face_tracker)

    if body.track_reanalyze_ttl is not None:
        settings.TRACK_REANALYZE_TTL = body.track_reanalyze_ttl
        logger.info("Updated TRACK_REANALYZE_TTL → %s", body.track_reanalyze_ttl)

    return {
        "detection_interval": settings.DETECTION_INTERVAL_SECONDS,
        "frame_fps": settings.FRAME_BROADCAST_FPS,
        "deepface_model": settings.DEEPFACE_MODEL,
        "face_detector": settings.FACE_DETECTOR,
        "yolo_confidence": settings.YOLO_CONFIDENCE,
        "face_tracker": settings.FACE_TRACKER,
        "track_reanalyze_ttl": settings.TRACK_REANALYZE_TTL,
    }


# =====================================================================
# Health Check
# =====================================================================


@router.get("/health")
async def health_check():
    """Return system health: API status, DB connectivity, active streams, uptime."""
    from app.services.detection import detection_engine
    from app.core.db_client import ping_db

    db_ok = ping_db()
    active_streams = len(detection_engine._workers)

    return {
        "api_status": "healthy",
        "db_connected": db_ok,
        "active_streams": active_streams,
        "uptime_seconds": SystemInfo.get_uptime_seconds(),
        "version": "1.0.0",
    }

