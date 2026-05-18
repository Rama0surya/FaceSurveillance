"""
Camera CRUD & stream control routes.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.schemas import CameraCreate, CameraUpdate, CameraResponse
from app.db import cameras as cameras_db
from app.services.detection import detection_engine
from app.services.mediamtx_client import mediamtx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


# ------------------------------------------------------------------
# Helper — derive a safe MediaMTX path name from a camera ID
# ------------------------------------------------------------------

def _mediamtx_path_name(camera_id: str) -> str:
    """Convert a camera UUID into a valid MediaMTX path name.

    MediaMTX path names must be simple alphanumeric+underscore strings.
    """
    return "cam_" + re.sub(r"[^a-zA-Z0-9]", "_", camera_id)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(body: CameraCreate):
    """Add a new camera (name + RTSP URL)."""
    camera = cameras_db.create_camera(body)
    return camera


@router.get("", response_model=list[CameraResponse])
async def list_cameras():
    """List every registered camera."""
    return cameras_db.get_cameras()


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: str, body: CameraUpdate):
    """Update a camera's name or RTSP URL."""
    camera = cameras_db.update_camera(camera_id, body)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: str):
    """Delete a camera. Stops stream if running."""
    # Stop any running stream first
    detection_engine.stop_stream(camera_id)

    # Also remove MediaMTX path if applicable
    if settings.USE_MEDIAMTX:
        path_name = _mediamtx_path_name(camera_id)
        try:
            await mediamtx_client.remove_path(path_name)
        except Exception:
            logger.debug("MediaMTX path removal skipped for camera %s", camera_id)

    deleted = cameras_db.delete_camera(camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")


# ------------------------------------------------------------------
# Stream control
# ------------------------------------------------------------------

@router.post("/{camera_id}/start")
async def start_stream(camera_id: str):
    """Start the RTSP stream and begin face detection.

    If MediaMTX is enabled and healthy:
      1. Register the camera's RTSP URL as a MediaMTX proxy path
      2. The detection engine reads from MediaMTX (stable, re-streamable)

    If MediaMTX is disabled or unreachable:
      - Fallback: detection engine reads directly from the camera RTSP URL
    """
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    stream_url = camera.rtsp_url
    use_mediamtx = False

    # --- MediaMTX integration (optional) ---
    if settings.USE_MEDIAMTX:
        try:
            healthy = await mediamtx_client.is_healthy()
            if healthy:
                path_name = _mediamtx_path_name(camera_id)
                # Try to add the path (re-adding is idempotent in MediaMTX)
                added = await mediamtx_client.add_path(path_name, camera.rtsp_url)
                if not added:
                    # Path might already exist — try editing instead
                    await mediamtx_client.edit_path(path_name, camera.rtsp_url)

                # Use the MediaMTX proxied URL for detection
                stream_url = mediamtx_client.get_proxied_rtsp_url(path_name)
                use_mediamtx = True
                logger.info(
                    "Camera %s → MediaMTX path '%s' → %s",
                    camera_id,
                    path_name,
                    stream_url,
                )
            else:
                logger.warning(
                    "MediaMTX not healthy — falling back to direct RTSP for camera %s",
                    camera_id,
                )
        except Exception:
            logger.exception(
                "MediaMTX integration failed — falling back to direct RTSP for camera %s",
                camera_id,
            )

    detection_engine.start_stream(camera_id, stream_url)
    cameras_db.update_camera_status(camera_id, "processing")

    return {
        "message": f"Stream started for camera {camera.name}",
        "camera_id": camera_id,
        "stream_url": stream_url,
        "via_mediamtx": use_mediamtx,
    }


@router.post("/{camera_id}/stop")
async def stop_stream(camera_id: str):
    """Stop the RTSP stream and detection."""
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    detection_engine.stop_stream(camera_id)
    cameras_db.update_camera_status(camera_id, "offline")

    # Clean up MediaMTX path
    if settings.USE_MEDIAMTX:
        path_name = _mediamtx_path_name(camera_id)
        try:
            await mediamtx_client.remove_path(path_name)
        except Exception:
            logger.debug("MediaMTX path removal skipped for camera %s", camera_id)

    return {"message": f"Stream stopped for camera {camera.name}", "camera_id": camera_id}


@router.get("/{camera_id}/status")
async def get_status(camera_id: str):
    """Get the current status of a camera (live / offline / processing)."""
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    engine_status = detection_engine.get_status(camera_id)

    return {
        "camera_id": camera_id,
        "name": camera.name,
        "status": engine_status,
    }


# ------------------------------------------------------------------
# MediaMTX status endpoint
# ------------------------------------------------------------------

@router.get("/{camera_id}/mediamtx-status")
async def get_mediamtx_status(camera_id: str):
    """Get MediaMTX path info for a camera (if applicable)."""
    if not settings.USE_MEDIAMTX:
        return {"enabled": False, "message": "MediaMTX is disabled"}

    path_name = _mediamtx_path_name(camera_id)

    try:
        healthy = await mediamtx_client.is_healthy()
        if not healthy:
            return {"enabled": True, "healthy": False, "message": "MediaMTX is not responding"}

        path_info = await mediamtx_client.get_path(path_name)
        return {
            "enabled": True,
            "healthy": True,
            "path_name": path_name,
            "path_info": path_info,
            "proxied_url": mediamtx_client.get_proxied_rtsp_url(path_name) if path_info else None,
        }
    except Exception as e:
        return {"enabled": True, "healthy": False, "error": str(e)}
