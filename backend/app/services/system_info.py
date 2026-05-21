"""
System information service — detects hardware, software environment,
and provides acceleration recommendations.

Includes a background cache that polls hardware info every 60 seconds
so API responses are instant (~0ms) instead of blocking (~600ms+).
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

import psutil

logger = logging.getLogger(__name__)

# Track app start time for uptime calculation
_start_time = time.time()


# =====================================================================
# Background Cache — thread-safe, auto-refreshing
# =====================================================================

class _SystemInfoCache:
    """Thread-safe in-memory cache with background polling.

    Heavy operations (GPU detection, nvidia-smi, torch import) run in a
    background thread every ``interval`` seconds.  API handlers only read
    from the cache dict — never call heavy functions directly.
    """

    def __init__(self, interval: int = 60) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task] = None

        # Cached payloads — split into lightweight vs heavyweight
        self._cpu_memory: dict[str, Any] = {}
        self._gpu: dict[str, Any] = {}
        self._disk: dict[str, Any] = {}
        self._acceleration: dict[str, Any] = {}
        self._last_updated: float = 0.0

    # ---- Public read API (called from route handlers) ----

    def get_full_info(self) -> dict:
        """Return the full cached payload.  Instant, no I/O."""
        with self._lock:
            return {
                "cpu": dict(self._cpu_memory.get("cpu", {})),
                "memory": dict(self._cpu_memory.get("memory", {})),
                "gpu": dict(self._gpu),
                "disk": dict(self._disk),
                "python": SystemInfo.get_python_info(),
                "models": SystemInfo.get_model_info(),
                "acceleration": dict(self._acceleration),
                "cache_age_seconds": round(time.time() - self._last_updated, 1) if self._last_updated else None,
            }

    def get_cpu_memory(self) -> dict:
        with self._lock:
            return dict(self._cpu_memory)

    def get_gpu(self) -> dict:
        with self._lock:
            return dict(self._gpu)

    def get_hardware(self) -> dict:
        with self._lock:
            return {
                "gpu": dict(self._gpu),
                "cpu": dict(self._cpu_memory.get("cpu", {})),
            }

    # ---- Lifecycle ----

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Perform an initial synchronous refresh, then schedule the
        background polling task on the given event loop."""
        logger.info("SystemInfoCache: initial refresh …")
        self._refresh()
        logger.info("SystemInfoCache: initial refresh done (%.0fms)", (time.time() - self._last_updated) * 1000)

        if loop is not None:
            self._task = loop.create_task(self._poll_loop())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("SystemInfoCache: background polling stopped")

    # ---- Background polling ----

    async def _poll_loop(self) -> None:
        """Async loop that offloads the heavy refresh to a thread."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._refresh)
                logger.debug("SystemInfoCache: refreshed (interval=%ds)", self._interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("SystemInfoCache: refresh failed, will retry")

    def _refresh(self) -> None:
        """Collect all hardware data (runs in background thread)."""
        # Lightweight — CPU & memory (~50ms due to cpu_percent interval)
        cpu_mem = {
            "cpu": SystemInfo.get_cpu_info(),
            "memory": SystemInfo.get_memory_info(),
        }

        # Heavyweight — GPU detection (~500ms+ due to nvidia-smi / torch)
        gpu = SystemInfo.get_gpu_info()

        # Lightweight
        disk = SystemInfo.get_disk_info()

        # Acceleration recommendation (depends on GPU result)
        accel = SystemInfo._get_acceleration_recommendation_from(gpu)

        # Atomic swap under lock
        with self._lock:
            self._cpu_memory = cpu_mem
            self._gpu = gpu
            self._disk = disk
            self._acceleration = accel
            self._last_updated = time.time()


# Singleton instance — imported by routes and lifespan
system_info_cache = _SystemInfoCache(interval=60)


# =====================================================================
# Raw collection functions (unchanged logic, used by cache refresh)
# =====================================================================

class SystemInfo:
    """Detect hardware and software environment."""

    @staticmethod
    def get_cpu_info() -> dict:
        """Return CPU info."""
        return {
            "name": platform.processor() or "Unknown",
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "usage_percent": psutil.cpu_percent(interval=0.5),
            "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        }

    @staticmethod
    def get_memory_info() -> dict:
        """Return memory info."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        }

    @staticmethod
    def get_gpu_info() -> dict:
        """Detect GPU and CUDA availability."""
        result = {
            "available": False,
            "name": "No GPU detected",
            "cuda_available": False,
            "cuda_version": None,
            "cudnn_version": None,
            "vram_total_gb": None,
            "vram_used_gb": None,
            "driver_version": None,
            "onnx_gpu_available": False,
            "onnx_providers": [],
            "torch_cuda": False,
        }

        # Method 1: nvidia-smi
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                timeout=5,
                text=True,
            )
            parts = output.strip().split(", ")
            if len(parts) >= 4:
                result["available"] = True
                result["name"] = parts[0]
                result["vram_total_gb"] = round(float(parts[1]) / 1024, 2)
                result["vram_used_gb"] = round(float(parts[2]) / 1024, 2)
                result["driver_version"] = parts[3]
        except Exception:
            pass

        # Method 2: PyTorch CUDA
        try:
            import torch

            result["torch_cuda"] = torch.cuda.is_available()
            if result["torch_cuda"]:
                result["cuda_available"] = True
                result["cuda_version"] = torch.version.cuda
                if not result["available"]:
                    result["available"] = True
                    result["name"] = torch.cuda.get_device_name(0)
        except ImportError:
            pass

        # Method 3: ONNX Runtime
        try:
            import onnxruntime as ort

            providers = ort.get_available_providers()
            result["onnx_providers"] = providers
            result["onnx_gpu_available"] = "CUDAExecutionProvider" in providers
            if result["onnx_gpu_available"]:
                result["cuda_available"] = True
        except ImportError:
            pass

        return result

    @staticmethod
    def get_disk_info() -> dict:
        """Return disk usage info."""
        disk = shutil.disk_usage("/")
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        }

    @staticmethod
    def get_python_info() -> dict:
        """Return Python environment info."""
        return {
            "version": platform.python_version(),
            "platform": platform.platform(),
        }

    @staticmethod
    def get_model_info() -> dict:
        """Return info about active AI models."""
        from app.core.config import settings

        return {
            "deepface_model": settings.DEEPFACE_MODEL,
            "face_detector": settings.FACE_DETECTOR,
            "yolo_confidence": settings.YOLO_CONFIDENCE,
            "face_tracker": settings.FACE_TRACKER,
            "detection_interval": settings.DETECTION_INTERVAL_SECONDS,
            "frame_broadcast_fps": settings.FRAME_BROADCAST_FPS,
            "available_models": [
                "VGG-Face",
                "Facenet",
                "OpenFace",
                "DeepID",
                "ArcFace",
                "Dlib",
            ],
            "available_detectors": [
                "opencv",
                "retinaface",
                "mtcnn",
                "ssd",
                "dlib",
                "yolov8",
            ],
        }

    @classmethod
    def get_full_info(cls) -> dict:
        """Return all system info in a single payload.

        .. deprecated::
            Use ``system_info_cache.get_full_info()`` for cached reads.
            This method is kept for the background refresh worker.
        """
        return {
            "cpu": cls.get_cpu_info(),
            "memory": cls.get_memory_info(),
            "gpu": cls.get_gpu_info(),
            "disk": cls.get_disk_info(),
            "python": cls.get_python_info(),
            "models": cls.get_model_info(),
            "acceleration": cls._get_acceleration_recommendation(),
        }

    @classmethod
    def _get_acceleration_recommendation(cls) -> dict:
        """Provide hardware acceleration recommendation."""
        gpu = cls.get_gpu_info()
        return cls._get_acceleration_recommendation_from(gpu)

    @staticmethod
    def _get_acceleration_recommendation_from(gpu: dict) -> dict:
        """Build recommendation from a pre-fetched GPU dict (no I/O)."""
        if gpu["cuda_available"]:
            return {
                "recommended": "CUDA GPU",
                "status": "optimal",
                "message": f"GPU {gpu['name']} terdeteksi dengan CUDA. Performa optimal.",
                "tips": [
                    "Pastikan CUDA toolkit terinstall",
                    "Install onnxruntime-gpu untuk akselerasi model",
                    "Gunakan batch processing untuk throughput lebih tinggi",
                ],
            }
        elif gpu["available"]:
            return {
                "recommended": "GPU (tanpa CUDA)",
                "status": "partial",
                "message": f"GPU {gpu['name']} terdeteksi tapi CUDA tidak tersedia.",
                "tips": [
                    "Install NVIDIA CUDA Toolkit",
                    "Install cuDNN yang sesuai",
                    "Pastikan driver NVIDIA terbaru",
                ],
            }
        else:
            return {
                "recommended": "CPU Only",
                "status": "fallback",
                "message": "Tidak ada GPU terdeteksi. Menggunakan CPU.",
                "tips": [
                    "Pertimbangkan menggunakan GPU NVIDIA untuk 5-10x speedup",
                    "Tingkatkan DETECTION_INTERVAL_SECONDS jika CPU lambat",
                    "Gunakan model yang lebih ringan (opencv detector)",
                ],
            }

    @classmethod
    def get_uptime_seconds(cls) -> float:
        """Return the server uptime in seconds."""
        return round(time.time() - _start_time, 1)
