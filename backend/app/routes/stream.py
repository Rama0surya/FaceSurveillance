"""
API routes for streaming video (MJPEG) and events (SSE).

Stream Architecture (Layer 1 — Independent Service):
  - MJPEG endpoint: ``GET /api/stream/video/{camera_id}``
    Pure video stream, embeddable in ``<img src="...">``.
    Connection-stateful (per-client queue), but the underlying
    RTSP reader + AI pipeline runs independently.

  - SSE endpoint: ``GET /api/stream/events/{camera_id}``
    Detection events, snapshot notifications, toggle changes.
    Frontend subscribes once; EventSource auto-reconnects.

  - Status endpoint: ``GET /api/stream/status/{camera_id}``
    Lightweight health check — returns stream alive status,
    client count, FPS info. Does NOT touch the video stream.

Key design invariants:
  - The video stream endpoint is INDEPENDENT of the web page.
    Browser can refresh, navigate away, and reconnect without
    affecting the underlying RTSP reader or AI pipeline.
  - Events (SSE) and video (MJPEG) are on SEPARATE endpoints.
    A re-render of the dashboard doesn't affect the video stream.
  - CORS headers allow cross-origin embedding (frontend on :5173,
    backend on :8000).
"""

from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.sse import sse_manager
from app.db import cameras as cameras_db
from app.services.detection import detection_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])


# =====================================================================
# MJPEG Video Stream — pure video, always on
# =====================================================================

@router.get("/video/{camera_id}")
async def stream_video(camera_id: str, request: Request):
    """
    Multipart MJPEG video stream for a specific camera.

    This endpoint returns a continuous ``multipart/x-mixed-replace``
    response that can be directly embedded in ``<img src="...">``.

    The stream is **independent** of the web page lifecycle:
    - Page refresh only kills THIS HTTP connection; the RTSP reader
      and AI pipeline continue running on the server.
    - Reconnecting creates a new queue and immediately starts
      receiving the latest frames.

    Headers are configured for:
    - No caching (``Cache-Control: no-cache``)
    - Keep-alive (long-lived connection)
    - Cross-origin access (``Access-Control-Allow-Origin: *``)
    - No proxy buffering (``X-Accel-Buffering: no``)
    """
    # Verify camera exists
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Get active stream worker
    worker = detection_engine.get_worker(camera_id)
    if worker is None or not worker.is_alive:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stream is not running. Start the camera stream first.",
        )

    # Capture the running event loop for queue registration
    loop = asyncio.get_running_loop()

    # Create a per-client queue with small backlog (drop-oldest semantics)
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=3)

    async def frame_generator():
        # Register queue BEFORE the try block — unregister always runs in finally
        worker.register_mjpeg_queue(q, loop)
        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.debug(
                        "MJPEG client disconnected (camera=%s)", camera_id
                    )
                    break

                try:
                    # Wait up to 5s for a frame; if none arrives,
                    # loop back to check is_disconnected()
                    frame_bytes = await asyncio.wait_for(q.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue

                # Yield in multipart MJPEG format
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(frame_bytes)).encode("ascii")
                    + b"\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
        except asyncio.CancelledError:
            pass
        except GeneratorExit:
            pass
        finally:
            # Always unregister, even on abrupt disconnects
            worker.unregister_mjpeg_queue(q)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        },
    )


# =====================================================================
# SSE Events — detection, snapshot, toggle notifications
# =====================================================================

@router.get("/events/{camera_id}")
async def stream_events(camera_id: str, request: Request):
    """
    Server-Sent Events (SSE) endpoint for a specific camera.

    Pushes real-time events:
      - ``detection``: new face detected (bbox, gender, emotion, age)
      - ``snapshot``: new face snapshot saved
      - ``toggle_changed``: pipeline toggle updated

    The frontend subscribes via ``new EventSource('/api/stream/events/{cam}')``.
    EventSource auto-reconnects on connection loss.

    This endpoint is SEPARATE from the video stream — subscribing
    or unsubscribing from events has zero effect on the MJPEG stream.
    """
    # Verify camera exists
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    async def event_generator():
        # Use async subscribe for proper lock-safe registration
        q = await sse_manager.subscribe_async(camera_id)
        try:
            # Send initial connection confirmation
            yield 'data: {"type": "connected"}\n\n'

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for an event with a timeout for keep-alive
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield event
                except asyncio.TimeoutError:
                    # Keep-alive comment (SSE standard)
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        except GeneratorExit:
            pass
        finally:
            sse_manager.unsubscribe(camera_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        },
    )


# =====================================================================
# Stream Status — lightweight health check
# =====================================================================

@router.get("/status/{camera_id}")
async def stream_status(camera_id: str):
    """
    Lightweight status check for a camera stream.

    Returns whether the stream is alive, how many MJPEG clients
    are connected, and SSE subscriber count. Does NOT touch the
    video stream itself.

    Use this endpoint to show stream health indicators in the UI
    without creating a video connection.
    """
    camera = cameras_db.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    worker = detection_engine.get_worker(camera_id)

    if worker is None:
        return {
            "camera_id": camera_id,
            "stream_alive": False,
            "mjpeg_clients": 0,
            "sse_clients": 0,
        }

    # Count MJPEG clients from the worker's registered queues
    with worker._mjpeg_queues_lock:
        mjpeg_count = len(worker._mjpeg_queues)

    # Count SSE clients
    sse_count = sse_manager.broadcast_camera_count(camera_id)

    return {
        "camera_id": camera_id,
        "stream_alive": worker.is_alive,
        "mjpeg_clients": mjpeg_count,
        "sse_clients": sse_count,
    }
