"""
Statistics routes — today summary, hourly breakdown, and day-over-day comparison.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.db.stats import get_today_stats, get_hourly_stats, get_comparison_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/today")
async def today_stats(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
):
    """
    Get today's aggregated stats per camera.

    Returns total detections, gender breakdown, emotion distribution,
    and age-group counts.

    Response: ``{total, male, female, emotions:{}, ages:{}}``
    """
    data = get_today_stats(camera_id=camera_id)

    # If a specific camera_id is provided, return the single aggregated result
    if camera_id and data:
        result = data[0]
        return {
            "total": result.get("total", 0),
            "male": result.get("male", 0),
            "female": result.get("female", 0),
            "emotions": result.get("emotions", {}),
            "ages": result.get("age_groups", {}),
        }

    return {"data": data}


@router.get("/hourly")
async def hourly_stats(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
):
    """
    Get hour-by-hour detection data for charting.

    Returns ``[{hour, total, male, female}]`` for each hour bucket.
    """
    data = get_hourly_stats(camera_id=camera_id, date=date)

    # Slim the response to the requested format
    result = [
        {
            "hour": row.get("hour"),
            "total": row.get("total", 0),
            "male": row.get("male", 0),
            "female": row.get("female", 0),
        }
        for row in data
    ]
    return {"data": result}


@router.get("/comparison")
async def comparison_stats(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
):
    """
    Compare today's detection count with yesterday's.

    Returns ``{today: {total}, yesterday: {total}, change_pct}``.
    """
    return get_comparison_stats(camera_id=camera_id)
