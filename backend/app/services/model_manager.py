"""
Centralized AI model loading & GPU detection.

Load models ONCE at startup, share across all StreamWorker threads.
Provides a clean API for detection, tracking, age/gender, and emotion analysis.

Falls back to legacy DeepFace pipeline if ultralytics or insightface
are not installed.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton that manages all AI models for the detection pipeline."""

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.device: str = "cpu"
        self.yolo_model = None          # YOLOv8n-face (shared for detection-only)
        self.insight_app = None         # InsightFace FaceAnalysis
        self._loaded: bool = False
        self.legacy_mode: bool = False  # True → fallback to DeepFace for everything

        # Thread lock for InsightFace inference (not inherently thread-safe)
        self._insight_lock = threading.Lock()

    # -----------------------------------------------------------------
    # Singleton
    # -----------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "ModelManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # -----------------------------------------------------------------
    # GPU / device detection
    # -----------------------------------------------------------------

    def _detect_device(self) -> str:
        """Auto-detect best compute device: 'cuda' if available, else 'cpu'.

        Respects ``settings.USE_GPU`` override ('auto' | 'cuda' | 'cpu').
        """
        forced = getattr(settings, "USE_GPU", "auto")
        if forced == "cpu":
            logger.info("GPU disabled by config (USE_GPU=cpu)")
            return "cpu"

        # 1. Try PyTorch CUDA
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                logger.info("GPU detected via PyTorch: %s", gpu_name)
                if forced == "cuda" or forced == "auto":
                    return "cuda"
        except ImportError:
            pass

        # 2. Try ONNX Runtime CUDA provider
        try:
            import onnxruntime as ort
            if "CUDAExecutionProvider" in ort.get_available_providers():
                logger.info("GPU detected via ONNX Runtime CUDAExecutionProvider")
                if forced == "cuda" or forced == "auto":
                    return "cuda"
        except ImportError:
            pass

        if forced == "cuda":
            logger.warning("USE_GPU=cuda but no CUDA backend found — falling back to cpu")

        logger.info("No GPU detected, using CPU")
        return "cpu"

    # -----------------------------------------------------------------
    # Model loading
    # -----------------------------------------------------------------

    def load_models(self) -> None:
        """Load all models. Call ONCE at application startup."""
        if self._loaded:
            return

        self.device = self._detect_device()
        logger.info("Compute device: %s", self.device)

        # Check if user explicitly wants legacy mode
        detector_cfg = getattr(settings, "FACE_DETECTOR", "yolov8")
        if detector_cfg == "deepface_legacy":
            logger.info("FACE_DETECTOR=deepface_legacy — using legacy DeepFace pipeline")
            self.legacy_mode = True
            self._loaded = True
            return

        # ---- 1. YOLOv8n-face ----
        try:
            from ultralytics import YOLO
            import torch
            import ultralytics.nn.tasks as _ult_tasks
            
            torch.serialization.add_safe_globals([_ult_tasks.DetectionModel])

            model_path = getattr(settings, "YOLO_MODEL_PATH", "yolov8n-face-lindevs.pt")
            self.yolo_model = YOLO(model_path)

            if self.device == "cuda":
                self.yolo_model.to("cuda")

            logger.info("YOLOv8 model loaded from '%s' on %s", model_path, self.device)
        except ImportError:
            logger.warning(
                "ultralytics not installed — falling back to legacy DeepFace pipeline"
            )
            self.legacy_mode = True
            self._loaded = True
            return
        except Exception:
            logger.exception("Failed to load YOLOv8 model — falling back to legacy mode")
            self.legacy_mode = True
            self._loaded = True
            return

        # ---- 2. InsightFace ----
        try:
            from insightface.app import FaceAnalysis

            insight_model = getattr(settings, "INSIGHT_MODEL", "buffalo_l")
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if self.device == "cuda"
                else ["CPUExecutionProvider"]
            )

            self.insight_app = FaceAnalysis(
                name=insight_model,
                root="~/.insightface",
                providers=providers,
            )
            ctx_id = 0 if self.device == "cuda" else -1
            self.insight_app.prepare(ctx_id=ctx_id, det_size=(640, 640))

            logger.info("InsightFace '%s' loaded on %s", insight_model, self.device)
        except ImportError:
            logger.warning(
                "insightface not installed — age/gender will fall back to DeepFace"
            )
            self.insight_app = None
        except Exception:
            logger.exception("Failed to load InsightFace — age/gender will fall back to DeepFace")
            self.insight_app = None

        self._loaded = True
        logger.info(
            "Model loading complete (legacy_mode=%s, device=%s)",
            self.legacy_mode,
            self.device,
        )

    # -----------------------------------------------------------------
    # Per-camera tracker factory
    # -----------------------------------------------------------------

    def create_tracker(self):
        """Create a NEW YOLO model instance for per-camera tracking.

        Each StreamWorker needs its own model instance so that
        ByteTrack/BoTSORT maintains separate tracking state per camera.

        Returns None if legacy mode is active.
        """
        if self.legacy_mode or self.yolo_model is None:
            return None

        try:
            from ultralytics import YOLO
            import torch
            import ultralytics.nn.tasks as _ult_tasks

            # Fix PyTorch 2.6 breaking change
            torch.serialization.add_safe_globals([_ult_tasks.DetectionModel])

            model_path = getattr(settings, "YOLO_MODEL_PATH", "yolov8n-face-lindevs.pt")
            tracker = YOLO(model_path)

            if self.device == "cuda":
                tracker.to("cuda")

            logger.info("Created new YOLO tracker instance on %s", self.device)
            return tracker
        except Exception:
            logger.exception("Failed to create YOLO tracker instance")
            return None

    # -----------------------------------------------------------------
    # Detection (shared model — no tracking state)
    # -----------------------------------------------------------------

    def detect_faces_yolo(self, frame: np.ndarray, conf: float = 0.5) -> list[dict]:
        """Detect faces using shared YOLOv8 model (no tracking).

        Returns:
            List of dicts: [{"bbox": {"x","y","w","h"}, "confidence": float}]
        """
        if self.yolo_model is None:
            return []

        if conf is None:
            conf = getattr(settings, "YOLO_CONFIDENCE", 0.5)

        results = self.yolo_model(frame, conf=conf, verbose=False)
        faces = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                faces.append({
                    "bbox": {
                        "x": int(x1),
                        "y": int(y1),
                        "w": int(x2 - x1),
                        "h": int(y2 - y1),
                    },
                    "confidence": float(box.conf[0]),
                })
        return faces

    # -----------------------------------------------------------------
    # Detection + Tracking (per-camera model instance)
    # -----------------------------------------------------------------

    @staticmethod
    def detect_and_track(
        tracker_model,
        frame: np.ndarray,
        tracker: str = "bytetrack.yaml",
        conf: float = 0.5,
        persist: bool = True,
    ) -> list[dict]:
        """Detect + track faces using a per-camera YOLO instance.

        Args:
            tracker_model: YOLO model instance (from create_tracker())
            frame: BGR numpy array
            tracker: tracker config file name
            conf: confidence threshold
            persist: persist tracking state across frames

        Returns:
            List of dicts: [{"bbox": {…}, "confidence": float, "track_id": int}]
        """
        if tracker_model is None:
            return []

        results = tracker_model.track(
            frame,
            tracker=tracker,
            conf=conf,
            persist=persist,
            verbose=False,
        )

        faces = []
        for r in results:
            if r.boxes.id is None:
                continue
            for box, track_id in zip(r.boxes, r.boxes.id):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                faces.append({
                    "bbox": {
                        "x": int(x1),
                        "y": int(y1),
                        "w": int(x2 - x1),
                        "h": int(y2 - y1),
                    },
                    "confidence": float(box.conf[0]),
                    "track_id": int(track_id),
                })
        return faces

    # -----------------------------------------------------------------
    # Age / Gender — InsightFace
    # -----------------------------------------------------------------

    def analyze_age_gender(self, frame: np.ndarray, bbox: dict) -> dict:
        """Analyze age and gender for a face crop using InsightFace.

        Falls back to DeepFace if InsightFace is unavailable.

        Returns:
            {"age": int, "gender": str ("male"/"female"/"unknown")}
        """
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]

        # Expand crop slightly for better context
        pad = int(max(w, h) * 0.15)
        y1 = max(0, y - pad)
        y2 = min(frame.shape[0], y + h + pad)
        x1 = max(0, x - pad)
        x2 = min(frame.shape[1], x + w + pad)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return {"age": 0, "gender": "unknown"}

        # Primary: InsightFace
        if self.insight_app is not None:
            try:
                with self._insight_lock:
                    faces = self.insight_app.get(crop)
                if faces:
                    face = faces[0]
                    return {
                        "age": int(face.age),
                        "gender": "male" if face.gender == 1 else "female",
                    }
            except Exception:
                logger.debug("InsightFace age/gender failed, trying DeepFace fallback")

        # Fallback: DeepFace
        try:
            from deepface import DeepFace

            result = DeepFace.analyze(
                img_path=crop,
                actions=["age", "gender"],
                enforce_detection=False,
                silent=True,
                detector_backend=getattr(settings, "FACE_DETECTOR", "opencv"),
                model_name=getattr(settings, "DEEPFACE_MODEL", "VGG-Face"),
            )
            if isinstance(result, list):
                result = result[0]
            age = int(result.get("age", 0))
            gender_raw = result.get("dominant_gender", "Man")
            gender = "male" if gender_raw == "Man" else "female"
            return {"age": age, "gender": gender}
        except Exception:
            logger.debug("DeepFace age/gender fallback also failed")
            return {"age": 0, "gender": "unknown"}

    # -----------------------------------------------------------------
    # Emotion — DeepFace (lightweight, emotion-only)
    # -----------------------------------------------------------------

    def analyze_emotion(self, frame: np.ndarray, bbox: dict) -> dict:
        """Analyze emotion for a face crop using DeepFace (emotion only).

        Returns:
            {"emotion": str}
        """
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        y1, y2 = max(0, y), min(frame.shape[0], y + h)
        x1, x2 = max(0, x), min(frame.shape[1], x + w)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return {"emotion": "neutral"}

        try:
            from deepface import DeepFace

            result = DeepFace.analyze(
                img_path=crop,
                actions=["emotion"],
                enforce_detection=False,
                silent=True,
                detector_backend=getattr(settings, "FACE_DETECTOR", "opencv"),
            )
            if isinstance(result, list):
                result = result[0]
            return {"emotion": result.get("dominant_emotion", "neutral")}
        except Exception:
            logger.debug("DeepFace emotion analysis failed")
            return {"emotion": "neutral"}

    # -----------------------------------------------------------------
    # Legacy full analysis (DeepFace for everything)
    # -----------------------------------------------------------------

    def analyze_legacy(self, frame: np.ndarray) -> list[dict]:
        """Run the original DeepFace.analyze() for all tasks.

        Used when legacy_mode is True (ultralytics/insightface unavailable).

        Returns:
            Raw DeepFace results list.
        """
        try:
            from deepface import DeepFace

            results = DeepFace.analyze(
                img_path=frame,
                actions=["emotion", "age", "gender"],
                enforce_detection=False,
                silent=True,
                detector_backend=getattr(settings, "FACE_DETECTOR", "opencv"),
                model_name=getattr(settings, "DEEPFACE_MODEL", "VGG-Face"),
            )
            if isinstance(results, dict):
                results = [results]
            return results
        except Exception:
            logger.exception("DeepFace legacy analyze failed")
            return []


# Singleton instance
model_manager = ModelManager.get_instance()
