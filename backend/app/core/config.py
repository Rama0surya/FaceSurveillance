import os
from pydantic_settings import BaseSettings


def _find_env_file() -> str:
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.getcwd(), "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    return ".env"


class Settings(BaseSettings):
    ENV: str = "development"

    # MySQL / MariaDB
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "face_surveillance"

    DEEPFACE_MODEL: str = "VGG-Face"
    DETECTION_INTERVAL_SECONDS: float = 2.0
    FRAME_BROADCAST_FPS: int = 5

    FACE_DETECTOR: str = "yolov8"
    FACE_TRACKER: str = "bytetrack"
    YOLO_CONFIDENCE: float = 0.5
    YOLO_MODEL_PATH: str = "yolov8n-face-lindevs.pt"
    INSIGHT_MODEL: str = "buffalo_l"
    USE_GPU: str = "auto"
    TRACK_REANALYZE_TTL: int = 300

    # Multi-thread pipeline queue sizes
    FRAME_QUEUE_SIZE: int = 2       # Thread A → B: small = always-fresh frames
    ANALYSIS_QUEUE_SIZE: int = 10   # Thread B → C: buffer for heavy inference

    # Smart capture filters
    CAPTURE_MIN_CONFIDENCE: float = 0.65  # Skip YOLO detections below this confidence
    MIN_FACE_SIZE: int = 60               # Skip faces smaller than NxN pixels
    CAPTURE_COOLDOWN: float = 5.0         # Seconds between captures of same track_id

    SNAPSHOT_STORAGE: str = "local"
    SNAPSHOT_LOCAL_DIR: str = "snapshots"

    CORS_ORIGINS: str = "http://localhost:5173"
    SECRET_KEY: str = "changeme"
    STATS_BROADCAST_INTERVAL: int = 5

    MEDIAMTX_API_URL: str = "http://localhost:9997"
    MEDIAMTX_RTSP_URL: str = "rtsp://localhost:8554"
    MEDIAMTX_HLS_URL: str = "http://localhost:8888" 
    USE_MEDIAMTX: bool = True

    # ── RTSP / Streaming Performance (adopted from CCTV AI Jaya) ──
    READER_DECODE_FPS: int = 3              # Max decode rate for 2-phase reader (grab+retrieve)
    BROADCAST_FPS: int = 5                  # Max MJPEG broadcast FPS to frontend
    GRAY_FRAME_THRESHOLD: float = 5.0       # Stddev below this = corrupt/gray frame → skip
    RTSP_RECONNECT_DELAY: int = 2           # Initial reconnect delay (seconds)
    RTSP_RECONNECT_MAX: int = 30            # Max reconnect delay (seconds, exponential backoff cap)

    # ── AI Search Settings (adopted from CCTV AI Jaya) ──
    CLIP_ENABLED: bool = True
    CLIP_MODEL_PRESET: str = "clip-light"   # options: clip-light (RN50), clip (ViT-B-32), clip-heavy (ViT-L-14), siglip
    CLIP_MODEL_NAME: str = ""
    CLIP_PRETRAINED: str = ""

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    def get_clip_model_info(self) -> dict:
        """Resolve CLIP model parameters based on model preset or overrides."""
        CLIP_PRESETS = {
            "clip-light": {
                "model_name": "RN50",
                "pretrained": "openai",
                "embedding_dim": 1024,
                "description": "CLIP RN50 — lightweight, fast CPU inference, ~150MB",
            },
            "clip": {
                "model_name": "ViT-B-32",
                "pretrained": "laion2b_s34b_b79k",
                "embedding_dim": 512,
                "description": "CLIP ViT-B-32 — standard speed, moderate RAM, ~300MB",
            },
            "clip-heavy": {
                "model_name": "ViT-L-14",
                "pretrained": "datacomp_xl_s13b_b90k",
                "embedding_dim": 768,
                "description": "CLIP ViT-L-14 — heavy, accurate, ~900MB RAM",
            },
            "siglip": {
                "model_name": "ViT-SO400M-14-SigLIP-384",
                "pretrained": "webli",
                "embedding_dim": 1152,
                "description": "SigLIP SO400M — most accurate, ~1.5GB RAM",
            }
        }
        if self.CLIP_MODEL_NAME:
            return {
                "model_name": self.CLIP_MODEL_NAME,
                "pretrained": self.CLIP_PRETRAINED,
                "embedding_dim": None,
                "description": f"Custom model: {self.CLIP_MODEL_NAME}",
            }
        preset = self.CLIP_MODEL_PRESET.lower()
        if preset not in CLIP_PRESETS:
            preset = "clip-light"
        return CLIP_PRESETS[preset]

    class Config:
        env_file = _find_env_file()
        extra = "ignore"


settings = Settings()