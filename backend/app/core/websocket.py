"""
Channel-based WebSocket connection manager.

Three channel types:
  • **stream** – per-camera detection frames  (``/ws/stream/{camera_id}``)
  • **stats**  – global statistics broadcast   (``/ws/stats``)
  • **alerts** – real-time alert notifications  (``/ws/alerts``)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for stream, stats, and alert channels."""

    def __init__(self) -> None:
        # camera_id  →  [ws, ws, …]
        self.stream_connections: dict[str, list[WebSocket]] = {}
        # flat list for global stats subscribers
        self.stats_connections: list[WebSocket] = []
        # flat list for alert subscribers
        self.alert_connections: list[WebSocket] = []

    # ------------------------------------------------------------------
    # Stream channel (per camera)
    # ------------------------------------------------------------------

    async def connect_stream(self, camera_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.stream_connections.setdefault(camera_id, []).append(websocket)
        logger.info("WS stream connected: camera=%s  clients=%d",
                     camera_id, len(self.stream_connections[camera_id]))

    def disconnect_stream(self, camera_id: str, websocket: WebSocket) -> None:
        conns = self.stream_connections.get(camera_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.stream_connections.pop(camera_id, None)
        logger.info("WS stream disconnected: camera=%s", camera_id)

    async def broadcast_stream(self, camera_id: str, message: dict[str, Any]) -> None:
        """Send a detection message to every client watching *camera_id*."""
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in self.stream_connections.get(camera_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_stream(camera_id, ws)

    async def broadcast_frame(self, camera_id: str, frame_base64: str) -> None:
        """Send a JPEG frame (base64) to every client watching *camera_id*.

        Message format: ``{"type": "frame", "camera_id": "...", "data": "base64..."}``
        """
        message = {
            "type": "frame",
            "camera_id": camera_id,
            "data": frame_base64,
        }
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self.stream_connections.get(camera_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_stream(camera_id, ws)

    # ------------------------------------------------------------------
    # Stats channel (global)
    # ------------------------------------------------------------------

    async def connect_stats(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.stats_connections.append(websocket)
        logger.info("WS stats connected: clients=%d", len(self.stats_connections))

    def disconnect_stats(self, websocket: WebSocket) -> None:
        if websocket in self.stats_connections:
            self.stats_connections.remove(websocket)
        logger.info("WS stats disconnected")

    async def broadcast_stats(self, message: dict[str, Any]) -> None:
        """Push stats update to every ``/ws/stats`` subscriber."""
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in self.stats_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_stats(ws)

    # ------------------------------------------------------------------
    # Alert channel (global)
    # ------------------------------------------------------------------

    async def connect_alert(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.alert_connections.append(websocket)
        logger.info("WS alert connected: clients=%d", len(self.alert_connections))

    def disconnect_alert(self, websocket: WebSocket) -> None:
        if websocket in self.alert_connections:
            self.alert_connections.remove(websocket)
        logger.info("WS alert disconnected")

    async def broadcast_alert(self, message: dict[str, Any]) -> None:
        """Push an alert message to every ``/ws/alerts`` subscriber."""
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in self.alert_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_alert(ws)


# Singleton instance used across the app
manager = ConnectionManager()
