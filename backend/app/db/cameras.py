"""
CRUD operations for the ``cameras`` table in Supabase.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.supabase_client import get_supabase
from app.models.schemas import CameraCreate, CameraUpdate, CameraResponse

TABLE = "cameras"


def create_camera(data: CameraCreate) -> CameraResponse:
    """Insert a new camera row and return it."""
    client = get_supabase()
    row = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "rtsp_url": data.rtsp_url,
        "status": "offline",
        "detection_zone": data.detection_zone,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = client.table(TABLE).insert(row).execute()
    return CameraResponse(**result.data[0])


def get_cameras() -> list[CameraResponse]:
    """Return every camera, ordered by creation date."""
    client = get_supabase()
    result = client.table(TABLE).select("*").order("created_at", desc=True).execute()
    return [CameraResponse(**r) for r in result.data]


def get_camera(camera_id: str) -> Optional[CameraResponse]:
    """Fetch a single camera by ID, or ``None``."""
    client = get_supabase()
    result = (
        client.table(TABLE)
        .select("*")
        .eq("id", camera_id)
        .maybe_single()
        .execute()
    )
    if result.data is None:
        return None
    return CameraResponse(**result.data)


def update_camera(camera_id: str, data: CameraUpdate) -> Optional[CameraResponse]:
    """Update fields on an existing camera."""
    client = get_supabase()
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return get_camera(camera_id)

    result = (
        client.table(TABLE)
        .update(updates)
        .eq("id", camera_id)
        .execute()
    )
    if not result.data:
        return None
    return CameraResponse(**result.data[0])


def delete_camera(camera_id: str) -> bool:
    """Delete a camera. Returns ``True`` if a row was removed."""
    client = get_supabase()
    result = client.table(TABLE).delete().eq("id", camera_id).execute()
    return bool(result.data)


def update_camera_status(camera_id: str, status: str) -> None:
    """Set the status column (``offline`` | ``live`` | ``processing``)."""
    client = get_supabase()
    client.table(TABLE).update({"status": status}).eq("id", camera_id).execute()


def get_camera_raw(camera_id: str) -> Optional[dict]:
    """Fetch a single camera as a raw dict (includes detection_zone)."""
    client = get_supabase()
    result = (
        client.table(TABLE)
        .select("*")
        .eq("id", camera_id)
        .maybe_single()
        .execute()
    )
    return result.data
