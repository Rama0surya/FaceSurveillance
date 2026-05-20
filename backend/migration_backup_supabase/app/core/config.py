import os

from pydantic_settings import BaseSettings


def _find_env_file() -> str:
    """Try to locate .env in a few sensible places."""
    candidates = [
        os.path.join(os.getcwd(), ".env"),       # project root (if started there)
        os.path.join(os.getcwd(), "..", ".env"),   # from backend/ dir → parent
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),  # relative to this file
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    return ".env"  # fallback


class Settings(BaseSettings):
    # Environment mode
    ENV: str = "development"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_API_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_STORAGE_BUCKET: str = "snapshots"

    # DeepFace (retained for emotion analysis)
    DEEPFACE_MODEL: str = "VGG-Face"

    # Detection
    DETECTION_INTERVAL_SECONDS: float = 2.0
    FRAME_BROADCAST_FPS: int = 5

    # Model Pipeline
    FACE_DETECTOR: str = "yolov8"       # "yolov8" | "deepface_legacy"
    FACE_TRACKER: str = "bytetrack"     # "bytetrack" | "botsort" | "none"
    YOLO_CONFIDENCE: float = 0.5
    YOLO_MODEL_PATH: str = "yolov8n-face-lindevs.pt"
    INSIGHT_MODEL: str = "buffalo_l"
    USE_GPU: str = "auto"               # "auto" | "cuda" | "cpu"
    TRACK_REANALYZE_TTL: int = 300      # seconds before re-analyzing a tracked face

    # Snapshots
    SNAPSHOT_STORAGE: str = "local"  # "local" or "supabase"
    SNAPSHOT_LOCAL_DIR: str = "snapshots"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    # Security
    SECRET_KEY: str = "changeme"

    # WebSocket
    STATS_BROADCAST_INTERVAL: int = 5  # seconds between stats pushes

    # MediaMTX (optional RTSP proxy)
    MEDIAMTX_API_URL: str = "http://localhost:9997"
    MEDIAMTX_RTSP_URL: str = "rtsp://localhost:8554"
    USE_MEDIAMTX: bool = True  # Set to False to bypass MediaMTX entirely

    class Config:
        env_file = _find_env_file()


settings = Settings()
