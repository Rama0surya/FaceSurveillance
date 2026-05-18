"""
Detection engine — runs face detection on RTSP/HLS streams.

Each camera gets its own ``StreamWorker`` thread that:
  1. Opens the stream with ``cv2.VideoCapture``
  2. Every *N* seconds runs the detection pipeline on the latest frame
  3. Classifies age, crops faces, saves snapshots
  4. Persists results to Supabase
  5. Broadcasts via WebSocket
  6. Streams frames (base64 JPEG) to WS clients at max FRAME_BROADCAST_FPS

Pipeline modes:
  - **Modern** (default): YOLOv8n-face → ByteTrack → InsightFace age/gender → DeepFace emotion
  - **Legacy** (fallback): DeepFace.analyze() for everything (if ultralytics/insightface unavailable)
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.supabase_client import upload_snapshot
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
# Stream worker (runs in a dedicated thread)
# =====================================================================

class StreamWorker:
    """Background worker that reads frames and runs detection."""

    def __init__(self, camera_id: str, rtsp_url: str, loop: asyncio.AbstractEventLoop) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._loop = loop  # main asyncio event loop (for WS broadcast)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

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
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"stream-{self.camera_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- main loop ---------------------------------------------------

    def _run(self) -> None:
        """Thread entry-point: open stream → read → detect → broadcast."""
        logger.info("Starting stream worker for camera %s (%s)", self.camera_id, self.rtsp_url)
        update_camera_status(self.camera_id, "processing")

        cap: Optional[cv2.VideoCapture] = None
        retry_delay = 2  # seconds between reconnect attempts (with backoff)

        # Frame broadcast throttle
        frame_interval = 1.0 / max(settings.FRAME_BROADCAST_FPS, 1)
        last_frame_broadcast = 0.0

        while not self._stop_event.is_set():
            try:
                cap = cv2.VideoCapture(self.rtsp_url)
                if not cap.isOpened():
                    logger.warning("Cannot open stream %s — retrying in %ds", self.rtsp_url, retry_delay)
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)
                    continue

                # Stream opened successfully
                update_camera_status(self.camera_id, "live")
                retry_delay = 2
                last_detect = 0.0

                while not self._stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning("Lost frame from camera %s", self.camera_id)
                        break  # will reconnect

                    now = time.time()

                    # ---- Frame broadcast (throttled) ----
                    if now - last_frame_broadcast >= frame_interval:
                        last_frame_broadcast = now
                        self._broadcast_frame(frame)

                    # ---- Detection (interval-gated) ----
                    if now - last_detect < settings.DETECTION_INTERVAL_SECONDS:
                        # Skip — not time to detect yet
                        continue

                    last_detect = now
                    self._process_frame(frame)

            except Exception:
                logger.exception("Stream worker error (camera %s)", self.camera_id)
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
            finally:
                if cap is not None:
                    cap.release()

        # Stopped
        update_camera_status(self.camera_id, "offline")
        logger.info("Stream worker stopped for camera %s", self.camera_id)

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

    # ---- detection (modern pipeline) ---------------------------------

    def _process_frame(self, frame: np.ndarray) -> None:
        """Run the detection pipeline on a single frame.

        Dispatches to the modern (YOLO+ByteTrack+InsightFace) or legacy
        (DeepFace) pipeline depending on model_manager state.
        """
        from app.services.model_manager import model_manager

        if model_manager.legacy_mode or self._tracker_model is None:
            self._process_frame_legacy(frame)
            return

        self._process_frame_modern(frame)

    def _process_frame_modern(self, frame: np.ndarray) -> None:
        """Modern pipeline: YOLOv8 detect+track → zone filter → de-dup → analyze."""
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
            logger.exception("YOLO detect/track failed for camera %s", self.camera_id)
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
                    # Already analyzed recently — skip
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

        # ---- Step 4: Analyze each new face ----
        timestamp = datetime.now(timezone.utc).isoformat()
        faces_payload: list[dict] = []
        stats_male = 0
        stats_female = 0
        dominant_emotion = None

        for face_data in new_faces:
            bbox = face_data["bbox"]

            try:
                # InsightFace: age + gender
                ag = model_manager.analyze_age_gender(frame, bbox)

                # DeepFace: emotion only
                emo = model_manager.analyze_emotion(frame, bbox)
            except Exception:
                logger.debug("Analysis failed for a face on camera %s", self.camera_id)
                ag = {"age": 0, "gender": "unknown"}
                emo = {"emotion": "neutral"}

            age_group = classify_age(ag["age"])

            # Crop & save snapshot
            snapshot_url = self._save_snapshot(frame, bbox)

            face_dict = {
                "id": str(uuid.uuid4()),
                "track_id": face_data.get("track_id"),
                "bbox": bbox,
                "gender": ag["gender"],
                "emotion": emo["emotion"],
                "age_group": age_group,
                "age": ag["age"],
                "confidence": round(face_data["confidence"], 2),
                "snapshot_url": snapshot_url,
            }
            faces_payload.append(face_dict)

            # Accumulate stats
            if ag["gender"] == "male":
                stats_male += 1
            else:
                stats_female += 1
            dominant_emotion = emo["emotion"]

            # Update hourly stats
            try:
                gender_val = "Man" if ag["gender"] == "male" else "Woman"
                upsert_hourly_stats(
                    camera_id=self.camera_id,
                    gender=gender_val,
                    emotion=emo["emotion"],
                    age_group=age_group,
                )
            except Exception:
                logger.exception("Stats upsert failed for camera %s", self.camera_id)

        # ---- Step 5: Persist + broadcast ----
        self._persist_and_broadcast(faces_payload, timestamp, stats_male, stats_female, dominant_emotion)

    # ---- detection (legacy pipeline) ---------------------------------

    def _process_frame_legacy(self, frame: np.ndarray) -> None:
        """Legacy pipeline: DeepFace.analyze() for everything (fallback)."""
        try:
            from deepface import DeepFace

            results = DeepFace.analyze(
                img_path=frame,
                actions=["emotion", "age", "gender"],
                enforce_detection=False,
                silent=True,
            )
        except Exception:
            logger.exception("DeepFace.analyze failed for camera %s", self.camera_id)
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
            # (DeepFace returns this when enforce_detection=False and no face found)
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
                logger.exception("Stats upsert failed for camera %s", self.camera_id)

        if not faces_payload:
            return

        self._persist_and_broadcast(faces_payload, timestamp, stats_male, stats_female, dominant_emotion)

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
