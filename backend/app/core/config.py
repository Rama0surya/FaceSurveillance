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

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    class Config:
        env_file = _find_env_file()
        extra = "ignore"


settings = Settings()