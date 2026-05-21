"""
Mock data generator for development and demo purposes.

Uses MySQL 8.0 UPSERT (INSERT ... ON DUPLICATE KEY UPDATE) for
hourly_stats to prevent IntegrityError on duplicate (camera_id, hour_bucket).
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from app.core.db_client import get_db

EMOTIONS   = ["happy", "neutral", "sad", "angry", "surprise", "fear", "disgust"]
GENDERS    = ["male", "female"]
AGE_GROUPS = ["anak", "remaja", "dewasa", "lansia"]
AGE_RANGES = {"anak": (4, 12), "remaja": (13, 17), "dewasa": (18, 59), "lansia": (60, 85)}
CAMERA_NAMES = ["Lobby Utama", "Pintu Masuk", "Area Parkir"]
CAMERA_URLS  = [
    "rtsp://192.168.1.10:554/stream1",
    "rtsp://192.168.1.11:554/stream1",
    "rtsp://192.168.1.12:554/stream1",
]

# MySQL 8.0 UPSERT query for hourly_stats.
# If a row with the same (camera_id, hour_bucket) already exists,
# merge the new values into the existing row atomically.
_UPSERT_HOURLY_STATS = text("""
    INSERT INTO hourly_stats
        (id, camera_id, hour_bucket, total, male, female, emotions, age_groups)
    VALUES
        (:id, :camera_id, :hour_bucket, :total, :male, :female, :emotions, :age_groups)
    ON DUPLICATE KEY UPDATE
        total      = total      + :add_total,
        male       = male       + :add_male,
        female     = female     + :add_female,
        emotions   = :merged_emotions,
        age_groups = :merged_age_groups
""")


def _merge_json_counters(existing_json: str | dict | None, new_counts: dict) -> dict:
    """Merge two counter dicts (e.g. {"happy": 3} + {"happy": 2} → {"happy": 5}).

    ``existing_json`` may be a JSON string from the DB or a Python dict.
    """
    if existing_json is None:
        return dict(new_counts)
    if isinstance(existing_json, str):
        existing_json = json.loads(existing_json)
    merged = dict(existing_json)
    for k, v in new_counts.items():
        merged[k] = merged.get(k, 0) + v
    return merged


def generate_mock_data(num_detections: int = 100, hours_span: int = 48) -> dict:
    """Generate mock face-detection data.

    Returns a summary dict with counts of created records.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        # ── Ensure cameras exist ──
        camera_ids: list[str] = []
        existing = {
            r["name"]: r["id"]
            for r in db.execute(text("SELECT id, name FROM cameras")).mappings().all()
        }
        for i, name in enumerate(CAMERA_NAMES):
            if name in existing:
                camera_ids.append(existing[name])
            else:
                cid = str(uuid.uuid4())
                db.execute(
                    text(
                        "INSERT INTO cameras (id, name, rtsp_url, status, created_at) "
                        "VALUES (:id, :n, :u, 'offline', :t)"
                    ),
                    {"id": cid, "n": name, "u": CAMERA_URLS[i], "t": now.isoformat()},
                )
                camera_ids.append(cid)

        # Include any other cameras already in the DB
        for cid in existing.values():
            if cid not in camera_ids:
                camera_ids.append(cid)
        db.commit()

        # ── Generate detections & snapshots ──
        det_count = snap_count = 0
        buckets: dict[str, dict] = {}

        for _ in range(num_detections):
            cam = random.choice(camera_ids)
            ts = now - timedelta(seconds=random.randint(0, hours_span * 3600))
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            faces = []

            for _ in range(random.randint(1, 3)):
                g = random.choice(GENDERS)
                e = random.choice(EMOTIONS)
                ag = random.choices(AGE_GROUPS, weights=[10, 15, 55, 20], k=1)[0]
                age = random.randint(*AGE_RANGES[ag])
                fid = str(uuid.uuid4())

                faces.append({
                    "id": fid,
                    "bbox": {
                        "x": random.randint(50, 500),
                        "y": random.randint(30, 400),
                        "w": random.randint(60, 150),
                        "h": random.randint(60, 180),
                    },
                    "gender": g,
                    "emotion": e,
                    "age_group": ag,
                    "age": age,
                    "confidence": round(random.uniform(0.70, 0.99), 2),
                    "snapshot_url": f"/snapshots/mock/{fid[:8]}.jpg",
                })

                # Accumulate into hour buckets
                hb = ts.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                k = f"{cam}|{hb}"
                if k not in buckets:
                    buckets[k] = {
                        "camera_id": cam,
                        "hour_bucket": hb,
                        "total": 0,
                        "male": 0,
                        "female": 0,
                        "emotions": {},
                        "age_groups": {},
                    }
                b = buckets[k]
                b["total"] += 1
                if g == "male":
                    b["male"] += 1
                else:
                    b["female"] += 1
                b["emotions"][e] = b["emotions"].get(e, 0) + 1
                b["age_groups"][ag] = b["age_groups"].get(ag, 0) + 1

            did = str(uuid.uuid4())
            db.execute(
                text(
                    "INSERT INTO detections (id, camera_id, timestamp, faces) "
                    "VALUES (:id, :c, :t, :f)"
                ),
                {"id": did, "c": cam, "t": ts_str, "f": json.dumps(faces)},
            )
            det_count += 1

            for face in faces:
                db.execute(
                    text(
                        "INSERT INTO snapshots (id, camera_id, detection_id, url, created_at) "
                        "VALUES (:id, :c, :d, :u, :t)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "c": cam,
                        "d": did,
                        "u": face["snapshot_url"],
                        "t": ts_str,
                    },
                )
                snap_count += 1

        db.commit()

        # ── Upsert hourly_stats (race-condition safe) ──
        stats_count = 0
        for key, b in buckets.items():
            # Fetch existing row to merge JSON counters properly
            existing_row = db.execute(
                text(
                    "SELECT emotions, age_groups FROM hourly_stats "
                    "WHERE camera_id = :c AND hour_bucket = :h LIMIT 1"
                ),
                {"c": b["camera_id"], "h": b["hour_bucket"]},
            ).mappings().first()

            if existing_row:
                merged_emo = _merge_json_counters(existing_row["emotions"], b["emotions"])
                merged_age = _merge_json_counters(existing_row["age_groups"], b["age_groups"])
            else:
                merged_emo = b["emotions"]
                merged_age = b["age_groups"]

            db.execute(
                _UPSERT_HOURLY_STATS,
                {
                    "id": str(uuid.uuid4()),
                    "camera_id": b["camera_id"],
                    "hour_bucket": b["hour_bucket"],
                    "total": b["total"],
                    "male": b["male"],
                    "female": b["female"],
                    "emotions": json.dumps(b["emotions"]),
                    "age_groups": json.dumps(b["age_groups"]),
                    # ON DUPLICATE KEY UPDATE params
                    "add_total": b["total"],
                    "add_male": b["male"],
                    "add_female": b["female"],
                    "merged_emotions": json.dumps(merged_emo),
                    "merged_age_groups": json.dumps(merged_age),
                },
            )
            stats_count += 1

        db.commit()

        return {
            "cameras": len(camera_ids),
            "detections": det_count,
            "snapshots": snap_count,
            "hourly_stats_buckets": stats_count,
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()