"""
MySQL/MariaDB client via SQLAlchemy — replaces supabase_client.py.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    return SessionLocal()


def ping_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _ensure_local_dir() -> str:
    path = os.path.abspath(settings.SNAPSHOT_LOCAL_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _get_snapshot_base_url() -> str:
    """Build the snapshot base URL, resolving SERVER_IP if needed.

    The default value "http://${SERVER_IP}:8000" uses shell-style variable
    syntax that Python's os.getenv() does NOT expand. We resolve it
    explicitly so snapshot URLs stored in the DB are always valid.
    """
    raw = os.getenv("SNAPSHOT_BASE_URL", "")

    # If explicitly set and doesn't contain the un-expanded placeholder, use it
    if raw and "${SERVER_IP}" not in raw and "$SERVER_IP" not in raw:
        return raw.rstrip("/")

    # Fall back to SERVER_IP env var (set in docker-compose via VITE_API_URL pattern)
    server_ip = os.getenv("SERVER_IP", "")
    if server_ip:
        return f"http://{server_ip}:8000"

    # Last resort: use the backend's own port (works for same-host access)
    port = os.getenv("PORT", "8000")
    return f"http://localhost:{port}"


def upload_snapshot(image_bytes: bytes, camera_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{camera_id}/{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    base = _ensure_local_dir()
    full_path = os.path.join(base, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(image_bytes)

    base_url = _get_snapshot_base_url()
    return f"{base_url}/snapshots/{filename}"