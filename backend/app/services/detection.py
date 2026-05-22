"""
Detection engine — runs face detection on RTSP/HLS streams.

Architecture: 4-Thread Producer-Consumer Pipeline
=================================================

Each camera gets its own ``StreamWorker`` with **four decoupled threads**:

  Thread A — **RTSP Frame Grabber**
    Reads frames from the RTSP stream as fast as possible (30 FPS+).
    Puts frames into two bounded queues: ``frame_queue`` (for AI) and
    ``broadcast_queue`` (for frontend).  If either queue is full, the
    oldest frame is **dropped** (frame-skipping) so that downstream
    consumers always get the freshest frame available.

  Thread B — **YOLO + ByteTrack Detector** (AI-only, no broadcast)
    Pulls frames from ``frame_queue``, runs YOLOv8n-face detection and
    (optionally) ByteTrack tracking.  Applies smart capture filters:
    confidence threshold, minimum face size, and per-track cooldown
    with emotion-change bypass.  When capture criteria are met,
    enqueues ``AnalysisTask`` for Thread C.

  Thread C — **Heavy Inference Worker**
    Pulls ``AnalysisTask`` items from ``analysis_queue``.
    Runs InsightFace (age/gender) + DeepFace (emotion), saves snapshots,
    persists to DB, evaluates alerts, and broadcasts results via WebSocket.
    Can be toggled OFF entirely via pipeline_state for maximum FPS.

  Thread D — **Frame Broadcast Worker** (DECOUPLED from AI)
    Pulls frames from ``broadcast_queue`` and pushes JPEG-encoded frames
    to all MJPEG client queues.  Runs at the configured ``frame_fps``
    rate, completely independent of YOLO/InsightFace inference timing.
    Frontend streams are NEVER blocked by AI inference latency.

Runtime Toggles (via ``pipeline_state``):
  - ``tracking_enabled``:    ON/OFF ByteTrack in Thread B
  - ``insightface_enabled``: ON/OFF heavy inference in Thread C

Smart Capture Filters:
  - Confidence threshold (CAPTURE_MIN_CONFIDENCE)
  - Minimum face size (MIN_FACE_SIZE)
  - Per-track cooldown (CAPTURE_COOLDOWN) with emotion-change bypass

Pipeline modes:
  - **Modern** (default): YOLOv8n-face → ByteTrack → InsightFace → DeepFace emotion
  - **Legacy** (fallback): DeepFace.analyze() for everything

Refactoring changelog:
  - **Thread D decoupling**: Frame broadcast moved out of Thread B into
    dedicated Thread D — eliminates AI-induced stream lag
  - Lock-free toggle reads via pipeline_state.snapshot()
  - Runtime config reads from runtime_config (not Pydantic settings)
  - Fixed safe_put_frame threading issue for MJPEG queues
  - Eliminated double-cooldown bug between Thread B and Thread C
  - Reduced memory allocations: shared full_frame copy across tasks
  - Smarter track state cleanup (time-based, lower threshold)
  - Removed dead AnalysisTask.Config (Pydantic concept in dataclass)
  - Safe track_id sentinel (-1) when tracking is disabled
"""

from __future__ import annotations

import asyncio
# base64 import removed — WS frame broadcast eliminated (MJPEG only)
import io
import logging
import queue
import threading
import time
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.db_client import upload_snapshot
from app.core.websocket import manager as ws_manager
from app.core.sse import sse_manager
from app.db.detections import insert_detection, insert_snapshot
from app.db.stats import upsert_hourly_stats
from app.db.cameras import update_camera_status, get_camera_raw
from app.services.alert_engine import alert_engine
from app.services.pipeline_state import pipeline_state, runtime_config

logger = logging.getLogger(__name__)


# =====================================================================
# Age classification helper
# =====================================================================

def classify_age(age: int) -> str:
    """Map a numeric age to a group label."""
    if age < 13:
        return "anak"
    elif age < 18:
        return "remaja"
    elif age < 60:
        return "dewasa"
    else:
        return "lansia"


# =====================================================================
# Detection zone helper
# =====================================================================

def _is_face_in_zone(
    face_region: dict,
    detection_zone: Optional[dict],
) -> bool:
    """Check whether the centre of a face bbox falls inside the detection zone polygon.

    If no detection zone is configured, every face is accepted.
    """
    if detection_zone is None:
        return True

    points = detection_zone.get("points")
    if not points or len(points) < 3:
        return True  # invalid polygon — accept all

    # Build a NumPy contour from the polygon points
    contour = np.array(points, dtype=np.float32).reshape((-1, 1, 2))

    # Centre of the face bounding box
    cx = face_region.get("x", 0) + face_region.get("w", 0) / 2
    cy = face_region.get("y", 0) + face_region.get("h", 0) / 2

    # pointPolygonTest returns positive if inside, 0 on edge, negative if outside
    result = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False)
    return result >= 0


# =====================================================================
# TrackState — per-track capture state for smart cooldown
# =====================================================================

@dataclass
class TrackState:
    """Mutable state for a tracked face ID.

    Stored in ``StreamWorker._track_state`` and accessed only by the
    StreamWorker's own threads (Thread B for reads, Thread C for writes),
    with a lock protecting cross-thread access.
    """
    last_capture_time: float = 0.0     # time.time() of last capture
    last_emotion: str = ""             # emotion string from last analysis


# =====================================================================
# AnalysisTask — immutable work item for Thread C
# =====================================================================

