"""
WebSocket endpoints for real-time detection stream and stats.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/stream/{camera_id}")
async def ws_stream(websocket: WebSocket, camera_id: str):
    """
    Real-time detection stream for a specific camera.

    Clients connect here to receive detection messages as they happen.
    The server pushes messages; the client only needs to listen.
    """
    await manager.connect_stream(camera_id, websocket)
    try:
        while True:
            # Keep the connection alive; we don't expect client messages
            # but we need to read to detect disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_stream(camera_id, websocket)
        logger.info("Client disconnected from /ws/stream/%s", camera_id)
    except Exception:
        manager.disconnect_stream(camera_id, websocket)


@router.websocket("/ws/stats")
async def ws_stats(websocket: WebSocket):
    """
    Global stats stream — pushes updated statistics every N seconds.

    Stats are broadcast by the background ``stats_broadcaster`` task.
    """
    await manager.connect_stats(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_stats(websocket)
        logger.info("Client disconnected from /ws/stats")
    except Exception:
        manager.disconnect_stats(websocket)


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """
    Real-time alert stream — pushes alert notifications as they are triggered.

    Clients connect here to receive alert messages in real-time.
    """
    await manager.connect_alert(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_alert(websocket)
        logger.info("Client disconnected from /ws/alerts")
    except Exception:
        manager.disconnect_alert(websocket)

