"""
Hourly statistics persistence and query helpers.

Key fix: ``upsert_hourly_stats`` now uses a single atomic
``INSERT … ON DUPLICATE KEY UPDATE`` statement with MySQL 8.0
``JSON_SET()`` for counter merging.  This eliminates the
SELECT-then-INSERT race condition that caused IntegrityError
under concurrent camera streams.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import text

from app.core.db_client import get_db

logger = logging.getLogger(__name__)


# =====================================================================
# Helpers
# =====================================================================

def _hour_bucket(dt: Optional[datetime] = None) -> str:
    """Return the current hour bucket as an ISO timestamp string."""
    dt = dt or datetime.now(timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()


def _j(v) -> dict:
    """Parse a value into a dict (from JSON string or dict passthrough)."""
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


# =====================================================================
# Atomic UPSERT — eliminates IntegrityError race condition
# =====================================================================

def upsert_hourly_stats(
    camera_id: str,
    gender: str,
    emotion: str,
    age_group: str,
) -> None:
    """Atomically insert or update an hourly stats row.

    Uses MySQL ``INSERT … ON DUPLICATE KEY UPDATE`` on the
    ``uq_hourly(camera_id, hour_bucket)`` unique constraint.

    JSON counters (emotions, age_groups) are merged atomically using
    ``JSON_SET()`` with ``COALESCE + JSON_EXTRACT`` for the increment.

    This is a single statement — no SELECT needed, no race window.
    """
    db = get_db()
    try:
        hour = _hour_bucket()
        male_val = 1 if gender == "Man" else 0
        female_val = 1 if gender == "Woman" else 0

        # Build the initial JSON for INSERT (new row case)
        init_emotions = json.dumps({emotion: 1})
        init_age_groups = json.dumps({age_group: 1})

        # The emotion and age_group keys must be safely quoted.
        # We use parameterised JSON path expressions via MySQL JSON_SET.
        # JSON path: $."<key>" — handles keys with special characters.
        emotion_path = f'$."{emotion}"'
        age_group_path = f'$."{age_group}"'

        db.execute(text("""
            INSERT INTO hourly_stats
                (id, camera_id, hour_bucket, total, male, female, emotions, age_groups)
            VALUES
                (:id, :camera_id, :hour, 1, :male, :female, :init_emo, :init_age)
            ON DUPLICATE KEY UPDATE
                total      = total + 1,
                male       = male + VALUES(male),
                female     = female + VALUES(female),
                emotions   = JSON_SET(
                    COALESCE(emotions, '{}'),
                    :emo_path,
                    COALESCE(
                        JSON_EXTRACT(emotions, :emo_path), 0
                    ) + 1
                ),
                age_groups = JSON_SET(
                    COALESCE(age_groups, '{}'),
                    :age_path,
                    COALESCE(
                        JSON_EXTRACT(age_groups, :age_path), 0
                    ) + 1
                )
        """), {
            "id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "hour": hour,
            "male": male_val,
            "female": female_val,
            "init_emo": init_emotions,
            "init_age": init_age_groups,
            "emo_path": emotion_path,
            "age_path": age_group_path,
        })
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =====================================================================
# Query helpers (unchanged logic, cleaned up formatting)
# =====================================================================

def get_today_stats(camera_id: Optional[str] = None) -> list[dict]:
    """Aggregate today's hourly stats per camera."""
    db = get_db()
    try:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).isoformat()
        params: dict = {"today": today}
        camera_filter = ""
        if camera_id:
            camera_filter = "AND camera_id = :c"
            params["c"] = camera_id

        rows = db.execute(text(
            f"SELECT * FROM hourly_stats WHERE hour_bucket >= :today {camera_filter}"
        ), params).mappings().all()

        aggregated: dict[str, dict] = {}
        for row in rows:
            row = dict(row)
            cid = row["camera_id"]
            if cid not in aggregated:
                aggregated[cid] = {
                    "camera_id": cid,
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "total": 0,
                    "male": 0,
                    "female": 0,
                    "emotions": {},
                    "age_groups": {},
                }
            bucket = aggregated[cid]
            bucket["total"] += row.get("total", 0)
            bucket["male"] += row.get("male", 0)
            bucket["female"] += row.get("female", 0)
            for k, v in _j(row.get("emotions")).items():
                bucket["emotions"][k] = bucket["emotions"].get(k, 0) + v
            for k, v in _j(row.get("age_groups")).items():
                bucket["age_groups"][k] = bucket["age_groups"].get(k, 0) + v

        return list(aggregated.values())
    finally:
        db.close()


def get_hourly_stats(
    camera_id: Optional[str] = None,
    date: Optional[str] = None,
) -> list[dict]:
    """Return hourly stats rows for a given date (defaults to today)."""
    db = get_db()
    try:
        if date:
            ds = datetime.fromisoformat(date).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc,
            )
        else:
            ds = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
        de = ds + timedelta(days=1)
        params: dict = {"ds": ds.isoformat(), "de": de.isoformat()}
        camera_filter = ""
        if camera_id:
            camera_filter = "AND camera_id = :c"
            params["c"] = camera_id

        rows = db.execute(text(f"""
            SELECT * FROM hourly_stats
            WHERE hour_bucket >= :ds AND hour_bucket < :de {camera_filter}
            ORDER BY hour_bucket ASC
        """), params).mappings().all()

        result = []
        for row in rows:
            row = dict(row)
            row["emotions"] = _j(row.get("emotions"))
            row["age_groups"] = _j(row.get("age_groups"))
            hb = str(row.get("hour_bucket", ""))
            try:
                row["hour"] = datetime.fromisoformat(hb).hour
            except (ValueError, TypeError):
                row["hour"] = None
            row["date"] = ds.strftime("%Y-%m-%d")
            row["hour_bucket"] = hb
            result.append(row)
        return result
    finally:
        db.close()


def get_comparison_stats(camera_id: Optional[str] = None) -> dict:
    """Compare today's total detections with yesterday's."""
    db = get_db()
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        camera_filter = ""
        params_today: dict = {"s": today_start.isoformat()}
        params_yesterday: dict = {
            "s": yesterday_start.isoformat(),
            "e": today_start.isoformat(),
        }
        if camera_id:
            camera_filter = "AND camera_id = :c"
            params_today["c"] = camera_id
            params_yesterday["c"] = camera_id

        today_total = db.execute(text(
            f"SELECT COALESCE(SUM(total),0) FROM hourly_stats "
            f"WHERE hour_bucket >= :s {camera_filter}"
        ), params_today).scalar() or 0

        yesterday_total = db.execute(text(
            f"SELECT COALESCE(SUM(total),0) FROM hourly_stats "
            f"WHERE hour_bucket >= :s AND hour_bucket < :e {camera_filter}"
        ), params_yesterday).scalar() or 0

        if yesterday_total > 0:
            change_pct = round(
                ((today_total - yesterday_total) / yesterday_total) * 100, 1,
            )
        else:
            change_pct = 100.0 if today_total > 0 else 0.0

        return {
            "today": {"total": int(today_total)},
            "yesterday": {"total": int(yesterday_total)},
            "change_pct": change_pct,
        }
    finally:
        db.close()