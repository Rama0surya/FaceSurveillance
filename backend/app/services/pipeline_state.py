"""
Thread-safe global pipeline state for model toggles and runtime config.

This module provides:

  1. **PipelineState** — runtime ON/OFF switches that pipeline threads read
     on every iteration.  Updates are instantaneous (no restart needed) and
     are controlled via the ``PUT /api/settings/pipeline-toggles`` endpoint.

  2. **RuntimeConfig** — mutable detection parameters (intervals, thresholds)
     that can be changed at runtime via ``PUT /api/settings/detection-config``.
     Separated from Pydantic ``BaseSettings`` (which may be frozen in v2).

Design choices:
  - Uses ``threading.Event`` for boolean toggles — ``Event.is_set()`` is
    documented thread-safe and avoids lock acquisition on every read.
  - Uses a ``threading.Lock`` only for multi-field writes (update).
  - Monotonic ``_version`` counter lets pipeline threads cheaply detect
    toggle changes via ``version != cached_version`` (no lock needed).
  - All public methods return plain dicts — safe for JSON serialisation.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import NamedTuple

logger = logging.getLogger(__name__)


# =====================================================================
# PipelineToggleSnapshot — immutable snapshot for TOCTOU-safe reads
# =====================================================================

class ToggleSnapshot(NamedTuple):
    """Immutable snapshot of all toggles — read once, use consistently."""
    tracking_enabled: bool
    insightface_enabled: bool
    version: int


# =====================================================================
# PipelineState — runtime model toggles
# =====================================================================

class PipelineState:
    """Thread-safe singleton that holds runtime model toggles.

    Performance-optimised reads:
      - ``tracking_enabled`` and ``insightface_enabled`` use
        ``threading.Event.is_set()`` — documented thread-safe, zero lock
        contention even at 30+ FPS × N cameras.
      - ``snapshot()`` returns both toggles + version as an immutable
        ``ToggleSnapshot`` for TOCTOU-safe multi-field reads.
      - ``version`` is a monotonically increasing int; pipeline threads
        can compare ``version != cached`` to detect changes cheaply.

    Attributes:
        tracking_enabled:    When False, Thread B skips ByteTrack and runs
                             YOLO detection-only (no track_id assignment).
        insightface_enabled: When False, Thread C skips InsightFace age/gender,
                             DeepFace emotion, snapshot saving, and DB writes.
                             The GPU is effectively freed for detection only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Event flags — is_set() == True means feature is enabled.
        # Default: both ON.
        self._tracking_event = threading.Event()
        self._tracking_event.set()

        self._insightface_event = threading.Event()
        self._insightface_event.set()

        # Monotonic version counter — incremented on every update().
        # Pipeline threads compare ``version != cached_version`` to detect
        # toggle changes without lock acquisition.
        self._version: int = 0

    # ---- Lock-free property reads ------------------------------------
    # Event.is_set() is thread-safe (C-level atomic flag in CPython).
    # No lock acquisition needed — critical for hot-path reads.

    @property
    def tracking_enabled(self) -> bool:
        return self._tracking_event.is_set()

    @property
    def insightface_enabled(self) -> bool:
        return self._insightface_event.is_set()

    @property
    def version(self) -> int:
        return self._version

    # ---- TOCTOU-safe snapshot ----------------------------------------

    def snapshot(self) -> ToggleSnapshot:
        """Return an immutable snapshot of all toggle values.

        Use this when you need to read multiple toggles consistently
        (e.g., Thread B checks both tracking AND insightface in one
        iteration — prevents the state changing between the two reads).
        """
        return ToggleSnapshot(
            tracking_enabled=self._tracking_event.is_set(),
            insightface_enabled=self._insightface_event.is_set(),
            version=self._version,
        )

    # ---- Bulk read / write -------------------------------------------

    def get_state(self) -> dict:
        """Return a dict snapshot of all toggle values."""
        return {
            "tracking_enabled": self._tracking_event.is_set(),
            "insightface_enabled": self._insightface_event.is_set(),
            "version": self._version,
        }

    def update(self, **kwargs) -> dict:
        """Update one or more toggles atomically.

        Only known fields are accepted; unknown keys are ignored.
        Increments the version counter so pipeline threads can detect
        changes without polling get_state().

        Returns:
            The full state dict after the update.
        """
        with self._lock:
            changed = False

            if "tracking_enabled" in kwargs:
                val = bool(kwargs["tracking_enabled"])
                if val:
                    self._tracking_event.set()
                else:
                    self._tracking_event.clear()
                logger.info("Pipeline toggle: tracking_enabled → %s", val)
                changed = True

            if "insightface_enabled" in kwargs:
                val = bool(kwargs["insightface_enabled"])
                if val:
                    self._insightface_event.set()
                else:
                    self._insightface_event.clear()
                logger.info("Pipeline toggle: insightface_enabled → %s", val)
                changed = True

            if changed:
                self._version += 1

            return {
                "tracking_enabled": self._tracking_event.is_set(),
                "insightface_enabled": self._insightface_event.is_set(),
                "version": self._version,
            }


