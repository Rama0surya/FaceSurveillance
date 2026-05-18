"""
Supabase client singleton and snapshot upload helpers.
"""

import os
import uuid
from datetime import datetime

from supabase import create_client, Client

from app.core.config import settings

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------
_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Return (and lazily initialise) the Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_API_KEY,
        )
    return _supabase_client


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _ensure_local_dir() -> str:
    """Create the local snapshots directory if it doesn't exist."""
    path = os.path.abspath(settings.SNAPSHOT_LOCAL_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def upload_snapshot(image_bytes: bytes, camera_id: str) -> str:
    """
    Save a face-crop snapshot and return its public URL.

    Depending on ``settings.SNAPSHOT_STORAGE`` this either writes to the
    local filesystem or uploads to Supabase Storage.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{camera_id}/{timestamp}_{uuid.uuid4().hex[:8]}.jpg"

    if settings.SNAPSHOT_STORAGE == "supabase":
        return _upload_to_supabase(image_bytes, filename)
    else:
        return _save_locally(image_bytes, filename)


def _upload_to_supabase(image_bytes: bytes, filename: str) -> str:
    """Upload to Supabase Storage and return the public URL."""
    client = get_supabase()
    bucket = settings.SUPABASE_STORAGE_BUCKET

    client.storage.from_(bucket).upload(
        path=filename,
        file=image_bytes,
        file_options={"content-type": "image/jpeg"},
    )

    public_url = client.storage.from_(bucket).get_public_url(filename)
    return public_url


def _save_locally(image_bytes: bytes, filename: str) -> str:
    """Save to the local ``snapshots/`` directory and return a relative URL."""
    base = _ensure_local_dir()
    full_path = os.path.join(base, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "wb") as f:
        f.write(image_bytes)

    # Return a URL that will be served via FastAPI static-files mount
    return f"/snapshots/{filename}"
