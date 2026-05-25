"""
Camera CRUD & stream control routes.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.schemas import CameraCreate, CameraUpdate, CameraResponse
from app.db import cameras as cameras_db
from app.services.detection import detection_engine
from app.services.mediamtx_client import mediamtx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

# How long to wait when probing RTSP host:port reachability (seconds)
_RTSP_PROBE_TIMEOUT = 5


# ------------------------------------------------------------------
# Helper — derive a safe MediaMTX path name from a camera ID
# ------------------------------------------------------------------

def _mediamtx_path_name(camera_id: str) -> str:
    """Convert a camera UUID into a valid MediaMTX path name."""
    return "cam_" + re.sub(r"[^a-zA-Z0-9]", "_", camera_id)


# ------------------------------------------------------------------
# Helper — RTSP reachability probe
# ------------------------------------------------------------------

async def _probe_rtsp(rtsp_url: str, timeout: float = _RTSP_PROBE_TIMEOUT) -> tuple[bool, str]:
    """Check if the RTSP host:port is reachable via TCP.

    Does NOT authenticate or negotiate the RTSP session — just verifies
    the host is up and the port is open. Fast (~timeout seconds worst case).

    Returns:
        (reachable: bool, message: str)
    """
    try:
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554  # default RTSP port

        if not host:
            return False, f"Invalid RTSP URL — cannot parse host from: {rtsp_url}"

        # Run the blocking socket connect in a thread so we don't block the event loop
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, _tcp_connect, host, port),
            timeout=timeout,
        )
        return True, f"Host {host}:{port} is reachable"

    except asyncio.TimeoutError:
        parsed = urlparse(rtsp_url)
        host = parsed.hostname or rtsp_url
        port = parsed.port or 554
        return False, (
            f"Cannot reach camera at {host}:{port} — "
            f"connection timed out after {timeout}s. "
            "Check that the camera is powered on and the IP/port is correct."
        )
    except OSError as e:
        return False, f"Network error connecting to camera: {e}"
    except Exception as e:
        return False, f"RTSP probe failed: {e}"


def _tcp_connect(host: str, port: int) -> None:
    """Blocking TCP connect — runs in thread executor."""
    with socket.create_connection((host, port), timeout=_RTSP_PROBE_TIMEOUT):
        pass  # Connection succeeded — close immediately


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(body: CameraCreate):
    """Add a new camera (name + RTSP URL).

    Probes the RTSP host:port before saving. Returns a warning in the
    response if the camera is unreachable, but still saves it so the
    user can fix the URL later.
    """
    # Probe reachability (non-blocking, short timeout)
    reachable, probe_message = await _probe_rtsp(body.rtsp_url, timeout=3)

    camera = cameras_db.create_camera(body)

    # Return the camera with an extra reachability hint
    result = dict(camera) if hasattr(camera, '__dict__') else camera
    if not reachable:
        logger.warning(
            "Camera %s (%s) created but RTSP unreachable: %s",
            camera.get("id") if isinstance(camera, dict) else getattr(camera, "id", "?"),
            body.rtsp_url,
            probe_message,
        )

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
    detection_engine.stop_stream(camera_id)

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
# RTSP probe endpoint (called by frontend before starting stream)
# ------------------------------------------------------------------

@router.post("/{camera_id}/probe")
async def probe_camera(camera_id: str):
    """Check if a camera's RTSP stream is reachable without starting it.

    Returns:
        {reachable: bool, message: str, camera_id: str}

    The frontend calls this when the user clicks Start, giving instant
    feedback if the camera is offline before committing to stream start.
    """
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    reachable, message = await _probe_rtsp(camera.rtsp_url)

    if not reachable:
        # Update DB status to reflect the camera is offline
        cameras_db.update_camera_status(camera_id, "offline")

    return {
        "camera_id": camera_id,
        "name": camera.name,
        "reachable": reachable,
        "message": message,
        "rtsp_url": camera.rtsp_url,
    }


# ------------------------------------------------------------------
# Stream control
# ------------------------------------------------------------------

@router.post("/{camera_id}/start")
async def start_stream(camera_id: str):
    """Start the RTSP stream and begin face detection.

    Probes RTSP reachability first. Returns 422 with a clear error
    message if the camera is unreachable — the frontend shows this
    as a warning toast instead of silently marking the camera live.
    """
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    # ---- RTSP reachability check ----
    reachable, probe_message = await _probe_rtsp(camera.rtsp_url)
    if not reachable:
        cameras_db.update_camera_status(camera_id, "offline")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "rtsp_unreachable",
                "message": probe_message,
                "camera_id": camera_id,
                "rtsp_url": camera.rtsp_url,
            },
        )

    stream_url = camera.rtsp_url
    use_mediamtx = False

    # --- MediaMTX integration (optional) ---
    if settings.USE_MEDIAMTX:
        try:
            healthy = await mediamtx_client.is_healthy()
            if healthy:
                path_name = _mediamtx_path_name(camera_id)
                added = await mediamtx_client.add_path(path_name, camera.rtsp_url)
                if not added:
                    await mediamtx_client.edit_path(path_name, camera.rtsp_url)
                stream_url = mediamtx_client.get_proxied_rtsp_url(path_name)
                use_mediamtx = True
                logger.info(
                    "Camera %s → MediaMTX path '%s' → %s",
                    camera_id, path_name, stream_url,
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

    # If engine says offline but DB says live/processing, sync them
    db_status = getattr(camera, "status", None)
    if engine_status == "offline" and db_status in ("live", "processing"):
        cameras_db.update_camera_status(camera_id, "offline")

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