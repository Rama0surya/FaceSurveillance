"""
Thread-safe global pipeline state for model toggles.

This module provides runtime ON/OFF switches that pipeline threads
read on every iteration.  Updates are instantaneous (no restart needed)
and are controlled via the ``PUT /api/settings/pipeline-toggles`` endpoint.

Design choices:
  - Separate module (not in config.py) to avoid Pydantic BaseSettings
    semantics and to keep runtime toggles distinct from env-based config.
  - Uses a threading.Lock for atomic read/write of multiple fields.
  - All public methods return plain dicts — safe for JSON serialisation.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class PipelineState:
    """Thread-safe singleton that holds runtime model toggles.

    Attributes:
        tracking_enabled:    When False, Thread B skips ByteTrack and runs
                             YOLO detection-only (no track_id assignment).
        insightface_enabled: When False, Thread C skips InsightFace age/gender,
                             DeepFace emotion, snapshot saving, and DB writes.
                             The GPU is effectively freed for detection only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tracking_enabled: bool = True
        self._insightface_enabled: bool = True

    # ---- Thread-safe property reads ----------------------------------
    # These are read by pipeline threads on every frame/task iteration.
    # Using @property with a lock ensures atomic reads even though Python's
    # GIL would make simple bool reads safe — we guard against future
    # expansion where multiple fields might need consistent reads.

    @property
    def tracking_enabled(self) -> bool:
        with self._lock:
            return self._tracking_enabled

    @property
    def insightface_enabled(self) -> bool:
        with self._lock:
            return self._insightface_enabled

    # ---- Bulk read / write -------------------------------------------

    def get_state(self) -> dict:
        """Return a snapshot of all toggle values (thread-safe)."""
        with self._lock:
            return {
                "tracking_enabled": self._tracking_enabled,
                "insightface_enabled": self._insightface_enabled,
            }

    def update(self, **kwargs) -> dict:
        """Update one or more toggles atomically.

        Only known fields are accepted; unknown keys are ignored.

        Returns:
            The full state dict after the update.
        """
        with self._lock:
            if "tracking_enabled" in kwargs:
                self._tracking_enabled = bool(kwargs["tracking_enabled"])
                logger.info("Pipeline toggle: tracking_enabled → %s", self._tracking_enabled)

            if "insightface_enabled" in kwargs:
                self._insightface_enabled = bool(kwargs["insightface_enabled"])
                logger.info("Pipeline toggle: insightface_enabled → %s", self._insightface_enabled)

            return {
                "tracking_enabled": self._tracking_enabled,
                "insightface_enabled": self._insightface_enabled,
            }


# Singleton — imported by detection.py and routes/settings.py
pipeline_state = PipelineState()
