"""
System information service — detects hardware, software environment,
and provides acceleration recommendations.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time

import psutil

logger = logging.getLogger(__name__)

# Track app start time for uptime calculation
_start_time = time.time()


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
            "available_models": ["VGG-Face", "Facenet", "OpenFace", "DeepID", "ArcFace", "Dlib"],
            "available_detectors": ["opencv", "retinaface", "mtcnn", "ssd", "dlib", "yolov8"],
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
        """Return all system info in a single payload."""
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
