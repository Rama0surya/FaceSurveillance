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
from app.services.pipeline_state import runtime_config

logger = logging.getLogger(__name__)


def load_yolo_model_safe(model_path: str):
    """Load a YOLOv8 model safely on PyTorch 2.6+.

    Strategy:
      1. Try with add_safe_globals() allowlist (preferred — keeps security).
      2. If that still fails, fall back to weights_only=False via monkey-patch.
         Both paths log clearly so you know which path was taken.

    Args:
        model_path: Path to the .pt weights file.

    Returns:
        YOLO model instance.

    Raises:
        Exception: re-raises if both strategies fail.
    """
    import torch
    from ultralytics import YOLO

    # ------------------------------------------------------------------ #
    # Strategy 1: allowlist known-safe globals from the checkpoint        #
    # ------------------------------------------------------------------ #
    # These are standard PyTorch / Ultralytics module classes that appear
    # in every YOLOv8 checkpoint.  They contain no executable code beyond
    # __init__ and forward(), so whitelisting them is safe.
    SAFE_GLOBALS = [
        "torch.nn.modules.container.Sequential",
        "torch.nn.modules.container.ModuleList",
        "torch.nn.modules.container.ModuleDict",
        "torch.nn.modules.activation.SiLU",
        "torch.nn.modules.activation.ReLU",
        "torch.nn.modules.batchnorm.BatchNorm2d",
        "torch.nn.modules.conv.Conv2d",
        "torch.nn.modules.pooling.MaxPool2d",
        "torch.nn.modules.upsampling.Upsample",
        "torch.nn.modules.linear.Linear",
    ]

    try:
        # Build list of actual class objects for add_safe_globals
        safe_classes = []
        for dotted_path in SAFE_GLOBALS:
            module_path, class_name = dotted_path.rsplit(".", 1)
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                safe_classes.append(cls)
            except (ImportError, AttributeError):
                pass  # class not present in this torch version — skip

        if safe_classes and hasattr(torch.serialization, "add_safe_globals"):
            torch.serialization.add_safe_globals(safe_classes)
            logger.info(
                "YOLOv8 load: allowlisted %d torch globals via add_safe_globals",
                len(safe_classes),
            )

        model = YOLO(model_path)
        logger.info("YOLOv8 model loaded successfully (weights_only=True path)")
        return model

    except Exception as e1:
        logger.warning(
            "YOLOv8 load with add_safe_globals failed (%s) — trying weights_only=False fallback",
            e1,
        )

    # ------------------------------------------------------------------ #
    # Strategy 2: monkey-patch torch.load with weights_only=False        #
    # ------------------------------------------------------------------ #
    # Safe ONLY if you trust the source of the .pt file (official
    # Ultralytics release).  Arbitrary .pt files from unknown sources
    # can execute code when loaded with weights_only=False.
    original_torch_load = torch.load

    def patched_load(f, map_location=None, **kwargs):
        # Force weights_only=False regardless of caller
        kwargs.pop("weights_only", None)
        return original_torch_load(f, map_location=map_location, weights_only=False, **kwargs)

    torch.load = patched_load
    try:
        model = YOLO(model_path)
        logger.info(
            "YOLOv8 model loaded via weights_only=False fallback. "
            "Ensure the .pt file is from a trusted source."
        )
        return model
    finally:
        # Always restore original torch.load — don't leave the patch active
        torch.load = original_torch_load


