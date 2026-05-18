"""
Mock data generator for demo / development purposes.

Generates fake detection, snapshot, and hourly_stats records
so the dashboard has realistic data without a real RTSP camera.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone, timedelta

from app.core.supabase_client import get_supabase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMOTIONS = ["happy", "neutral", "sad", "angry", "surprise", "fear", "disgust"]
GENDERS = ["male", "female"]
AGE_GROUPS = ["anak", "remaja", "dewasa", "lansia"]
AGE_RANGES = {
    "anak": (4, 12),
    "remaja": (13, 17),
    "dewasa": (18, 59),
    "lansia": (60, 85),
}

CAMERA_NAMES = [
    "Lobby Utama",
    "Pintu Masuk",
    "Area Parkir",
]

CAMERA_URLS = [
    "rtsp://192.168.1.10:554/stream1",
    "rtsp://192.168.1.11:554/stream1",
    "rtsp://192.168.1.12:554/stream1",
]


def _random_age(age_group: str) -> int:
    lo, hi = AGE_RANGES[age_group]
    return random.randint(lo, hi)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mock_data(
    num_detections: int = 100,
    hours_span: int = 48,
) -> dict:
    """
    Populate the Supabase database with mock cameras, detections,
    snapshots, and hourly_stats.

    Returns a summary dict.
    """
    client = get_supabase()
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # 1. Ensure demo cameras exist
    # ------------------------------------------------------------------
    camera_ids: list[str] = []

    existing = client.table("cameras").select("id, name").execute()
    existing_names = {r["name"] for r in (existing.data or [])}
    existing_ids = [r["id"] for r in (existing.data or [])]

    for i, name in enumerate(CAMERA_NAMES):
        if name in existing_names:
            # Reuse existing camera
            cam = next(r for r in existing.data if r["name"] == name)
            camera_ids.append(cam["id"])
        else:
            cam_id = str(uuid.uuid4())
            client.table("cameras").insert({
                "id": cam_id,
                "name": name,
                "rtsp_url": CAMERA_URLS[i],
                "status": "offline",
                "created_at": now.isoformat(),
            }).execute()
            camera_ids.append(cam_id)

    # If there were already cameras not in our list, include them too
    for cid in existing_ids:
        if cid not in camera_ids:
            camera_ids.append(cid)

    # ------------------------------------------------------------------
    # 2. Generate detections & snapshots
    # ------------------------------------------------------------------
    detection_count = 0
    snapshot_count = 0
    stats_buckets: dict[str, dict] = {}  # key = "camera_id|hour_iso"

    for _ in range(num_detections):
        camera_id = random.choice(camera_ids)
        # Random timestamp in the last `hours_span` hours
        offset_seconds = random.randint(0, hours_span * 3600)
        ts = now - timedelta(seconds=offset_seconds)
        timestamp = ts.isoformat()

        # 1-3 faces per detection
        num_faces = random.randint(1, 3)
        faces: list[dict] = []

        for _ in range(num_faces):
            gender = random.choice(GENDERS)
            emotion = random.choice(EMOTIONS)
            age_group = random.choices(
                AGE_GROUPS,
                weights=[10, 15, 55, 20],  # realistic distribution
                k=1,
            )[0]
            age = _random_age(age_group)
            face_id = str(uuid.uuid4())

            face = {
                "id": face_id,
                "bbox": {
                    "x": random.randint(50, 500),
                    "y": random.randint(30, 400),
                    "w": random.randint(60, 150),
                    "h": random.randint(60, 180),
                },
                "gender": gender,
                "emotion": emotion,
                "age_group": age_group,
                "age": age,
                "confidence": round(random.uniform(0.70, 0.99), 2),
                "snapshot_url": f"/snapshots/mock/{face_id[:8]}.jpg",
            }
            faces.append(face)

            # Accumulate stats for hourly bucket
            hour_bucket = ts.replace(minute=0, second=0, microsecond=0).isoformat()
            key = f"{camera_id}|{hour_bucket}"
            if key not in stats_buckets:
                stats_buckets[key] = {
                    "camera_id": camera_id,
                    "hour_bucket": hour_bucket,
                    "total": 0,
                    "male": 0,
                    "female": 0,
                    "emotions": {},
                    "age_groups": {},
                }
            bucket = stats_buckets[key]
            bucket["total"] += 1
            if gender == "male":
                bucket["male"] += 1
            else:
                bucket["female"] += 1
            bucket["emotions"][emotion] = bucket["emotions"].get(emotion, 0) + 1
            bucket["age_groups"][age_group] = bucket["age_groups"].get(age_group, 0) + 1

        # Insert detection
        detection_id = str(uuid.uuid4())
        client.table("detections").insert({
            "id": detection_id,
            "camera_id": camera_id,
            "timestamp": timestamp,
            "faces": faces,
        }).execute()
        detection_count += 1

        # Insert snapshots
        for face in faces:
            snap_id = str(uuid.uuid4())
            client.table("snapshots").insert({
                "id": snap_id,
                "camera_id": camera_id,
                "detection_id": detection_id,
                "url": face["snapshot_url"],
                "created_at": timestamp,
            }).execute()
            snapshot_count += 1

    # ------------------------------------------------------------------
    # 3. Upsert hourly_stats
    # ------------------------------------------------------------------
    stats_count = 0
    for key, bucket in stats_buckets.items():
        camera_id = bucket["camera_id"]
        hour_bucket = bucket["hour_bucket"]

        # Check if row exists
        existing_row = (
            client.table("hourly_stats")
            .select("id, total, male, female, emotions, age_groups")
            .eq("camera_id", camera_id)
            .eq("hour_bucket", hour_bucket)
            .maybe_single()
            .execute()
        )

        if existing_row.data:
            # Merge with existing
            row = existing_row.data
            emotions = row.get("emotions") or {}
            age_groups = row.get("age_groups") or {}
            for emo, cnt in bucket["emotions"].items():
                emotions[emo] = emotions.get(emo, 0) + cnt
            for ag, cnt in bucket["age_groups"].items():
                age_groups[ag] = age_groups.get(ag, 0) + cnt

            client.table("hourly_stats").update({
                "total": (row.get("total") or 0) + bucket["total"],
                "male": (row.get("male") or 0) + bucket["male"],
                "female": (row.get("female") or 0) + bucket["female"],
                "emotions": emotions,
                "age_groups": age_groups,
            }).eq("id", row["id"]).execute()
        else:
            client.table("hourly_stats").insert({
                "id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "hour_bucket": hour_bucket,
                "total": bucket["total"],
                "male": bucket["male"],
                "female": bucket["female"],
                "emotions": bucket["emotions"],
                "age_groups": bucket["age_groups"],
            }).execute()

        stats_count += 1

    return {
        "cameras": len(camera_ids),
        "detections": detection_count,
        "snapshots": snapshot_count,
        "hourly_stats_buckets": stats_count,
    }
