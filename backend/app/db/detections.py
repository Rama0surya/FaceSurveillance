from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from app.core.db_client import get_db


def insert_detection(camera_id: str, faces_data: list[dict], timestamp: Optional[str] = None) -> str:
    db = get_db()
    try:
        did = str(uuid.uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        db.execute(text("""
            INSERT INTO detections (id, camera_id, timestamp, faces)
            VALUES (:id, :camera_id, :timestamp, :faces)
        """), {"id": did, "camera_id": camera_id, "timestamp": ts, "faces": json.dumps(faces_data)})
        db.commit()
        return did
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def insert_snapshot(camera_id: str, detection_id: str, url: str) -> str:
    db = get_db()
    try:
        sid = str(uuid.uuid4())
        db.execute(text("""
            INSERT INTO snapshots (id, camera_id, detection_id, url, created_at)
            VALUES (:id, :camera_id, :detection_id, :url, :created_at)
        """), {"id": sid, "camera_id": camera_id, "detection_id": detection_id,
               "url": url, "created_at": datetime.now(timezone.utc).isoformat()})
        db.commit()
        return sid
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def query_detections(camera_id=None, date_from=None, date_to=None,
                     emotion=None, gender=None, page=1, per_page=20) -> list[dict]:
    db = get_db()
    try:
        conds, params = [], {"limit": per_page, "offset": (page - 1) * per_page}
        if camera_id: conds.append("camera_id = :camera_id"); params["camera_id"] = camera_id
        if date_from: conds.append("timestamp >= :date_from"); params["date_from"] = date_from
        if date_to:   conds.append("timestamp <= :date_to");   params["date_to"] = date_to
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = db.execute(text(f"""
            SELECT * FROM detections {where}
            ORDER BY timestamp DESC LIMIT :limit OFFSET :offset
        """), params).mappings().all()
        rows = [_parse_detection(dict(r)) for r in rows]
        if emotion or gender:
            filtered = []
            for row in rows:
                faces = row.get("faces", [])
                m = [f for f in faces
                     if (not emotion or f.get("emotion") == emotion)
                     and (not gender or f.get("gender") == gender)]
                if m:
                    row["faces"] = m; filtered.append(row)
            return filtered
        return rows
    finally:
        db.close()


def get_snapshots(page=1, per_page=20, camera_id=None) -> list[dict]:
    db = get_db()
    try:
        conds, params = [], {"limit": per_page, "offset": (page - 1) * per_page}
        if camera_id: conds.append("camera_id = :camera_id"); params["camera_id"] = camera_id
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = db.execute(text(f"""
            SELECT * FROM snapshots {where}
            ORDER BY created_at DESC LIMIT :limit OFFSET :offset
        """), params).mappings().all()
        return [_parse_snapshot(dict(r)) for r in rows]
    finally:
        db.close()


def query_snapshots_enriched(camera_id=None, date=None, emotion=None, limit=20, offset=0) -> list[dict]:
    db = get_db()
    try:
        conds, params = ["1=1"], {"limit": limit, "offset": offset}
        if camera_id: conds.append("s.camera_id = :camera_id"); params["camera_id"] = camera_id
        if date:      conds.append("DATE(s.created_at) = :date"); params["date"] = date
        where = " AND ".join(conds)
        rows = db.execute(text(f"""
            SELECT s.id, s.url, s.created_at, s.camera_id, s.detection_id,
                   c.name AS camera_name, d.faces AS faces_json, d.timestamp AS detection_timestamp
            FROM snapshots s
            LEFT JOIN cameras    c ON c.id = s.camera_id
            LEFT JOIN detections d ON d.id = s.detection_id
            WHERE {where}
            ORDER BY s.created_at DESC LIMIT :limit OFFSET :offset
        """), params).mappings().all()

        enriched = []
        for row in rows:
            row = dict(row)
            raw = row.get("faces_json")
            faces = json.loads(raw) if isinstance(raw, str) else (raw or [])
            face_info = next((f for f in faces if f.get("snapshot_url") == row.get("url")), {})
            if not face_info and faces:
                face_info = faces[0]
            enriched.append({
                "id": row["id"], "url": row.get("url", ""),
                "gender": face_info.get("gender", ""), "emotion": face_info.get("emotion", ""),
                "age": face_info.get("age", 0), "age_group": face_info.get("age_group", ""),
                "camera_name": row.get("camera_name", ""),
                "timestamp": str(row.get("detection_timestamp") or row.get("created_at", "")),
            })
        if emotion:
            enriched = [e for e in enriched if e.get("emotion") == emotion]
        return enriched
    finally:
        db.close()


def _parse_detection(row: dict) -> dict:
    f = row.get("faces")
    if f and isinstance(f, str): row["faces"] = json.loads(f)
    if row.get("timestamp"): row["timestamp"] = str(row["timestamp"])
    return row

def _parse_snapshot(row: dict) -> dict:
    if row.get("created_at"): row["created_at"] = str(row["created_at"])
    return row