class ModelManager:
    """Singleton that manages all AI models for the detection pipeline."""

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    class GPUNotAvailableError(RuntimeError):
        """Raised when GPU is required (USE_GPU=cuda) but not available."""
        pass

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
        """Detect compute device with STRICT MODE enforcement.

        When USE_GPU=cuda (strict mode):
          - CUDA must be available via PyTorch
          - CUDA must be functional (can allocate tensors)
          - ONNX Runtime CUDAExecutionProvider must be present
          - If ANY check fails → raise GPUNotAvailableError (HARD FAIL)

        When USE_GPU=auto:
          - Try CUDA, fallback to CPU (safe for development)

        When USE_GPU=cpu:
          - Force CPU (for testing/debugging only)
        """
        forced = getattr(settings, "USE_GPU", "auto")

        if forced == "cpu":
            logger.info("GPU disabled by config (USE_GPU=cpu)")
            return "cpu"

        # ---- Check PyTorch CUDA ----
        cuda_available = False
        cuda_functional = False
        gpu_name = "unknown"

        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                # Functional test: actually allocate a tensor on GPU
                test_tensor = torch.zeros(1, device="cuda")
                del test_tensor
                torch.cuda.empty_cache()
                cuda_functional = True
                logger.info("GPU functional test PASSED: %s", gpu_name)
        except ImportError:
            logger.error("PyTorch not installed — cannot use GPU")
        except Exception as e:
            logger.error("GPU functional test FAILED: %s", e)

        # ---- Check ONNX Runtime CUDA (for InsightFace) ----
        onnx_cuda = False
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            onnx_cuda = "CUDAExecutionProvider" in providers
            if onnx_cuda:
                logger.info("ONNX Runtime CUDAExecutionProvider: AVAILABLE")
            else:
                logger.warning(
                    "ONNX Runtime CUDAExecutionProvider: NOT AVAILABLE (providers=%s)",
                    providers,
                )
        except ImportError:
            logger.warning("onnxruntime not installed")

        # ---- STRICT MODE: USE_GPU=cuda ----
        if forced == "cuda":
            errors = []
            if not cuda_available:
                errors.append("torch.cuda.is_available() returned False")
            if not cuda_functional:
                errors.append("GPU functional test failed (cannot allocate tensor)")
            if not onnx_cuda:
                errors.append(
                    "ONNX Runtime CUDAExecutionProvider not available "
                    "(InsightFace will silently use CPU)"
                )

            if errors:
                msg = (
                    "\n\n"
                    "========================================================\n"
                    "   GPU STRICT MODE — STARTUP BLOCKED                    \n"
                    "========================================================\n"
                    "USE_GPU=cuda but GPU is NOT fully functional.\n"
                    "Refusing to start with silent CPU fallback.\n"
                    "--------------------------------------------------------\n"
                    + "\n".join(f"  X {e}" for e in errors)
                    + "\n--------------------------------------------------------\n"
                    "FIX: Install CUDA toolkit, cuDNN, torch+cu*, and\n"
                    "     onnxruntime-gpu. Or set USE_GPU=auto for fallback.\n"
                    "========================================================\n"
                )
                logger.critical(msg)
                raise self.GPUNotAvailableError(msg)

            logger.info("GPU STRICT MODE: All checks passed (%s)", gpu_name)
            return "cuda"

        # ---- AUTO MODE: USE_GPU=auto ----
        if cuda_functional:
            logger.info("Auto-detected GPU: %s", gpu_name)
            return "cuda"

        logger.info("No functional GPU detected, using CPU (USE_GPU=auto)")
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
            self.yolo_model = load_yolo_model_safe(model_path)

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
            if self.device == "cuda":
                # In strict mode, only use CUDA — no CPU fallback that
                # silently degrades performance
                providers = ["CUDAExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]

            self.insight_app = FaceAnalysis(
                name=insight_model,
                root="~/.insightface",
                providers=providers,
            )
            ctx_id = 0 if self.device == "cuda" else -1
            self.insight_app.prepare(ctx_id=ctx_id, det_size=(640, 640))

            logger.info("InsightFace '%s' loaded on %s", insight_model, self.device)
        except ImportError:
            if getattr(settings, "USE_GPU", "auto") == "cuda":
                logger.error("insightface not installed — required in GPU strict mode")
            else:
                logger.warning(
                    "insightface not installed — age/gender will fall back to DeepFace"
                )
            self.insight_app = None
        except Exception as e:
            if getattr(settings, "USE_GPU", "auto") == "cuda":
                raise self.GPUNotAvailableError(
                    f"InsightFace failed to load on CUDA: {e}"
                ) from e
            logger.exception("Failed to load InsightFace — age/gender will fall back to DeepFace")
            self.insight_app = None

        # ---- Post-load GPU validation ----
        self._validate_gpu_placement()

        self._loaded = True
        logger.info(
            "Model loading complete (legacy_mode=%s, device=%s)",
            self.legacy_mode,
            self.device,
        )

    # -----------------------------------------------------------------
    # Post-load GPU validation
    # -----------------------------------------------------------------

    def _validate_gpu_placement(self) -> None:
        """Verify all models are actually running on the expected device.

        Checks:
          1. YOLO model parameters are on CUDA
          2. InsightFace session uses CUDAExecutionProvider
          3. DeepFace backend (TF/PyTorch) can see GPU

        In strict mode (USE_GPU=cuda), any failure raises GPUNotAvailableError.
        In auto mode, failures are logged as warnings.
        """
        if self.device != "cuda":
            return  # Nothing to validate in CPU mode

        errors = []
        strict = getattr(settings, "USE_GPU", "auto") == "cuda"

        # ---- 1. Verify YOLO is on CUDA ----
        if self.yolo_model is not None:
            try:
                import torch
                param = next(self.yolo_model.model.parameters())
                if not param.is_cuda:
                    errors.append(
                        f"YOLO model is on {param.device}, expected cuda"
                    )
                else:
                    logger.info("GPU validation: YOLO model verified on CUDA")
            except Exception as e:
                errors.append(f"YOLO device check failed: {e}")

        # ---- 2. Verify InsightFace uses CUDA provider ----
        if self.insight_app is not None:
            try:
                for model in self.insight_app.models:
                    session = getattr(model, "session", None)
                    if session is not None:
                        providers = session.get_providers()
                        if "CUDAExecutionProvider" not in providers:
                            errors.append(
                                f"InsightFace model '{type(model).__name__}' "
                                f"using {providers} instead of CUDAExecutionProvider"
                            )
                        else:
                            logger.info(
                                "GPU validation: InsightFace '%s' verified on CUDAExecutionProvider",
                                type(model).__name__,
                            )
            except Exception as e:
                errors.append(f"InsightFace provider check failed: {e}")

        # ---- 3. Log DeepFace GPU status ----
        try:
            import tensorflow as tf
            gpus = tf.config.list_physical_devices('GPU')
            if gpus:
                logger.info("GPU validation: TensorFlow sees %d GPU(s): %s", len(gpus), gpus)
            else:
                errors.append("TensorFlow sees 0 GPUs — DeepFace will use CPU")
        except ImportError:
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("GPU validation: DeepFace (PyTorch backend) can use CUDA")
                else:
                    errors.append("DeepFace PyTorch backend: CUDA not available")
            except ImportError:
                errors.append("Neither TF nor PyTorch available for DeepFace")

        if errors:
            report = "\n".join(f"  X {e}" for e in errors)
            if strict:
                raise self.GPUNotAvailableError(
                    f"GPU STRICT MODE — post-load validation FAILED:\n{report}"
                )
            else:
                logger.warning(
                    "GPU validation warnings (non-fatal in auto mode):\n%s",
                    report,
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
            tracker = load_yolo_model_safe(model_path)

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
                detector_backend=runtime_config.face_detector or "opencv",
                model_name=runtime_config.deepface_model or "VGG-Face",
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
                detector_backend=runtime_config.face_detector or "opencv",
            )
            if isinstance(result, list):
                result = result[0]
            return {"emotion": result.get("dominant_emotion", "neutral")}
        except Exception:
            logger.debug("DeepFace emotion analysis failed")
            return {"emotion": "neutral"}

    # -----------------------------------------------------------------
    # Crop-based analysis (used by multi-thread pipeline Thread C)
    # -----------------------------------------------------------------

    def analyze_age_gender_from_crop(self, crop: np.ndarray) -> dict:
        """Analyze age and gender from a pre-cropped face image.

        Same logic as ``analyze_age_gender`` but skips bbox → crop
        computation (the caller already provides the crop).

        Returns:
            {"age": int, "gender": str ("male"/"female"/"unknown")}
        """
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
                detector_backend=runtime_config.face_detector or "opencv",
                model_name=runtime_config.deepface_model or "VGG-Face",
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

    def analyze_emotion_from_crop(self, crop: np.ndarray) -> dict:
        """Analyze emotion from a pre-cropped face image.

        Same logic as ``analyze_emotion`` but skips bbox → crop
        computation (the caller already provides the crop).

        Returns:
            {"emotion": str}
        """
        if crop.size == 0:
            return {"emotion": "neutral"}

        try:
            from deepface import DeepFace

            result = DeepFace.analyze(
                img_path=crop,
                actions=["emotion"],
                enforce_detection=False,
                silent=True,
                detector_backend=runtime_config.face_detector or "opencv",
            )
            if isinstance(result, list):
                result = result[0]
            return {"emotion": result.get("dominant_emotion", "neutral")}
        except Exception:
            logger.debug("DeepFace emotion analysis (from crop) failed")
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
                detector_backend=runtime_config.face_detector or "opencv",
                model_name=runtime_config.deepface_model or "VGG-Face",
            )
            if isinstance(results, dict):
                results = [results]
            return results
        except Exception:
            logger.exception("DeepFace legacy analyze failed")
            return []


# Singleton instance
model_manager = ModelManager.get_instance()
