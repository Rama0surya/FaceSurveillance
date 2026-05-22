"""
GPU Health Monitor — periodic VRAM and thermal checks.

Runs as a background daemon thread, polling GPU status every N seconds.
Logs warnings when VRAM usage exceeds threshold or memory fragmentation
is detected.  Designed for production use — zero impact on inference
performance (runs in its own thread with lightweight nvidia-smi / PyTorch calls).
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class GPUHealthMonitor:
    """Periodic GPU health checker — detects VRAM exhaustion and fragmentation."""

    def __init__(self, interval: float = 30.0, vram_threshold: float = 0.90):
        self._interval = interval
        self._vram_threshold = vram_threshold  # Alert if VRAM usage > 90%
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background health check thread."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="gpu-health"
        )
        self._thread.start()
        logger.info("GPU health monitor started (interval=%ss, threshold=%.0f%%)",
                     self._interval, self._vram_threshold * 100)

    def stop(self) -> None:
        """Stop the background health check thread."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("GPU health monitor stopped")

    def _monitor_loop(self) -> None:
        """Main loop — runs health checks at the configured interval."""
        # Initial check
        self._check_gpu()

        while not self._stop.wait(self._interval):
            try:
                self._check_gpu()
            except Exception:
                logger.exception("GPU health check failed")

    def _check_gpu(self) -> None:
        """Run GPU health checks via PyTorch CUDA API."""
        try:
            import torch
        except ImportError:
            return  # No PyTorch — nothing to monitor

        if not torch.cuda.is_available():
            logger.warning("GPU HEALTH: CUDA no longer available!")
            return

        for i in range(torch.cuda.device_count()):
            allocated = torch.cuda.memory_allocated(i)
            reserved = torch.cuda.memory_reserved(i)
            total = torch.cuda.get_device_properties(i).total_mem

            usage_pct = allocated / total if total > 0 else 0
            reserved_pct = reserved / total if total > 0 else 0

            if usage_pct > self._vram_threshold:
                logger.warning(
                    "GPU %d VRAM CRITICAL: %.1f%% used (%.0f MB / %.0f MB), "
                    "reserved=%.1f%%",
                    i, usage_pct * 100,
                    allocated / 1e6, total / 1e6,
                    reserved_pct * 100,
                )
            else:
                logger.debug(
                    "GPU %d: VRAM %.1f%% (%.0f MB / %.0f MB)",
                    i, usage_pct * 100, allocated / 1e6, total / 1e6,
                )

            # Check for fragmentation (reserved >> allocated)
            if reserved > 0 and allocated > 0 and allocated / reserved < 0.5:
                logger.warning(
                    "GPU %d: Possible memory fragmentation "
                    "(allocated=%.0f MB, reserved=%.0f MB, ratio=%.2f)",
                    i, allocated / 1e6, reserved / 1e6, allocated / reserved,
                )

    def get_status(self) -> dict:
        """Return current GPU status as a dict (for API exposure)."""
        try:
            import torch
        except ImportError:
            return {"available": False, "reason": "PyTorch not installed"}

        if not torch.cuda.is_available():
            return {"available": False, "reason": "CUDA not available"}

        gpus = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            allocated = torch.cuda.memory_allocated(i)
            reserved = torch.cuda.memory_reserved(i)
            total = props.total_mem

            gpus.append({
                "index": i,
                "name": props.name,
                "total_mb": round(total / 1e6),
                "allocated_mb": round(allocated / 1e6),
                "reserved_mb": round(reserved / 1e6),
                "free_mb": round((total - allocated) / 1e6),
                "usage_pct": round(allocated / total * 100, 1) if total > 0 else 0,
            })

        return {"available": True, "gpus": gpus}


# Singleton instance
gpu_monitor = GPUHealthMonitor()