@dataclass(frozen=True)
class AnalysisTask:
    """Immutable data container passed from Thread B → Thread C.

    Using ``frozen=True`` prevents accidental mutation across threads.
    All NumPy arrays are **independent copies** (ownership transferred
    at creation time), so no race conditions on pixel data.
    """
    camera_id: str
    frame_crop: np.ndarray       # Padded face crop for InsightFace (independent copy)
    full_frame: np.ndarray       # Full frame copy for snapshot saving (shared across tasks)
    bbox: dict                   # {"x", "y", "w", "h"} — plain dict, safe
    track_id: int                # -1 sentinel when tracking is disabled
    confidence: float
    timestamp: str


# =====================================================================
# MJPEG safe-put helper (fixed for asyncio.Queue from non-loop thread)
# =====================================================================

def _safe_put_frame_sync(q: asyncio.Queue, frame_bytes: bytes) -> None:
    """Non-blocking put into an asyncio.Queue — must be called from the event loop thread.

    This function is invoked via ``loop.call_soon_threadsafe()``, so it
    executes on the event loop thread where asyncio.Queue operations are safe.

    Drop-oldest-on-full strategy prevents unbounded memory growth.
    """
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        q.put_nowait(frame_bytes)
    except asyncio.QueueFull:
        pass  # extremely unlikely after drop — just skip


# =====================================================================
# Stream worker (3-thread producer-consumer pipeline)
# =====================================================================

