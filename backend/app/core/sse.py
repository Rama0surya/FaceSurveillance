"""
Thread-safe Server-Sent Events (SSE) connection manager.

Fixes applied:
  1. _queues access is now guarded by asyncio.Lock() — prevents race conditions
     when broadcast() is called concurrently from multiple coroutines.
  2. Snapshot copy of queue list before iterating — prevents "list changed size
     during iteration" RuntimeError when a client subscribes/unsubscribes mid-broadcast.
  3. broadcast() and broadcast_global() now silently drop puts to full queues
     (q.put_nowait with try/except) instead of blocking the entire broadcast with
     await q.put() — a slow/stalled client can no longer freeze all other clients.
  4. Added broadcast_camera_count() helper for observability.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

# Max events queued per client before oldest is dropped (back-pressure)
_QUEUE_MAX = 64


class SSEConnectionManager:
    """Manages SSE client queues and event broadcasting per camera."""

    def __init__(self) -> None:
        # camera_id -> list of asyncio.Queue
        self._queues: Dict[str, List[asyncio.Queue[str]]] = {}
        # Asyncio lock — must be acquired only from coroutines (not threads).
        # Thread C uses asyncio.run_coroutine_threadsafe() which schedules on the
        # event loop, so all actual dict mutations happen on the loop thread.
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Subscribe / Unsubscribe (called from async route handlers)          #
    # ------------------------------------------------------------------ #

    async def subscribe_async(self, camera_id: str) -> asyncio.Queue[str]:
        """Subscribe a new client queue (async, lock-safe)."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX)
        async with self._lock:
            self._queues.setdefault(camera_id, []).append(q)
            count = len(self._queues[camera_id])
        logger.info(
            "SSE client subscribed: camera=%s, clients=%d",
            camera_id,
            count,
        )
        return q

    # Keep legacy sync name working (called from sync route handlers in tests)
    def subscribe(self, camera_id: str) -> asyncio.Queue[str]:
        """Subscribe without lock (safe only when called from the event-loop thread)."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._queues.setdefault(camera_id, []).append(q)
        logger.info(
            "SSE client subscribed: camera=%s, clients=%d",
            camera_id,
            len(self._queues[camera_id]),
        )
        return q

    def unsubscribe(self, camera_id: str, q: asyncio.Queue[str]) -> None:
        """Unsubscribe a client queue (safe: called from the event-loop thread)."""
        conns = self._queues.get(camera_id, [])
        if q in conns:
            conns.remove(q)
        if not conns:
            self._queues.pop(camera_id, None)
        logger.info("SSE client unsubscribed: camera=%s", camera_id)

    # ------------------------------------------------------------------ #
    # Broadcast helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_event_str(event_type: str, data: dict, timestamp: str) -> str:
        message = {
            "type": event_type,
            "data": data,
            "timestamp": timestamp,
        }
        payload = json.dumps(message, default=str)
        return f"data: {payload}\n\n"

    @staticmethod
    def _safe_put(q: asyncio.Queue[str], event_str: str) -> None:
        """Non-blocking put — drop oldest message if queue is full (back-pressure)."""
        try:
            q.put_nowait(event_str)
        except asyncio.QueueFull:
            # Drop the oldest event to make room, then retry once.
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(event_str)
            except asyncio.QueueFull:
                pass  # extremely unlikely; just skip

    async def broadcast(
        self,
        camera_id: str,
        event_type: str,
        data: dict,
        timestamp: str | None = None,
    ) -> None:
        """Send an event to all subscribers of a specific camera.

        FIX: Takes a snapshot copy of the queue list under a lock so that
        concurrent subscribe/unsubscribe cannot corrupt iteration.
        Uses non-blocking put so a slow client cannot stall the broadcast.
        """
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        event_str = self._build_event_str(event_type, data, timestamp)

        async with self._lock:
            # Snapshot copy — iteration happens outside the lock
            queues = list(self._queues.get(camera_id, []))

        for q in queues:
            self._safe_put(q, event_str)

    async def broadcast_global(
        self,
        event_type: str,
        data: dict,
        timestamp: str | None = None,
    ) -> None:
        """Send an event to all subscribers across all cameras.

        FIX: Same snapshot-copy pattern to avoid iteration-during-mutation.
        """
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        event_str = self._build_event_str(event_type, data, timestamp)

        async with self._lock:
            # Flatten all queues into a single snapshot list
            all_queues = [
                q
                for queues in self._queues.values()
                for q in queues
            ]

        for q in all_queues:
            self._safe_put(q, event_str)

    def broadcast_camera_count(self, camera_id: str) -> int:
        """Return number of active SSE clients for a camera (non-locking read)."""
        return len(self._queues.get(camera_id, []))


# Singleton manager instance
sse_manager = SSEConnectionManager()
