"""
MySQL/MariaDB client via SQLAlchemy — replaces supabase_client.py.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime
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


def upload_snapshot(image_bytes: bytes, camera_id: str) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{camera_id}/{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    base = _ensure_local_dir()
    full_path = os.path.join(base, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    return f"/snapshots/{filename}"