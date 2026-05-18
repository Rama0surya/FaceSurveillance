"""
Operations on the ``hourly_stats`` table.

Each row represents a one-hour bucket for a single camera.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

from app.core.supabase_client import get_supabase

TABLE = "hourly_stats"


def _hour_bucket(dt: Optional[datetime] = None) -> str:
    """Return an ISO timestamp truncated to the current hour."""
    dt = dt or datetime.now(timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()


def upsert_hourly_stats(
    camera_id: str,
    gender: str,
    emotion: str,
    age_group: str,
) -> None:
    """
    Increment counters in the current hour bucket.

    If the bucket row doesn't exist yet it is created with initial values.
    """
    client = get_supabase()
    hour = _hour_bucket()

    # Try to fetch the existing bucket
    result = (
        client.table(TABLE)
        .select("*")
        .eq("camera_id", camera_id)
        .eq("hour_bucket", hour)
        .maybe_single()
        .execute()
    )

    if result.data:
        # Update existing row
        row = result.data
        emotions: dict = row.get("emotions") or {}
        age_groups: dict = row.get("age_groups") or {}

        emotions[emotion] = emotions.get(emotion, 0) + 1
        age_groups[age_group] = age_groups.get(age_group, 0) + 1

        updates = {
            "total": (row.get("total") or 0) + 1,
            "male": (row.get("male") or 0) + (1 if gender == "Man" else 0),
            "female": (row.get("female") or 0) + (1 if gender == "Woman" else 0),
            "emotions": emotions,
            "age_groups": age_groups,
        }
        client.table(TABLE).update(updates).eq("id", row["id"]).execute()
    else:
        # Insert new row
        new_row = {
            "id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "hour_bucket": hour,
            "total": 1,
            "male": 1 if gender == "Man" else 0,
            "female": 1 if gender == "Woman" else 0,
            "emotions": {emotion: 1},
            "age_groups": {age_group: 1},
        }
        client.table(TABLE).insert(new_row).execute()


def get_today_stats(camera_id: Optional[str] = None) -> list[dict]:
    """
    Return aggregated stats for today (UTC), optionally filtered by camera.
    """
    client = get_supabase()
    today_start = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )

    query = (
        client.table(TABLE)
        .select("*")
        .gte("hour_bucket", today_start)
    )
    if camera_id:
        query = query.eq("camera_id", camera_id)

    result = query.execute()
    rows = result.data or []

    # Aggregate per camera
    agg: dict[str, dict] = {}
    for row in rows:
        cid = row["camera_id"]
        if cid not in agg:
            agg[cid] = {
                "camera_id": cid,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "total": 0,
                "male": 0,
                "female": 0,
                "emotions": {},
                "age_groups": {},
            }
        bucket = agg[cid]
        bucket["total"] += row.get("total", 0)
        bucket["male"] += row.get("male", 0)
        bucket["female"] += row.get("female", 0)

        for emo, cnt in (row.get("emotions") or {}).items():
            bucket["emotions"][emo] = bucket["emotions"].get(emo, 0) + cnt
        for ag, cnt in (row.get("age_groups") or {}).items():
            bucket["age_groups"][ag] = bucket["age_groups"].get(ag, 0) + cnt

    return list(agg.values())


def get_hourly_stats(
    camera_id: Optional[str] = None,
    date: Optional[str] = None,
) -> list[dict]:
    """
    Return hour-by-hour stats for a given date (defaults to today).
    """
    client = get_supabase()

    if date:
        day_start = datetime.fromisoformat(date).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
    else:
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    day_end = day_start + timedelta(days=1)

    query = (
        client.table(TABLE)
        .select("*")
        .gte("hour_bucket", day_start.isoformat())
        .lt("hour_bucket", day_end.isoformat())
    )
    if camera_id:
        query = query.eq("camera_id", camera_id)

    query = query.order("hour_bucket", desc=False)
    result = query.execute()

    rows = result.data or []
    for row in rows:
        # Parse the hour number for charting convenience
        hb = row.get("hour_bucket", "")
        try:
            row["hour"] = datetime.fromisoformat(hb).hour
        except Exception:
            row["hour"] = None
        row["date"] = day_start.strftime("%Y-%m-%d")

    return rows


def get_comparison_stats(camera_id: Optional[str] = None) -> dict:
    """
    Compare today's total detections with yesterday's.

    Returns ``{today: {total}, yesterday: {total}, change_pct}``.
    """
    client = get_supabase()

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    # ---- Today ----
    q_today = (
        client.table(TABLE)
        .select("total")
        .gte("hour_bucket", today_start.isoformat())
    )
    if camera_id:
        q_today = q_today.eq("camera_id", camera_id)
    result_today = q_today.execute()

    today_total = sum(r.get("total", 0) for r in (result_today.data or []))

    # ---- Yesterday ----
    q_yesterday = (
        client.table(TABLE)
        .select("total")
        .gte("hour_bucket", yesterday_start.isoformat())
        .lt("hour_bucket", today_start.isoformat())
    )
    if camera_id:
        q_yesterday = q_yesterday.eq("camera_id", camera_id)
    result_yesterday = q_yesterday.execute()

    yesterday_total = sum(r.get("total", 0) for r in (result_yesterday.data or []))

    # ---- Change percentage ----
    if yesterday_total > 0:
        change_pct = round(((today_total - yesterday_total) / yesterday_total) * 100, 1)
    else:
        change_pct = 100.0 if today_total > 0 else 0.0

    return {
        "today": {"total": today_total},
        "yesterday": {"total": yesterday_total},
        "change_pct": change_pct,
    }

