"""
Detection & snapshot query routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.db.detections import query_detections, get_snapshots, query_snapshots_enriched

router = APIRouter(prefix="/api", tags=["detections"])


@router.get("/detections")
async def list_detections(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    date_from: Optional[str] = Query(None, description="ISO8601 start date"),
    date_to: Optional[str] = Query(None, description="ISO8601 end date"),
    emotion: Optional[str] = Query(None, description="Filter by dominant emotion"),
    gender: Optional[str] = Query(None, description="Filter by gender (male/female)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    Query face detections with optional filters.

    Supports filtering by camera, date range, emotion, and gender.
    Results are paginated.
    """
    data = query_detections(
        camera_id=camera_id,
        date_from=date_from,
        date_to=date_to,
        emotion=emotion,
        gender=gender,
        page=page,
        per_page=per_page,
    )
    return {
        "page": page,
        "per_page": per_page,
        "count": len(data),
        "data": data,
    }


@router.get("/snapshots")
async def list_snapshots(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    emotion: Optional[str] = Query(None, description="Filter by emotion (happy, sad, neutral, etc.)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List face-crop snapshots with enriched face data.

    Returns: ``[{id, url, gender, emotion, age, age_group, camera_name, timestamp}]``
    """
    data = query_snapshots_enriched(
        camera_id=camera_id,
        date=date,
        emotion=emotion,
        limit=limit,
        offset=offset,
    )
    return {
        "limit": limit,
        "offset": offset,
        "count": len(data),
        "data": data,
    }