class StreamWorker:
    """Background worker that reads frames and runs detection.

    Manages three threads per camera:
      - Thread A: RTSP frame grabber  (I/O-bound, never blocked by AI)
      - Thread B: YOLO + ByteTrack    (GPU-bound, fast ~30-80ms)
      - Thread C: Heavy inference      (GPU-bound, slow, only new faces)

    Runtime toggles from ``pipeline_state`` are checked on every iteration,
    allowing instant ON/OFF of tracking and InsightFace without restart.

    Runtime config from ``runtime_config`` is read on every iteration,
    allowing instant parameter changes without restart.
    """

    def __init__(self, camera_id: str, rtsp_url: str, loop: asyncio.AbstractEventLoop) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._loop = loop  # main asyncio event loop (for WS broadcast)
        self._stop_event = threading.Event()

        # ---- Inter-thread queues ----
        self._frame_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(
            maxsize=max(1, settings.FRAME_QUEUE_SIZE),
        )
        self._analysis_queue: queue.Queue[Optional[AnalysisTask]] = queue.Queue(
            maxsize=max(1, settings.ANALYSIS_QUEUE_SIZE),
        )
        # Broadcast queue (Thread A → Thread D) — decoupled from AI pipeline.
        # Frontend always gets fresh frames regardless of YOLO/InsightFace latency.
        self._broadcast_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(
            maxsize=2,  # Small = always the freshest frame
        )

        # ---- Thread references ----
        self._threads: list[threading.Thread] = []

        # Load detection zone from camera config
        self._detection_zone: Optional[dict] = None
        self._load_detection_zone()

        # ---- Smart capture state ----
        # track_id → TrackState  (shared between Thread B reads & Thread C writes)
        self._track_state: dict[int, TrackState] = {}
        self._track_state_lock = threading.Lock()
        self._last_track_cleanup: float = 0.0  # time-based cleanup instead of count-based

        # ---- MJPEG streaming queues ----
        self._mjpeg_queues: list[tuple[asyncio.Queue[bytes], asyncio.AbstractEventLoop]] = []
        self._mjpeg_queues_lock = threading.Lock()

        # --- Tracker model (modern pipeline) ---
        self._tracker_model = None
        self._init_tracker()

    def _init_tracker(self) -> None:
        """Create a per-camera YOLO tracker instance if modern pipeline is active."""
        try:
            from app.services.model_manager import model_manager
            if not model_manager.legacy_mode:
                self._tracker_model = model_manager.create_tracker()
                if self._tracker_model:
                    logger.info(
                        "Tracker model initialized for camera %s", self.camera_id
                    )
                else:
                    logger.warning(
                        "Failed to create tracker for camera %s — will use legacy mode",
                        self.camera_id,
                    )
        except Exception:
            logger.exception("Error initializing tracker for camera %s", self.camera_id)

    def _load_detection_zone(self) -> None:
        """Fetch the camera's detection_zone from DB."""
        try:
            cam_data = get_camera_raw(self.camera_id)
            if cam_data:
                self._detection_zone = cam_data.get("detection_zone")
        except Exception:
            logger.exception("Failed to load detection_zone for camera %s", self.camera_id)

    # ---- lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Spin up all three pipeline threads."""
        self._stop_event.clear()

        # Drain any stale items from previous runs
        self._drain_queue(self._frame_queue)
        self._drain_queue(self._analysis_queue)

        thread_specs = [
            ("grabber",     self._frame_grabber_loop),
            ("detector",    self._detection_loop),
            ("analyzer",    self._analysis_worker_loop),
            ("broadcaster", self._broadcast_worker_loop),
        ]

        for name, target in thread_specs:
            t = threading.Thread(
                target=target,
                name=f"{name}-{self.camera_id[:8]}",
                daemon=True,
            )
            self._threads.append(t)
            t.start()

        logger.info(
            "StreamWorker started for camera %s — 4 threads active",
            self.camera_id,
        )

    def stop(self) -> None:
        """Signal all threads to stop and wait for them to finish."""
        self._stop_event.set()

        # Inject sentinel values to unblock any thread waiting on queue.get()
        for q in (self._frame_queue, self._analysis_queue, self._broadcast_queue):
            try:
                q.put_nowait(None)
            except queue.Full:
                pass

        for t in self._threads:
            if t.is_alive():
                t.join(timeout=10)
        self._threads.clear()

        logger.info("StreamWorker stopped for camera %s", self.camera_id)

    @property
    def is_alive(self) -> bool:
        """True if at least the grabber and detector threads are running."""
        return any(t.is_alive() for t in self._threads)

    @staticmethod
    def _drain_queue(q: queue.Queue) -> None:
        """Empty a queue without blocking (best-effort cleanup)."""
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break

    # ---- TrackState helpers (thread-safe) -----------------------------

    def _get_track_state(self, track_id: int) -> Optional[TrackState]:
        """Read TrackState for a given track_id (thread-safe)."""
        with self._track_state_lock:
            return self._track_state.get(track_id)

    def _set_track_capture(self, track_id: int, emotion: str) -> None:
        """Record a capture event for a track_id (thread-safe).

        Called by Thread C after successful analysis.
        """
        with self._track_state_lock:
            state = self._track_state.get(track_id)
            if state is None:
                self._track_state[track_id] = TrackState(
                    last_capture_time=time.time(),
                    last_emotion=emotion,
                )
            else:
                state.last_capture_time = time.time()
                state.last_emotion = emotion

    def _mark_track_pending(self, track_id: int) -> None:
        """Mark a track_id as pending capture (Thread B).

        Sets last_capture_time so subsequent checks don't re-enqueue
        while Thread C is still processing.
        """
        with self._track_state_lock:
            state = self._track_state.get(track_id)
            if state is None:
                self._track_state[track_id] = TrackState(
                    last_capture_time=time.time(),
                    last_emotion="",
                )
            else:
                state.last_capture_time = time.time()

    def _cleanup_stale_tracks(self, cooldown: float) -> None:
        """Remove track states older than TTL, on a time-based interval.

        Runs at most once every 30 seconds to avoid overhead.
        Uses ``max(cooldown * 3, 30.0)`` as TTL — aggressive enough to
        prevent memory growth in crowded scenes.
        """
        now = time.time()
        if now - self._last_track_cleanup < 30.0:
            return  # too soon, skip

        self._last_track_cleanup = now
        max_age = max(cooldown * 3, 30.0)
        cutoff = now - max_age

        with self._track_state_lock:
            before = len(self._track_state)
            if before <= 20:
                return  # not worth cleaning yet

            self._track_state = {
                tid: s for tid, s in self._track_state.items()
                if s.last_capture_time > cutoff
            }
            after = len(self._track_state)
            if before != after:
                logger.debug(
                    "[Camera %s] Track state cleanup: %d → %d entries",
                    self.camera_id[:8], before, after,
                )

    def register_mjpeg_queue(self, q: asyncio.Queue[bytes], loop: asyncio.AbstractEventLoop) -> None:
        """Register an asyncio queue for MJPEG streaming."""
        with self._mjpeg_queues_lock:
            self._mjpeg_queues.append((q, loop))
            logger.info("MJPEG queue registered for camera %s, total=%d", self.camera_id, len(self._mjpeg_queues))

    def unregister_mjpeg_queue(self, q: asyncio.Queue[bytes]) -> None:
        """Unregister an asyncio queue from MJPEG streaming."""
        with self._mjpeg_queues_lock:
            self._mjpeg_queues = [item for item in self._mjpeg_queues if item[0] is not q]
            logger.info("MJPEG queue unregistered for camera %s, total=%d", self.camera_id, len(self._mjpeg_queues))

    # =================================================================
    # THREAD A — RTSP Frame Grabber
    # =================================================================

    def _frame_grabber_loop(self) -> None:
        """Thread A: Read frames from RTSP as fast as possible.

        This thread's ONLY job is to keep the RTSP buffer drained and
        deliver the freshest possible frame to Thread B.  It is **never**
        blocked by AI inference.

        Frame-skipping strategy:
          If ``frame_queue`` is full, the oldest frame is silently
          discarded and replaced with the newer one.  This guarantees
          Thread B always processes the most recent frame.

        Reconnect strategy:
          On stream failure, retries with exponential backoff
          (2s → 4s → 8s → … → 30s max).

        Memory optimisation:
          cv2.VideoCapture.read() returns a new buffer per call on most
          backends.  We attempt put_nowait first; only if the queue has
          space do we commit the frame.  If full, we drop-oldest then put.
          No unnecessary .copy() — the frame from read() is already our
          exclusive reference.
        """
        logger.info(
            "[Thread-A] Frame grabber started for camera %s (%s)",
            self.camera_id, self.rtsp_url,
        )
        update_camera_status(self.camera_id, "processing")

        cap: Optional[cv2.VideoCapture] = None
        retry_delay = 2  # seconds between reconnect attempts

        while not self._stop_event.is_set():
            try:
                cap = cv2.VideoCapture(self.rtsp_url)
                if not cap.isOpened():
                    logger.warning(
                        "[Thread-A] Cannot open stream %s — retrying in %ds",
                        self.rtsp_url, retry_delay,
                    )
                    self._stop_event.wait(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)
                    continue

                # Stream opened successfully
                update_camera_status(self.camera_id, "live")
                retry_delay = 2
                logger.info("[Thread-A] Stream opened for camera %s", self.camera_id)

                while not self._stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning(
                            "[Thread-A] Lost frame from camera %s — reconnecting",
                            self.camera_id,
                        )
                        break  # will reconnect

                    # --------------------------------------------------
                    # Enqueue frame with frame-skipping semantics:
                    # If queue is full, drop the oldest frame, put the new one.
                    # cv2 read() typically gives us a unique buffer, but some
                    # backends reuse buffers — .copy() ensures safety.
                    # --------------------------------------------------
                    # Single copy shared between AI queue and broadcast queue.
                    # Both Thread B and Thread D only read the frame.
                    frame_copy = frame.copy()

                    # ---- Enqueue for AI (Thread B) ----
                    try:
                        self._frame_queue.put_nowait(frame_copy)
                    except queue.Full:
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._frame_queue.put_nowait(frame_copy)
                        except queue.Full:
                            pass

                    # ---- Enqueue for Broadcast (Thread D) ----
                    try:
                        self._broadcast_queue.put_nowait(frame_copy)
                    except queue.Full:
                        try:
                            self._broadcast_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._broadcast_queue.put_nowait(frame_copy)
                        except queue.Full:
                            pass

            except Exception:
                logger.exception(
                    "[Thread-A] Frame grabber error (camera %s)", self.camera_id,
                )
                self._stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
            finally:
                if cap is not None:
                    cap.release()
                    cap = None

        # Thread stopping
        update_camera_status(self.camera_id, "offline")
        logger.info("[Thread-A] Frame grabber stopped for camera %s", self.camera_id)

    # =================================================================
    # THREAD B — YOLO + ByteTrack Detection & Tracking
    # =================================================================

    def _detection_loop(self) -> None:
        """Thread B: Fast detection + tracking (AI ONLY — no broadcast).

        Pulls frames from ``frame_queue``, runs YOLOv8n-face + (optionally)
        ByteTrack, applies smart capture filters, and enqueues
        ``AnalysisTask`` for new faces.

        Frame broadcast has been moved to Thread D (broadcast worker)
        so that AI inference latency NEVER delays the frontend stream.

        Toggle-aware (lock-free via pipeline_state.snapshot()):
          - ``tracking_enabled == False`` → skip ByteTrack
          - ``insightface_enabled == False`` → skip enqueue
        """
        from app.services.model_manager import model_manager

        logger.info("[Thread-B] Detector started for camera %s", self.camera_id)

        # Detection throttle — prevent running YOLO on every single frame
        last_detection = 0.0

        while not self._stop_event.is_set():
            # ---- Pull frame from queue ----
            try:
                frame = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue  # No frame yet, check stop_event and retry

            # Sentinel check (shutdown signal)
            if frame is None:
                break

            now = time.time()

            # ---- Read runtime config (lock-free, GIL-atomic) ----
            detection_interval = runtime_config.detection_interval

            # NOTE: Frame broadcast has been moved to Thread D.
            # Thread B is now 100% dedicated to AI inference.

            # ---- Detection interval gate ----
            # Only run AI detection every detection_interval seconds.
            if now - last_detection < detection_interval:
                continue
            last_detection = now

            # ---- Dispatch to modern or legacy pipeline ----
            if model_manager.legacy_mode or self._tracker_model is None:
                self._process_frame_legacy(frame)
            else:
                self._process_frame_modern(frame)

        logger.info("[Thread-B] Detector stopped for camera %s", self.camera_id)

    # =================================================================
    # THREAD D — Frame Broadcast Worker (DECOUPLED from AI)
    # =================================================================

    def _broadcast_worker_loop(self) -> None:
        """Thread D: Dedicated frame broadcaster — NEVER blocked by AI.

        Pulls frames from ``broadcast_queue`` (fed by Thread A) and pushes
        JPEG-encoded frames to all MJPEG client queues.

        This thread runs at the configured ``frame_fps`` rate, completely
        independent of YOLO/InsightFace inference timing.

        Why a separate thread?
          Thread B previously handled both AI detection AND frame broadcast.
          When YOLO takes 100ms+, the broadcast was delayed, causing visible
          lag on the frontend.  Thread D eliminates this coupling entirely.
        """
        logger.info(
            "[Thread-D] Broadcast worker started for camera %s", self.camera_id
        )

        last_broadcast = 0.0

        while not self._stop_event.is_set():
            # ---- Pull frame from broadcast queue ----
            try:
                frame = self._broadcast_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Sentinel check (shutdown signal)
            if frame is None:
                break

            now = time.time()

            # ---- Throttle by configured FPS ----
            frame_interval = 1.0 / max(runtime_config.frame_fps, 1)
            if now - last_broadcast < frame_interval:
                continue  # Too soon — skip this frame (drop-oldest semantics)
            last_broadcast = now

            # ---- Broadcast to MJPEG clients ----
            self._broadcast_frame(frame)

        logger.info(
            "[Thread-D] Broadcast worker stopped for camera %s", self.camera_id
        )

    def _process_frame_modern(self, frame: np.ndarray) -> None:
        """Modern pipeline (Thread B): detect → filter → smart capture → enqueue.

        Smart capture filter chain:
          1. YOLO confidence ≥ capture_min_confidence
          2. Face bbox ≥ min_face_size × min_face_size pixels
          3. Detection zone check
          4. Per-track cooldown (capture_cooldown) with emotion-change bypass

        Toggle-aware (using snapshot for TOCTOU consistency):
          - tracking_enabled OFF → YOLO detection only (no ByteTrack)
          - insightface_enabled OFF → skip enqueue entirely (no Thread C work)
        """
        from app.services.model_manager import model_manager

        # ---- Read runtime toggles (lock-free snapshot) ----
        toggles = pipeline_state.snapshot()
        tracking_on = toggles.tracking_enabled
        analysis_on = toggles.insightface_enabled

        # ---- Read smart capture thresholds (GIL-atomic reads) ----
        min_confidence = runtime_config.capture_min_confidence
        min_face_size = runtime_config.min_face_size
        capture_cooldown = runtime_config.capture_cooldown

        # ---- Step 1: Detect (+Track if enabled) ----
        tracker_cfg = runtime_config.face_tracker
        tracker_yaml = f"{tracker_cfg}.yaml" if tracker_cfg != "none" else None
        yolo_conf = runtime_config.yolo_confidence

        try:
            if tracking_on and tracker_yaml:
                # ByteTrack enabled — full detect + track
                tracked_faces = model_manager.detect_and_track(
                    self._tracker_model,
                    frame,
                    tracker=tracker_yaml,
                    conf=yolo_conf,
                    persist=True,
                )
            else:
                # Tracking disabled OR no tracker config — detection only
                tracked_faces = model_manager.detect_faces_yolo(frame, conf=yolo_conf)
                # Assign sentinel track_id = -1 (not a real ByteTrack ID)
                # This prevents collisions with real IDs when tracking is re-enabled.
                for f in tracked_faces:
                    f["track_id"] = -1
        except Exception:
            logger.exception("[Thread-B] YOLO detect/track failed for camera %s", self.camera_id)
            return

        if not tracked_faces:
            return

        # ---- Step 2: Confidence filter (anti-false-positive) ----
        tracked_faces = [
            f for f in tracked_faces
            if f.get("confidence", 0) >= min_confidence
        ]

        if not tracked_faces:
            return

        # ---- Step 3: Face size filter (anti-background) ----
        tracked_faces = [
            f for f in tracked_faces
            if f["bbox"]["w"] >= min_face_size and f["bbox"]["h"] >= min_face_size
        ]

        if not tracked_faces:
            return

        # ---- Step 4: Detection zone filter ----
        tracked_faces = [
            f for f in tracked_faces
            if _is_face_in_zone(f["bbox"], self._detection_zone)
        ]

        if not tracked_faces:
            return

        # ---- Step 5: If InsightFace is OFF, stop here (no capture) ----
        if not analysis_on:
            return

        # ---- Step 6: Smart cooldown + emotion-change bypass ----
        # Thread B is the SOLE gatekeeper for cooldown. Thread C only
        # analyzes and updates emotion state — it does NOT re-check cooldown.
        now = time.time()
        faces_to_capture: list[dict] = []

        for face in tracked_faces:
            track_id = face.get("track_id", -1)

            # Only apply per-track cooldown if tracking is active (track_id >= 0)
            if track_id >= 0 and tracking_on:
                state = self._get_track_state(track_id)

                if state is not None:
                    time_since_last = now - state.last_capture_time

                    if time_since_last < capture_cooldown:
                        # Within cooldown — skip unless we detect emotion change.
                        # But Thread B doesn't know the NEW emotion yet (Thread C
                        # handles that). So we simply enforce the time cooldown here.
                        #
                        # The emotion-change bypass works as follows:
                        # When Thread C detects a DIFFERENT emotion, it calls
                        # _set_track_capture() with the new emotion but does NOT
                        # reset last_capture_time. This means the next time
                        # Thread B checks, the cooldown will have naturally expired
                        # (or the emotion data is already recorded for future comparison).
                        #
                        # For a true emotion-change bypass (capture immediately when
                        # expression changes), Thread C resets last_capture_time to 0
                        # when emotion differs, so the NEXT Thread B cycle will pass
                        # the cooldown check immediately.
                        continue

                # Either new track or cooldown expired → mark pending and capture
                self._mark_track_pending(track_id)

            faces_to_capture.append(face)

        # Periodic cleanup of stale track states (time-based, every 30s)
        self._cleanup_stale_tracks(cooldown=capture_cooldown)

        if not faces_to_capture:
            return

        # ---- Step 7: Enqueue faces for Thread C (heavy inference) ----
        timestamp = datetime.now(timezone.utc).isoformat()

        # Share a single full_frame copy across all AnalysisTask objects from
        # this frame — Thread C only reads it (for snapshot saving), so sharing
        # is safe.  Saves ~6MB per extra face on 1080p frames.
        shared_full_frame = frame.copy()

        for face_data in faces_to_capture:
            bbox = face_data["bbox"]

            # Create padded crop for InsightFace (independent copy)
            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            pad = int(max(w, h) * 0.15)
            y1 = max(0, y - pad)
            y2 = min(frame.shape[0], y + h + pad)
            x1 = max(0, x - pad)
            x2 = min(frame.shape[1], x + w + pad)
            crop = frame[y1:y2, x1:x2].copy()  # Independent copy — no shared state

            if crop.size == 0:
                continue

            task = AnalysisTask(
                camera_id=self.camera_id,
                frame_crop=crop,
                full_frame=shared_full_frame,  # Shared reference (read-only in Thread C)
                bbox=bbox,
                track_id=face_data.get("track_id", -1),
                confidence=face_data.get("confidence", 0.0),
                timestamp=timestamp,
            )

            try:
                self._analysis_queue.put_nowait(task)
            except queue.Full:
                logger.debug(
                    "[Thread-B] Analysis queue full — skipping face track_id=%s",
                    task.track_id,
                )

    # =================================================================
    # THREAD C — Heavy Inference Worker
    # =================================================================

    def _analysis_worker_loop(self) -> None:
        """Thread C: InsightFace + DeepFace + Snapshot + DB + Alerts.

        Pulls ``AnalysisTask`` items from ``analysis_queue`` and performs
        the expensive analysis pipeline.  This thread runs **only for
        faces that passed smart capture filters** in Thread B.

        Toggle-aware:
          If ``pipeline_state.insightface_enabled == False``, this thread
          drains the queue but does NOT run any inference or I/O —
          effectively idling and freeing GPU resources.

        Emotion-change tracking (the bypass mechanism):
          After analysis, compares new_emotion vs last_emotion in TrackState.
          If emotion CHANGED → resets last_capture_time to 0, so Thread B's
          cooldown check will immediately allow the next capture cycle.
          If emotion is SAME → normal: just update emotion, keep the
          current last_capture_time (cooldown continues normally).
        """
        from app.services.model_manager import model_manager

        logger.info("[Thread-C] Analysis worker started for camera %s", self.camera_id)

        # Batch accumulator
        batch: list[dict] = []
        batch_timestamp: Optional[str] = None
        batch_stats_male = 0
        batch_stats_female = 0
        batch_dominant_emotion: Optional[str] = None
        batch_deadline = 0.0

        BATCH_WINDOW = 0.5  # seconds — wait up to 500ms to batch-collect faces

        while not self._stop_event.is_set():
            # ---- Pull task from queue ----
            try:
                task = self._analysis_queue.get(timeout=0.3)
            except queue.Empty:
                # Check if we have a pending batch to flush
                if batch and time.time() >= batch_deadline:
                    self._flush_batch(
                        batch, batch_timestamp,
                        batch_stats_male, batch_stats_female,
                        batch_dominant_emotion,
                    )
                    batch = []
                    batch_stats_male = 0
                    batch_stats_female = 0
                    batch_dominant_emotion = None
                continue

            # Sentinel check (shutdown signal)
            if task is None:
                break

            # ---- Toggle check: if InsightFace is OFF, discard task ----
            if not pipeline_state.insightface_enabled:
                continue

            # ---- Analyze face ----
            try:
                ag = self._analyze_age_gender(model_manager, task.frame_crop)
                emo = self._analyze_emotion(model_manager, task.frame_crop)
            except Exception:
                logger.debug(
                    "[Thread-C] Analysis failed for track_id=%s on camera %s",
                    task.track_id, task.camera_id,
                )
                ag = {"age": 0, "gender": "unknown"}
                emo = {"emotion": "neutral"}

            new_emotion = emo["emotion"]

            # ---- Emotion-change tracking (smart capture bypass) ----
            # Thread C does NOT re-check cooldown (Thread B already did).
            # Thread C's job:
            #   1. Analyse the face (done above).
            #   2. Compare new emotion vs. last recorded emotion.
            #   3. If emotion changed → reset cooldown (last_capture_time=0)
            #      so Thread B allows immediate re-capture next cycle.
            #   4. If emotion same → normal update (keep existing cooldown).
            if task.track_id >= 0:
                prev_state = self._get_track_state(task.track_id)
                if prev_state and prev_state.last_emotion and prev_state.last_emotion != new_emotion:
                    # Emotion CHANGED — bypass: reset cooldown so Thread B
                    # allows the next capture immediately.
                    with self._track_state_lock:
                        state = self._track_state.get(task.track_id)
                        if state:
                            state.last_capture_time = 0.0
                            state.last_emotion = new_emotion
                else:
                    # Same emotion or first capture — normal update
                    self._set_track_capture(task.track_id, new_emotion)

            age_group = classify_age(ag["age"])

            # ---- Save snapshot (disk I/O — fine in background thread) ----
            snapshot_url = self._save_snapshot(task.full_frame, task.bbox)

            face_dict = {
                "id": str(uuid.uuid4()),
                "track_id": task.track_id,
                "bbox": task.bbox,
                "gender": ag["gender"],
                "emotion": new_emotion,
                "age_group": age_group,
                "age": ag["age"],
                "confidence": round(task.confidence, 2),
                "snapshot_url": snapshot_url,
            }

            # Accumulate into batch
            batch.append(face_dict)
            if batch_timestamp is None:
                batch_timestamp = task.timestamp
                batch_deadline = time.time() + BATCH_WINDOW

            if ag["gender"] == "male":
                batch_stats_male += 1
            else:
                batch_stats_female += 1
            batch_dominant_emotion = new_emotion

            # Update hourly stats (per-face, non-blocking)
            try:
                gender_val = "Man" if ag["gender"] == "male" else "Woman"
                upsert_hourly_stats(
                    camera_id=self.camera_id,
                    gender=gender_val,
                    emotion=new_emotion,
                    age_group=age_group,
                )
            except Exception:
                logger.exception("[Thread-C] Stats upsert failed for camera %s", self.camera_id)

            # Auto-flush if batch is large enough
            if len(batch) >= 5:
                self._flush_batch(
                    batch, batch_timestamp,
                    batch_stats_male, batch_stats_female,
                    batch_dominant_emotion,
                )
                batch = []
                batch_timestamp = None
                batch_stats_male = 0
                batch_stats_female = 0
                batch_dominant_emotion = None

        # Flush any remaining batch on shutdown
        if batch:
            self._flush_batch(
                batch, batch_timestamp,
                batch_stats_male, batch_stats_female,
                batch_dominant_emotion,
            )

        logger.info("[Thread-C] Analysis worker stopped for camera %s", self.camera_id)

    @staticmethod
    def _analyze_age_gender(model_manager, crop: np.ndarray) -> dict:
        """Run InsightFace age/gender on a face crop (with DeepFace fallback)."""
        return model_manager.analyze_age_gender_from_crop(crop)

    @staticmethod
    def _analyze_emotion(model_manager, crop: np.ndarray) -> dict:
        """Run DeepFace emotion analysis on a face crop."""
        return model_manager.analyze_emotion_from_crop(crop)

    # ---- batch flush (Thread C helper) --------------------------------

    def _flush_batch(
        self,
        faces_payload: list[dict],
        timestamp: Optional[str],
        stats_male: int,
        stats_female: int,
        dominant_emotion: Optional[str],
    ) -> None:
        """Persist a batch of analyzed faces and broadcast via WebSocket."""
        if not faces_payload:
            return

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        self._persist_and_broadcast(faces_payload, ts, stats_male, stats_female, dominant_emotion)

    # ---- detection (legacy pipeline) ---------------------------------

    def _process_frame_legacy(self, frame: np.ndarray) -> None:
        """Legacy pipeline: DeepFace.analyze() for everything (fallback).

        NOTE: In legacy mode, all processing happens in Thread B since we
        cannot decouple detection from analysis (DeepFace does everything).

        Toggle-aware:
          - ``insightface_enabled == False`` → skip entirely (no analysis)
        Smart capture filters:
          - Face size filter (MIN_FACE_SIZE)
          - Confidence filter (CAPTURE_MIN_CONFIDENCE)
          - Detection zone filter
        """
        # ---- Toggle check: if InsightFace/analysis is OFF, skip entirely ----
        if not pipeline_state.insightface_enabled:
            return

        try:
            from deepface import DeepFace

            results = DeepFace.analyze(
                img_path=frame,
                actions=["emotion", "age", "gender"],
                enforce_detection=False,
                silent=True,
            )
        except Exception:
            logger.exception("[Thread-B] DeepFace.analyze failed for camera %s", self.camera_id)
            return

        # DeepFace may return a single dict or a list
        if isinstance(results, dict):
            results = [results]

        if not results:
            return

        # ---- Read smart capture thresholds ----
        min_face_size = runtime_config.min_face_size
        min_confidence = runtime_config.capture_min_confidence

        timestamp = datetime.now(timezone.utc).isoformat()
        faces_payload: list[dict] = []
        stats_male = 0
        stats_female = 0
        dominant_emotion = None

        for face_result in results:
            region = face_result.get("region", {})
            x = region.get("x", 0)
            y = region.get("y", 0)
            w = region.get("w", 0)
            h = region.get("h", 0)

            # Skip if the detection bbox is essentially the full frame
            if w <= 0 or h <= 0:
                continue

            # ---- Face size filter (anti-background) ----
            if w < min_face_size or h < min_face_size:
                continue

            confidence = face_result.get("face_confidence", 0.0)

            # ---- Confidence filter (anti-false-positive) ----
            if confidence and confidence < min_confidence:
                continue

            # ---- Detection zone filtering ----
            if not _is_face_in_zone(region, self._detection_zone):
                continue

            age_raw = int(face_result.get("age", 0))
            age_group = classify_age(age_raw)

            dominant_emotion_val = face_result.get("dominant_emotion", "neutral")
            gender_val = face_result.get("dominant_gender", "Man")

            # Crop & save snapshot
            bbox = {"x": x, "y": y, "w": w, "h": h}
            snapshot_url = self._save_snapshot(frame, bbox)

            face_id = str(uuid.uuid4())

            face_dict = {
                "id": face_id,
                "bbox": bbox,
                "gender": "male" if gender_val == "Man" else "female",
                "emotion": dominant_emotion_val,
                "age_group": age_group,
                "age": age_raw,
                "confidence": round(confidence, 2) if confidence else 0.0,
                "snapshot_url": snapshot_url,
            }
            faces_payload.append(face_dict)

            # Accumulate stats
            if gender_val == "Man":
                stats_male += 1
            else:
                stats_female += 1
            dominant_emotion = dominant_emotion_val

            # Update hourly stats for this face
            try:
                upsert_hourly_stats(
                    camera_id=self.camera_id,
                    gender=gender_val,
                    emotion=dominant_emotion_val,
                    age_group=age_group,
                )
            except Exception:
                logger.exception("[Thread-B] Stats upsert failed for camera %s", self.camera_id)

        if not faces_payload:
            return

        self._persist_and_broadcast(faces_payload, timestamp, stats_male, stats_female, dominant_emotion)

    # ---- frame broadcast (MJPEG only) ----------------------------------

    def _broadcast_frame(self, frame: np.ndarray) -> None:
        """Encode a frame to JPEG and push to MJPEG client queues.

        The WS base64 frame path has been removed — it was encoding every
        frame as base64 (33% CPU overhead) but no frontend component
        consumed it.  Detection events (bounding boxes, stats) still go
        via ``ws_manager.broadcast_stream()`` in ``_persist_and_broadcast``.

        If no MJPEG clients are connected, JPEG encoding is skipped
        entirely (zero CPU cost when nobody is watching).
        """
        with self._mjpeg_queues_lock:
            if not self._mjpeg_queues:
                return  # No viewers — skip encoding entirely

        try:
            ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if not ret:
                return
            jpg_bytes = buf.tobytes()

            # Push raw JPEG bytes to each MJPEG client queue.
            # _safe_put_frame_sync runs on the event loop via call_soon_threadsafe.
            with self._mjpeg_queues_lock:
                for q, loop in self._mjpeg_queues:
                    loop.call_soon_threadsafe(_safe_put_frame_sync, q, jpg_bytes)
        except Exception:
            logger.exception("Frame broadcast failed for camera %s", self.camera_id)

    # ---- snapshot helper ---------------------------------------------

    def _save_snapshot(self, frame: np.ndarray, bbox: dict) -> str:
        """Crop a face from the frame and save it as a snapshot.

        Returns:
            Snapshot URL string (empty string on failure).
        """
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        y1 = max(0, y)
        y2 = min(frame.shape[0], y + h)
        x1 = max(0, x)
        x2 = min(frame.shape[1], x + w)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return ""

        try:
            pil_img = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            return upload_snapshot(buf.getvalue(), self.camera_id)
        except Exception:
            logger.exception("Snapshot save failed for camera %s", self.camera_id)
            return ""

    # ---- shared persist + broadcast ----------------------------------

    def _persist_and_broadcast(
        self,
        faces_payload: list[dict],
        timestamp: str,
        stats_male: int,
        stats_female: int,
        dominant_emotion: Optional[str],
    ) -> None:
        """Persist detection records and broadcast via WebSocket.

        Shared between modern and legacy pipelines.
        """
        if not faces_payload:
            return

        # Persist detection record
        try:
            detection_id = insert_detection(
                camera_id=self.camera_id,
                faces_data=faces_payload,
                timestamp=timestamp,
            )

            # Persist individual snapshot records
            for face in faces_payload:
                if face.get("snapshot_url"):
                    try:
                        insert_snapshot(
                            camera_id=self.camera_id,
                            detection_id=detection_id,
                            url=face["snapshot_url"],
                        )
                    except Exception:
                        logger.exception("Snapshot record insert failed")

        except Exception:
            logger.exception("Detection insert failed for camera %s", self.camera_id)
            return

        # Evaluate alert rules against detected faces
        try:
            alert_engine.evaluate(self.camera_id, faces_payload, self._loop)
        except Exception:
            logger.exception("Alert evaluation failed for camera %s", self.camera_id)

        # Build WebSocket message (same format as before — no frontend breakage)
        ws_message = {
            "type": "detection",
            "camera_id": self.camera_id,
            "timestamp": timestamp,
            "faces": faces_payload,
            "stats_delta": {
                "total": len(faces_payload),
                "male": stats_male,
                "female": stats_female,
                "emotion": dominant_emotion,
            },
        }

        # Schedule broadcast on the asyncio event loop
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_stream(self.camera_id, ws_message),
                self._loop,
            )
        except Exception:
            logger.exception("WS broadcast failed for camera %s", self.camera_id)

        # Schedule SSE broadcasts on the asyncio event loop
        try:
            # Broadcast the main detection event
            asyncio.run_coroutine_threadsafe(
                sse_manager.broadcast(
                    self.camera_id,
                    "detection",
                    {
                        "camera_id": self.camera_id,
                        "faces": faces_payload,
                        "stats_delta": {
                            "total": len(faces_payload),
                            "male": stats_male,
                            "female": stats_female,
                            "emotion": dominant_emotion,
                        },
                    },
                    timestamp,
                ),
                self._loop,
            )

            # Broadcast separate snapshot events for each face that has a snapshot URL
            for face in faces_payload:
                if face.get("snapshot_url"):
                    snap_data = {
                        "id": face["id"],
                        "camera_id": self.camera_id,
                        "detection_id": detection_id,
                        "url": face["snapshot_url"],
                        "gender": face["gender"],
                        "emotion": face["emotion"],
                        "age": face["age"],
                        "age_group": face["age_group"],
                        "timestamp": timestamp,
                    }
                    asyncio.run_coroutine_threadsafe(
                        sse_manager.broadcast(self.camera_id, "snapshot", snap_data, timestamp),
                        self._loop,
                    )
        except Exception:
            logger.exception("SSE broadcasts failed for camera %s", self.camera_id)


