from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
import numpy as np
from sqlalchemy import text
from app.core.db_client import get_db


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types produced by InsightFace/DeepFace."""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def _sanitize_faces(faces_data: list[dict]) -> list[dict]:
    """Remove non-serializable fields (embeddings) before storing to DB.

    The embedding field is a numpy array stored separately in the snapshots
    table as LONGBLOB. Keeping it in the faces JSON would cause NumpyEncoder
    to inline a large float array into every detection row — wasteful and
    the source of serialization failures when NumpyEncoder isn't applied.

    We strip it here and rely on the snapshots.embedding column instead.
    """
    sanitized = []
    for face in faces_data:
        clean = {k: v for k, v in face.items() if k != "embedding"}
        sanitized.append(clean)
    return sanitized


def insert_detection(camera_id: str, faces_data: list[dict], timestamp: Optional[str] = None) -> str:
    db = get_db()
    try:
        did = str(uuid.uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        # Sanitize first (remove numpy arrays / embedding blobs)
        clean_faces = _sanitize_faces(faces_data)

        # Always use NumpyEncoder to safely handle any remaining numpy scalars
        # (age as np.int64, confidence as np.float32, etc.)
        faces_json = json.dumps(clean_faces, cls=NumpyEncoder)

        db.execute(text("""
            INSERT INTO detections (id, camera_id, timestamp, faces)
            VALUES (:id, :camera_id, :timestamp, :faces)
        """), {"id": did, "camera_id": camera_id, "timestamp": ts, "faces": faces_json})
        db.commit()
        return did
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def insert_snapshot(camera_id: str, detection_id: str, url: str, embedding: Optional[np.ndarray] = None) -> str:
    db = get_db()
    try:
        sid = str(uuid.uuid4())
        emb_bytes = embedding.astype(np.float32).tobytes() if embedding is not None else None
        db.execute(text("""
            INSERT INTO snapshots (id, camera_id, detection_id, url, embedding, created_at)
            VALUES (:id, :camera_id, :detection_id, :url, :embedding, :created_at)
        """), {"id": sid, "camera_id": camera_id, "detection_id": detection_id,
               "url": url, "embedding": emb_bytes, "created_at": datetime.now(timezone.utc).isoformat()})
        db.commit()
        return sid
    except Exception:
        db.rollback()
        raise
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


def search_snapshots_by_embedding(
    query_embedding: np.ndarray,
    camera_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 20,
    similarity_threshold: float = 0.15
) -> list[dict]:
    db = get_db()
    try:
        conds = ["embedding IS NOT NULL"]
        params = {}
        if camera_id:
            conds.append("s.camera_id = :camera_id")
            params["camera_id"] = camera_id
        if date_from:
            conds.append("s.created_at >= :date_from")
            params["date_from"] = date_from
        if date_to:
            conds.append("s.created_at <= :date_to")
            params["date_to"] = date_to

        where = " AND ".join(conds)
        rows = db.execute(text(f"""
            SELECT s.id, s.url, s.created_at, s.camera_id, s.detection_id, s.embedding,
                   c.name AS camera_name, d.faces AS faces_json, d.timestamp AS detection_timestamp
            FROM snapshots s
            LEFT JOIN cameras    c ON c.id = s.camera_id
            LEFT JOIN detections d ON d.id = s.detection_id
            WHERE {where}
            ORDER BY s.created_at DESC
        """), params).mappings().all()

        if not rows:
            return []

        ids, urls, created_ats, camera_ids, camera_names = [], [], [], [], []
        detection_ids, faces_jsons, detection_timestamps, embeddings = [], [], [], []

        for row in rows:
            emb = np.frombuffer(row["embedding"], dtype=np.float32)
            if emb.shape[0] != query_embedding.shape[0]:
                continue
            ids.append(row["id"])
            urls.append(row["url"])
            created_ats.append(row["created_at"])
            camera_ids.append(row["camera_id"])
            camera_names.append(row["camera_name"] or "")
            detection_ids.append(row["detection_id"])
            faces_jsons.append(row["faces_json"])
            detection_timestamps.append(row["detection_timestamp"])
            embeddings.append(emb)

        if not embeddings:
            return []

        embeddings_matrix = np.array(embeddings)
        query_normalized = query_embedding.astype(np.float32)
        query_norm = np.linalg.norm(query_normalized)
        if query_norm > 0:
            query_normalized = query_normalized / query_norm

        similarities = embeddings_matrix @ query_normalized
        scored = [(i, float(s)) for i, s in enumerate(similarities) if s >= similarity_threshold]
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[:limit]

        results = []
        for idx, sim in scored:
            raw = faces_jsons[idx]
            faces = json.loads(raw) if isinstance(raw, str) else (raw or [])
            face_info = next((f for f in faces if f.get("snapshot_url") == urls[idx]), {})
            if not face_info and faces:
                face_info = faces[0]

            results.append({
                "id": ids[idx],
                "url": urls[idx],
                "gender": face_info.get("gender", ""),
                "emotion": face_info.get("emotion", ""),
                "age": face_info.get("age", 0),
                "age_group": face_info.get("age_group", ""),
                "camera_name": camera_names[idx],
                "camera_id": camera_ids[idx],
                "detection_id": detection_ids[idx],
                "timestamp": str(detection_timestamps[idx] or created_ats[idx]),
                "similarity": round(sim, 4),
            })
        return results
    finally:
        db.close()