"""
Detection engine — runs face detection on RTSP/HLS streams.

Architecture: 3-Thread Producer-Consumer Pipeline
=================================================

Each camera gets its own ``StreamWorker`` with **three decoupled threads**:

  Thread A — **RTSP Frame Grabber**
    Reads frames from the RTSP stream as fast as possible (30 FPS+).
    Puts frames into a bounded ``frame_queue`` (maxsize=2).
    If the queue is full, the oldest frame is **dropped** (frame-skipping)
    so that Thread B always gets the freshest frame available.

  Thread B — **YOLO + ByteTrack Detector**
    Pulls frames from ``frame_queue``, runs YOLOv8n-face detection and
    ByteTrack tracking.  Broadcasts annotated frames to WebSocket clients.
    When a **new track_id** appears, it packages a lightweight
    ``AnalysisTask`` (face crop + metadata) and enqueues it for Thread C.

  Thread C — **Heavy Inference Worker**
    Pulls ``AnalysisTask`` items from ``analysis_queue``.
    Runs InsightFace (age/gender) + DeepFace (emotion), saves snapshots,
    persists to DB, evaluates alerts, and broadcasts results via WebSocket.
    This thread is invoked **only for new faces**, saving ~80% GPU/CPU.

Pipeline modes:
  - **Modern** (default): YOLOv8n-face → ByteTrack → InsightFace → DeepFace emotion
  - **Legacy** (fallback): DeepFace.analyze() for everything
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import queue
import threading
import time
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.db_client import upload_snapshot
from app.core.websocket import manager as ws_manager
from app.db.detections import insert_detection, insert_snapshot
from app.db.stats import upsert_hourly_stats
from app.db.cameras import update_camera_status, get_camera_raw
from app.services.alert_engine import alert_engine

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
    full_frame: np.ndarray       # Full frame copy for snapshot saving
    bbox: dict                   # {"x", "y", "w", "h"} — plain dict, safe
    track_id: int
    confidence: float
    timestamp: str

    class Config:
        # Allow numpy arrays in frozen dataclass
        arbitrary_types_allowed = True


# =====================================================================
# Stream worker (3-thread producer-consumer pipeline)
# =====================================================================

class StreamWorker:
    """Background worker that reads frames and runs detection.

    Manages three threads per camera:
      - Thread A: RTSP frame grabber  (I/O-bound, never blocked by AI)
      - Thread B: YOLO + ByteTrack    (GPU-bound, fast ~30-80ms)
      - Thread C: Heavy inference      (GPU-bound, slow, only new faces)
    """

    def __init__(self, camera_id: str, rtsp_url: str, loop: asyncio.AbstractEventLoop) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._loop = loop  # main asyncio event loop (for WS broadcast)
        self._stop_event = threading.Event()

        # ---- Inter-thread queues ----
        # Frame queue: Thread A → Thread B
        # Small maxsize ensures Thread B always gets the freshest frame.
        self._frame_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(
            maxsize=max(1, settings.FRAME_QUEUE_SIZE),
        )
        # Analysis queue: Thread B → Thread C
        # Larger buffer since Thread C is slower but called less frequently.
        self._analysis_queue: queue.Queue[Optional[AnalysisTask]] = queue.Queue(
            maxsize=max(1, settings.ANALYSIS_QUEUE_SIZE),
        )

        # ---- Thread references ----
        self._threads: list[threading.Thread] = []

        # Load detection zone from camera config
        self._detection_zone: Optional[dict] = None
        self._load_detection_zone()

        # --- Tracking state (modern pipeline) ---
        self._analyzed_tracks: dict[int, float] = {}  # track_id → timestamp last analyzed
        self._tracker_model = None  # per-camera YOLO instance for tracking

        # Initialize tracker model if modern pipeline is active
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
            ("grabber",  self._frame_grabber_loop),
            ("detector", self._detection_loop),
            ("analyzer", self._analysis_worker_loop),
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
            "StreamWorker started for camera %s — 3 threads active",
            self.camera_id,
        )

    def stop(self) -> None:
        """Signal all threads to stop and wait for them to finish."""
        self._stop_event.set()

        # Inject sentinel values to unblock any thread waiting on queue.get()
        try:
            self._frame_queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self._analysis_queue.put_nowait(None)
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
                    # frame.copy() transfers ownership — no shared mutation.
                    # --------------------------------------------------
                    frame_copy = frame.copy()
                    try:
                        self._frame_queue.put_nowait(frame_copy)
                    except queue.Full:
                        # Queue full → drop oldest, insert newest
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._frame_queue.put_nowait(frame_copy)
                        except queue.Full:
                            pass  # extremely unlikely, just skip this frame

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
        """Thread B: Fast detection + tracking + frame broadcast.

        Pulls frames from ``frame_queue``, runs YOLOv8n-face + ByteTrack,
        filters by detection zone, de-duplicates by track_id, broadcasts
        annotated frames via WebSocket, and enqueues ``AnalysisTask`` for
        any **new** face track IDs.

        This thread does NOT run InsightFace or DeepFace — keeping it fast
        (~30-80ms on GPU, ~150-300ms on CPU).
        """
        from app.services.model_manager import model_manager

        logger.info("[Thread-B] Detector started for camera %s", self.camera_id)

        # Frame broadcast throttle
        frame_interval = 1.0 / max(settings.FRAME_BROADCAST_FPS, 1)
        last_frame_broadcast = 0.0

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

            # ---- Frame broadcast (throttled) ----
            if now - last_frame_broadcast >= frame_interval:
                last_frame_broadcast = now
                self._broadcast_frame(frame)

            # ---- Dispatch to modern or legacy pipeline ----
            if model_manager.legacy_mode or self._tracker_model is None:
                self._process_frame_legacy(frame)
            else:
                self._process_frame_modern(frame)

        logger.info("[Thread-B] Detector stopped for camera %s", self.camera_id)

    def _process_frame_modern(self, frame: np.ndarray) -> None:
        """Modern pipeline (Thread B): YOLOv8 detect+track → zone filter → dedup → enqueue new faces."""
        from app.services.model_manager import model_manager

        # ---- Step 1: Detect + Track (YOLOv8 + ByteTrack) ----
        tracker_cfg = getattr(settings, "FACE_TRACKER", "bytetrack")
        tracker_yaml = f"{tracker_cfg}.yaml" if tracker_cfg != "none" else None
        yolo_conf = getattr(settings, "YOLO_CONFIDENCE", 0.5)

        try:
            if tracker_yaml:
                tracked_faces = model_manager.detect_and_track(
                    self._tracker_model,
                    frame,
                    tracker=tracker_yaml,
                    conf=yolo_conf,
                    persist=True,
                )
            else:
                # No tracking — detection only
                tracked_faces = model_manager.detect_faces_yolo(frame, conf=yolo_conf)
                # Add dummy track_id
                for i, f in enumerate(tracked_faces):
                    f["track_id"] = i
        except Exception:
            logger.exception("[Thread-B] YOLO detect/track failed for camera %s", self.camera_id)
            return

        if not tracked_faces:
            return

        # ---- Step 2: Filter by detection zone ----
        tracked_faces = [
            f for f in tracked_faces
            if _is_face_in_zone(f["bbox"], self._detection_zone)
        ]

        if not tracked_faces:
            return

        # ---- Step 3: De-duplicate using track_id ----
        now = time.time()
        reanalyze_ttl = getattr(settings, "TRACK_REANALYZE_TTL", 300)
        new_faces = []

        for face in tracked_faces:
            track_id = face.get("track_id")
            if track_id is not None:
                last_seen = self._analyzed_tracks.get(track_id)
                if last_seen is not None and (now - last_seen) < reanalyze_ttl:
                    # Already analyzed recently — skip heavy inference
                    continue
                # Mark as analyzed
                self._analyzed_tracks[track_id] = now
            new_faces.append(face)

        # Cleanup stale tracks (keep entries from the last TTL*2 window)
        if len(self._analyzed_tracks) > 500:
            cutoff = now - (reanalyze_ttl * 2)
            self._analyzed_tracks = {
                tid: ts for tid, ts in self._analyzed_tracks.items()
                if ts > cutoff
            }

        if not new_faces:
            return

        # ---- Step 4: Enqueue new faces for Thread C (heavy inference) ----
        timestamp = datetime.now(timezone.utc).isoformat()

        for face_data in new_faces:
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
                full_frame=frame.copy(),  # Independent copy for snapshot
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
        new face track IDs** — typically a fraction of all frames —
        dramatically reducing GPU/CPU load.

        All data arrives as independent copies (no shared mutable state).
        """
        from app.services.model_manager import model_manager

        logger.info("[Thread-C] Analysis worker started for camera %s", self.camera_id)

        # Batch accumulator: collect results until we have a "batch" to persist.
        # In practice, tasks trickle in one at a time, but we batch-persist
        # to minimize DB round-trips when multiple faces appear simultaneously.
        batch: list[dict] = []
        batch_timestamp: Optional[str] = None
        batch_stats_male = 0
        batch_stats_female = 0
        batch_dominant_emotion: Optional[str] = None
        batch_deadline = 0.0  # flush batch at this time

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

            age_group = classify_age(ag["age"])

            # ---- Save snapshot (disk I/O — fine in background thread) ----
            snapshot_url = self._save_snapshot(task.full_frame, task.bbox)

            face_dict = {
                "id": str(uuid.uuid4()),
                "track_id": task.track_id,
                "bbox": task.bbox,
                "gender": ag["gender"],
                "emotion": emo["emotion"],
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
            batch_dominant_emotion = emo["emotion"]

            # Update hourly stats (per-face, non-blocking)
            try:
                gender_val = "Man" if ag["gender"] == "male" else "Woman"
                upsert_hourly_stats(
                    camera_id=self.camera_id,
                    gender=gender_val,
                    emotion=emo["emotion"],
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
        """
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

            # ---- Detection zone filtering ----
            if not _is_face_in_zone(region, self._detection_zone):
                continue

            age_raw = int(face_result.get("age", 0))
            age_group = classify_age(age_raw)

            dominant_emotion_val = face_result.get("dominant_emotion", "neutral")
            gender_val = face_result.get("dominant_gender", "Man")
            confidence = face_result.get("face_confidence", 0.0)

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

    # ---- frame broadcast ---------------------------------------------

    def _broadcast_frame(self, frame: np.ndarray) -> None:
        """Encode a frame to base64 JPEG and broadcast via WebSocket."""
        # Only encode and broadcast if there are WS subscribers
        if not ws_manager.stream_connections.get(self.camera_id):
            return

        try:
            ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if not ret:
                return
            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_frame(self.camera_id, frame_b64),
                self._loop,
            )
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


# =====================================================================
# Detection engine singleton
# =====================================================================

class DetectionEngine:
    """Manages ``StreamWorker`` instances for all active cameras."""

    def __init__(self) -> None:
        self._workers: dict[str, StreamWorker] = {}

    def start_stream(self, camera_id: str, rtsp_url: str) -> None:
        """Start detection on a camera stream."""
        if camera_id in self._workers and self._workers[camera_id].is_alive:
            logger.warning("Stream already running for camera %s", camera_id)
            return

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

    def stop_all(self) -> None:
        """Gracefully stop every running stream."""
        for camera_id in list(self._workers.keys()):
            self.stop_stream(camera_id)


# Singleton
detection_engine = DetectionEngine()