# =====================================================================
# Detection engine singleton
# =====================================================================

class DetectionEngine:
    """Manages ``StreamWorker`` instances for all active cameras."""

    def __init__(self) -> None:
        self._workers: dict[str, StreamWorker] = {}

    def start_stream(self, camera_id: str, rtsp_url: str) -> None:
        """Start detection on a camera stream.

        Uses asyncio.get_running_loop() for correct event loop capture.
        Falls back to get_event_loop() for non-async contexts (tests).
        """
        if camera_id in self._workers and self._workers[camera_id].is_alive:
            logger.warning("Stream already running for camera %s", camera_id)
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called from a non-async context (e.g. test harness) — fall back
            loop = asyncio.get_event_loop()

        worker = StreamWorker(camera_id, rtsp_url, loop)
        self._workers[camera_id] = worker
        worker.start()

    def stop_stream(self, camera_id: str) -> None:
        """Stop detection on a camera stream."""
        worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop()

    def get_status(self, camera_id: str) -> str:
        """Return the status of a camera: ``live``, ``processing``, or ``offline``."""
        worker = self._workers.get(camera_id)
        if worker and worker.is_alive:
            return "live"
        return "offline"

    def get_worker(self, camera_id: str) -> Optional[StreamWorker]:
        """Return the active StreamWorker for a camera, if any."""
        return self._workers.get(camera_id)

    def stop_all(self) -> None:
        """Gracefully stop every running stream."""
        for camera_id in list(self._workers.keys()):
            self.stop_stream(camera_id)


# Singleton
detection_engine = DetectionEngine()
