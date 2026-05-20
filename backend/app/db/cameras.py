from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from app.core.db_client import get_db
from app.models.schemas import CameraCreate, CameraUpdate, CameraResponse


def create_camera(data: CameraCreate) -> CameraResponse:
    db = get_db()
    try:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        dz = json.dumps(data.detection_zone) if data.detection_zone else None
        db.execute(text("""
            INSERT INTO cameras (id, name, rtsp_url, status, detection_zone, created_at)
            VALUES (:id, :name, :rtsp_url, :status, :detection_zone, :created_at)
        """), {"id": row_id, "name": data.name, "rtsp_url": data.rtsp_url,
               "status": "offline", "detection_zone": dz, "created_at": now})
        db.commit()
        return get_camera(row_id)
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def get_cameras() -> list[CameraResponse]:
    db = get_db()
    try:
        rows = db.execute(text("SELECT * FROM cameras ORDER BY created_at DESC")).mappings().all()
        return [_row_to_camera(r) for r in rows]
    finally:
        db.close()


def get_camera(camera_id: str) -> Optional[CameraResponse]:
    db = get_db()
    try:
        row = db.execute(text("SELECT * FROM cameras WHERE id = :id LIMIT 1"),
                         {"id": camera_id}).mappings().first()
        return _row_to_camera(row) if row else None
    finally:
        db.close()


def get_camera_raw(camera_id: str) -> Optional[dict]:
    db = get_db()
    try:
        row = db.execute(text("SELECT * FROM cameras WHERE id = :id LIMIT 1"),
                         {"id": camera_id}).mappings().first()
        if not row:
            return None
        d = dict(row)
        if d.get("detection_zone") and isinstance(d["detection_zone"], str):
            d["detection_zone"] = json.loads(d["detection_zone"])
        return d
    finally:
        db.close()


def update_camera(camera_id: str, data: CameraUpdate) -> Optional[CameraResponse]:
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return get_camera(camera_id)
    db = get_db()
    try:
        if "detection_zone" in updates and updates["detection_zone"] is not None:
            updates["detection_zone"] = json.dumps(updates["detection_zone"])
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["camera_id"] = camera_id
        db.execute(text(f"UPDATE cameras SET {set_clause} WHERE id = :camera_id"), updates)
        db.commit()
        return get_camera(camera_id)
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def delete_camera(camera_id: str) -> bool:
    db = get_db()
    try:
        r = db.execute(text("DELETE FROM cameras WHERE id = :id"), {"id": camera_id})
        db.commit()
        return r.rowcount > 0
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def update_camera_status(camera_id: str, status: str) -> None:
    db = get_db()
    try:
        db.execute(text("UPDATE cameras SET status = :status WHERE id = :id"),
                   {"status": status, "id": camera_id})
        db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def _row_to_camera(row) -> CameraResponse:
    d = dict(row)
    if d.get("detection_zone") and isinstance(d["detection_zone"], str):
        d["detection_zone"] = json.loads(d["detection_zone"])
    if "created_at" in d and d["created_at"] is not None:
        d["created_at"] = str(d["created_at"])
    return CameraResponse(**d)