# =====================================================================
# RuntimeConfig — mutable detection parameters
# =====================================================================

@dataclass
class RuntimeConfig:
    """Mutable runtime detection configuration.

    These values are read by pipeline threads on every iteration.
    They are set via ``PUT /api/settings/detection-config`` and stored
    here instead of on ``settings`` (Pydantic BaseSettings) because
    Pydantic v2 freezes model attributes after construction.

    Thread-safety:
      - Simple attribute reads of Python floats/ints are GIL-atomic.
      - Writes are done from a single async route handler, so no lock
        is needed for writes either.
      - For compound reads (multiple fields at once), callers should
        read individual attrs into locals at the top of their loop
        iteration to get a consistent snapshot.
    """
    detection_interval: float = 2.0
    frame_fps: int = 5
    deepface_model: str = "VGG-Face"
    face_detector: str = "yolov8"
    yolo_confidence: float = 0.5
    face_tracker: str = "bytetrack"
    track_reanalyze_ttl: int = 300
    capture_min_confidence: float = 0.65
    min_face_size: int = 60
    capture_cooldown: float = 5.0
    reader_decode_fps: int = 3
    broadcast_fps: int = 5

    def to_dict(self) -> dict:
        """Return a plain dict of all config values."""
        return {
            "detection_interval": self.detection_interval,
            "frame_fps": self.frame_fps,
            "deepface_model": self.deepface_model,
            "face_detector": self.face_detector,
            "yolo_confidence": self.yolo_confidence,
            "face_tracker": self.face_tracker,
            "track_reanalyze_ttl": self.track_reanalyze_ttl,
            "capture_min_confidence": self.capture_min_confidence,
            "min_face_size": self.min_face_size,
            "capture_cooldown": self.capture_cooldown,
            "reader_decode_fps": self.reader_decode_fps,
            "broadcast_fps": self.broadcast_fps,
        }


def _create_runtime_config() -> RuntimeConfig:
    """Create RuntimeConfig initialised from env-based Settings."""
    from app.core.config import settings

    return RuntimeConfig(
        detection_interval=settings.DETECTION_INTERVAL_SECONDS,
        frame_fps=settings.FRAME_BROADCAST_FPS,
        deepface_model=settings.DEEPFACE_MODEL,
        face_detector=settings.FACE_DETECTOR,
        yolo_confidence=settings.YOLO_CONFIDENCE,
        face_tracker=settings.FACE_TRACKER,
        track_reanalyze_ttl=settings.TRACK_REANALYZE_TTL,
        capture_min_confidence=settings.CAPTURE_MIN_CONFIDENCE,
        min_face_size=settings.MIN_FACE_SIZE,
        capture_cooldown=settings.CAPTURE_COOLDOWN,
        reader_decode_fps=settings.READER_DECODE_FPS,
        broadcast_fps=settings.BROADCAST_FPS,
    )


# =====================================================================
# Singletons — imported by detection.py and routes/settings.py
# =====================================================================

pipeline_state = PipelineState()
runtime_config = _create_runtime_config()
