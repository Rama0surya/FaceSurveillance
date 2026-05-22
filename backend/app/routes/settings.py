"""
API routes for system settings, hardware info, and runtime configuration.

Refactored:
  - Runtime detection config now writes to ``runtime_config`` (a plain
    dataclass in ``pipeline_state``) instead of mutating Pydantic
    ``BaseSettings`` attributes (which may be frozen in Pydantic v2).
  - Pipeline toggles route unchanged except for SSE broadcast.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.pipeline_state import pipeline_state, runtime_config
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
# Pipeline Toggles (runtime ON/OFF)
# =====================================================================

class PipelineToggleUpdate(BaseModel):
    """Body for PUT /api/settings/pipeline-toggles."""
    tracking_enabled: Optional[bool] = Field(
        None, description="Enable/disable ByteTrack tracking in Thread B"
    )
    insightface_enabled: Optional[bool] = Field(
        None, description="Enable/disable InsightFace + DeepFace + snapshot in Thread C"
    )


@router.get("/pipeline-toggles")
async def get_pipeline_toggles():
    """Return current pipeline toggle state."""
    return pipeline_state.get_state()


@router.put("/pipeline-toggles")
async def update_pipeline_toggles(body: PipelineToggleUpdate):
    """Update pipeline toggles at runtime (instant, no restart needed).

    - ``tracking_enabled=false`` → Thread B skips ByteTrack (YOLO-only, faster)
    - ``insightface_enabled=false`` → Thread C idles (no age/gender/emotion/snapshot)
    """
    updates = {}
    if body.tracking_enabled is not None:
        updates["tracking_enabled"] = body.tracking_enabled
    if body.insightface_enabled is not None:
        updates["insightface_enabled"] = body.insightface_enabled

    if not updates:
        return pipeline_state.get_state()

    res_state = pipeline_state.update(**updates)

    from app.core.sse import sse_manager
    try:
        await sse_manager.broadcast_global("toggle_changed", res_state)
    except Exception:
        logger.exception("Failed to broadcast toggle change via SSE")

    return res_state


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
    # ── Smart capture settings ──
    capture_min_confidence: Optional[float] = Field(
        None, ge=0.1, le=1.0, description="Min YOLO confidence to capture (anti-false-positive)"
    )
    min_face_size: Optional[int] = Field(
        None, ge=20, le=500, description="Min face bbox size in pixels (anti-background)"
    )
    capture_cooldown: Optional[float] = Field(
        None, ge=1.0, le=60.0, description="Seconds between captures of same track_id"
    )


@router.put("/detection-config")
async def update_detection_config(body: DetectionConfigUpdate):
    """Update runtime detection configuration.

    Writes to ``runtime_config`` (a mutable dataclass) instead of the
    Pydantic ``settings`` object.  Pipeline threads read ``runtime_config``
    on every iteration, so changes take effect immediately.
    """
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

    # ---- Apply changes to RuntimeConfig ----

    if body.detection_interval is not None:
        runtime_config.detection_interval = body.detection_interval
        logger.info("Updated detection_interval → %s", body.detection_interval)

    if body.frame_fps is not None:
        runtime_config.frame_fps = body.frame_fps
        logger.info("Updated frame_fps → %s", body.frame_fps)

    if body.deepface_model is not None:
        runtime_config.deepface_model = body.deepface_model
        logger.info("Updated deepface_model → %s", body.deepface_model)

    if body.face_detector is not None:
        # Normalize "yolo" → "yolov8" for DeepFace compatibility
        normalized = "yolov8" if body.face_detector == "yolo" else body.face_detector
        runtime_config.face_detector = normalized
        logger.info("Updated face_detector → %s", normalized)

    if body.yolo_confidence is not None:
        runtime_config.yolo_confidence = body.yolo_confidence
        logger.info("Updated yolo_confidence → %s", body.yolo_confidence)

    if body.face_tracker is not None:
        runtime_config.face_tracker = body.face_tracker
        logger.info("Updated face_tracker → %s", body.face_tracker)

    if body.track_reanalyze_ttl is not None:
        runtime_config.track_reanalyze_ttl = body.track_reanalyze_ttl
        logger.info("Updated track_reanalyze_ttl → %s", body.track_reanalyze_ttl)

    # ── Smart capture settings ──
    if body.capture_min_confidence is not None:
        runtime_config.capture_min_confidence = body.capture_min_confidence
        logger.info("Updated capture_min_confidence → %s", body.capture_min_confidence)

    if body.min_face_size is not None:
        runtime_config.min_face_size = body.min_face_size
        logger.info("Updated min_face_size → %s", body.min_face_size)

    if body.capture_cooldown is not None:
        runtime_config.capture_cooldown = body.capture_cooldown
        logger.info("Updated capture_cooldown → %s", body.capture_cooldown)

    return runtime_config.to_dict()


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
