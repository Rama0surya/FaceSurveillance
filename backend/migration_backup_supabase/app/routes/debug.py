"""
Debug routes — mock data generation.

These routes are only registered when the app is running in development mode
(i.e. when the environment variable ``ENV`` is not set to ``production``).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/debug", tags=["debug"])

logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    """Return True if we're NOT in production."""
    return os.getenv("ENV", "development").lower() != "production"


@router.post("/generate-mock")
async def generate_mock(count: int = 100):
    """
    Populate the database with mock detection data for demo purposes.

    **Only available in development mode.**

    Query params:
        - ``count``: number of detections to generate (default 100)
    """
    if not is_dev_mode():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available in development mode.",
        )

    from app.services.mock_data import generate_mock_data

    try:
        result = generate_mock_data(num_detections=count)
        logger.info("Mock data generated: %s", result)
        return {
            "message": "Mock data generated successfully",
            "summary": result,
        }
    except Exception as e:
        logger.exception("Mock data generation failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-mock")
async def clear_mock():
    """
    Clear all data from detection-related tables (for resetting demo state).

    **Only available in development mode.**
    """
    if not is_dev_mode():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available in development mode.",
        )

    from app.core.supabase_client import get_supabase

    try:
        client = get_supabase()
        # Delete in order to respect foreign key constraints
        client.table("snapshots").delete().neq("id", "").execute()
        client.table("detections").delete().neq("id", "").execute()
        client.table("hourly_stats").delete().neq("id", "").execute()

        return {"message": "All detection data cleared"}
    except Exception as e:
        logger.exception("Clear mock data failed")
        raise HTTPException(status_code=500, detail=str(e))
