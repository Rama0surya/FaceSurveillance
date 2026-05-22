"""
Lightweight memory leak detector for stress testing.

Uses ``tracemalloc`` to track Python memory allocations and ``psutil``
(optional) for process RSS monitoring.  Runs as a background daemon
thread, logging top allocations and detecting monotonic RSS growth
that indicates a memory leak.

Enable via::

    from app.services.memory_profiler import memory_profiler
    memory_profiler.start()
    # ... run workload ...
    memory_profiler.stop()
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
import tracemalloc
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryProfiler:
    """Periodic memory usage tracker — detect leaks over time."""

    def __init__(self, interval: float = 60.0, top_n: int = 10):
        self._interval = interval
        self._top_n = top_n
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._snapshots: list[tuple[float, int]] = []
        self._active = False

    def start(self) -> None:
        """Start tracemalloc and the profiling background thread."""
        if self._active:
            return

        tracemalloc.start(10)
        self._active = True
        self._stop.clear()
        self._snapshots.clear()

        self._thread = threading.Thread(
            target=self._profile_loop, daemon=True, name="mem-profiler"
        )
        self._thread.start()
        logger.info(
            "Memory profiler started (interval=%ss, top_n=%d)",
            self._interval, self._top_n,
        )

    def stop(self) -> None:
        """Stop profiling and release tracemalloc resources."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        if self._active:
            tracemalloc.stop()
            self._active = False
        logger.info("Memory profiler stopped")

    def _profile_loop(self) -> None:
        """Background loop — take snapshots and compare to baseline."""
        baseline_snapshot = tracemalloc.take_snapshot()

        while not self._stop.wait(self._interval):
            try:
                self._take_snapshot(baseline_snapshot)
            except Exception:
                logger.exception("Memory profiler error")

    def _take_snapshot(self, baseline) -> None:
        """Take a memory snapshot and analyse it."""
        current = tracemalloc.take_snapshot()
        stats = current.compare_to(baseline, "lineno")

        # Process RSS via psutil (optional)
        rss_mb = 0
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            rss_mb = proc.memory_info().rss / 1e6
        except ImportError:
            pass

        self._snapshots.append((time.time(), int(rss_mb)))

        # Log top allocations
        top_stats = stats[:self._top_n]
        logger.info("=== Memory Profile (RSS=%.0f MB) ===", rss_mb)
        for stat in top_stats:
            logger.info("  %s", stat)

        # Detect leak: RSS growing monotonically over last 5 samples
        if len(self._snapshots) >= 5:
            last_5 = [s[1] for s in self._snapshots[-5:]]
            if all(last_5[i] < last_5[i + 1] for i in range(4)):
                growth = last_5[-1] - last_5[0]
                logger.warning(
                    "POTENTIAL MEMORY LEAK: RSS grew by %d MB "
                    "over last 5 intervals (%s)",
                    growth, last_5,
                )

        # Force GC and log collected objects
        collected = gc.collect()
        if collected > 100:
            logger.info("GC collected %d objects", collected)

    def get_status(self) -> dict:
        """Return profiler status for API exposure."""
        if not self._snapshots:
            return {"active": self._active, "samples": 0}

        recent = self._snapshots[-5:]
        return {
            "active": self._active,
            "samples": len(self._snapshots),
            "latest_rss_mb": recent[-1][1] if recent else 0,
            "rss_trend": [s[1] for s in recent],
        }


# Singleton instance
memory_profiler = MemoryProfiler()
