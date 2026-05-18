"""
CRUD operations for the ``detections`` and ``snapshots`` tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.supabase_client import get_supabase

DETECTIONS_TABLE = "detections"
SNAPSHOTS_TABLE = "snapshots"


def insert_detection(
    camera_id: str,
    faces_data: list[dict],
    timestamp: Optional[str] = None,
) -> str:
    """
    Insert a detection record with its faces payload.

    Returns the new detection ``id``.
    """
    client = get_supabase()
    detection_id = str(uuid.uuid4())
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    row = {
        "id": detection_id,
        "camera_id": camera_id,
        "timestamp": ts,
        "faces": faces_data,
    }
    client.table(DETECTIONS_TABLE).insert(row).execute()
    return detection_id


def insert_snapshot(
    camera_id: str,
    detection_id: str,
    url: str,
) -> str:
    """Insert a snapshot record and return its id."""
    client = get_supabase()
    snapshot_id = str(uuid.uuid4())
    row = {
        "id": snapshot_id,
        "camera_id": camera_id,
        "detection_id": detection_id,
        "url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table(SNAPSHOTS_TABLE).insert(row).execute()
    return snapshot_id


def query_detections(
    camera_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    emotion: Optional[str] = None,
    gender: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> list[dict]:
    """
    Query detections with optional filters.

    Emotion/gender filtering is done in-app because the ``faces`` column
    is JSONB and Supabase client doesn't support deep JSON predicates well.
    """
    client = get_supabase()
    query = client.table(DETECTIONS_TABLE).select("*")

    if camera_id:
        query = query.eq("camera_id", camera_id)
    if date_from:
        query = query.gte("timestamp", date_from)
    if date_to:
        query = query.lte("timestamp", date_to)

    query = query.order("timestamp", desc=True)

    offset = (page - 1) * per_page
    query = query.range(offset, offset + per_page - 1)

    result = query.execute()
    rows = result.data or []

    # In-app filter on faces JSONB for emotion / gender
    if emotion or gender:
        filtered: list[dict] = []
        for row in rows:
            faces = row.get("faces", [])
            matching_faces = [
                f for f in faces
                if (not emotion or f.get("emotion") == emotion)
                and (not gender or f.get("gender") == gender)
            ]
            if matching_faces:
                row["faces"] = matching_faces
                filtered.append(row)
        rows = filtered

    return rows


def get_snapshots(
    page: int = 1,
    per_page: int = 20,
    camera_id: Optional[str] = None,
) -> list[dict]:
    """Return snapshots with pagination."""
    client = get_supabase()
    query = client.table(SNAPSHOTS_TABLE).select("*")

    if camera_id:
        query = query.eq("camera_id", camera_id)

    query = query.order("created_at", desc=True)

    offset = (page - 1) * per_page
    query = query.range(offset, offset + per_page - 1)

    result = query.execute()
    return result.data or []


def query_snapshots_enriched(
    camera_id: Optional[str] = None,
    date: Optional[str] = None,
    emotion: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    Return enriched snapshot records with face data from the associated detection.

    Each result contains:
    ``{id, url, gender, emotion, age, age_group, camera_name, timestamp}``
    """
    client = get_supabase()

    query = (
        client.table(SNAPSHOTS_TABLE)
        .select("id, url, created_at, camera_id, detection_id, cameras(name), detections(faces, timestamp)")
    )

    if camera_id:
        query = query.eq("camera_id", camera_id)

    if date:
        # Filter by date range
        date_start = f"{date}T00:00:00+00:00"
        date_end = f"{date}T23:59:59+00:00"
        query = query.gte("created_at", date_start).lte("created_at", date_end)

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    result = query.execute()
    rows = result.data or []

    # Enrich each snapshot with face-level data from the detection JSONB
    enriched: list[dict] = []
    for row in rows:
        detection_data = row.get("detections") or {}
        camera_data = row.get("cameras") or {}
        faces = detection_data.get("faces", []) if isinstance(detection_data, dict) else []

        # Find the matching face by snapshot URL
        face_info: dict = {}
        for face in faces:
            if face.get("snapshot_url") == row.get("url"):
                face_info = face
                break

        # If no exact URL match, use the first face as fallback
        if not face_info and faces:
            face_info = faces[0]

        item = {
            "id": row["id"],
            "url": row.get("url", ""),
            "gender": face_info.get("gender", ""),
            "emotion": face_info.get("emotion", ""),
            "age": face_info.get("age", 0),
            "age_group": face_info.get("age_group", ""),
            "camera_name": camera_data.get("name", "") if isinstance(camera_data, dict) else "",
            "timestamp": detection_data.get("timestamp", row.get("created_at", "")),
        }
        enriched.append(item)

    # Apply emotion filter in-app (since it's inside JSONB)
    if emotion:
        enriched = [e for e in enriched if e.get("emotion") == emotion]

    return enriched

