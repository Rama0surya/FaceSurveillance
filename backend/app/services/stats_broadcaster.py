"""
Background task that periodically pushes stats to ``/ws/stats`` subscribers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.websocket import manager as ws_manager
from app.db.stats import get_today_stats

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _broadcast_loop() -> None:
    """Runs forever, pushing stats every N seconds."""
    while True:
        try:
            await asyncio.sleep(settings.STATS_BROADCAST_INTERVAL)

            # Only broadcast if there are subscribers
            if not ws_manager.stats_connections:
                continue

            stats = get_today_stats()
            message = {
                "type": "stats_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cameras": stats,
            }
            await ws_manager.broadcast_stats(message)

        except asyncio.CancelledError:
            logger.info("Stats broadcaster cancelled")
            break
        except Exception:
            logger.exception("Stats broadcast error")
            await asyncio.sleep(2)


def start() -> None:
    """Start the background stats broadcaster task."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_broadcast_loop())
        logger.info(
            "Stats broadcaster started (interval=%ds)",
            settings.STATS_BROADCAST_INTERVAL,
        )


def stop() -> None:
    """Cancel the background stats broadcaster task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None
        logger.info("Stats broadcaster stopped")
