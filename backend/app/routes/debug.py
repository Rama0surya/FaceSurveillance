from __future__ import annotations
import logging, os
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

router = APIRouter(prefix="/api/debug", tags=["debug"])
logger = logging.getLogger(__name__)

def is_dev_mode() -> bool:
    return os.getenv("ENV","development").lower() != "production"

@router.post("/generate-mock")
async def generate_mock(count: int = 100):
    if not is_dev_mode(): raise HTTPException(403,"Only in development mode.")
    from app.services.mock_data import generate_mock_data
    try:
        return {"message":"Mock data generated","summary": generate_mock_data(num_detections=count)}
    except Exception as e:
        logger.exception("Mock data generation failed"); raise HTTPException(500, str(e))

@router.delete("/clear-mock")
async def clear_mock():
    if not is_dev_mode(): raise HTTPException(403,"Only in development mode.")
    from app.core.db_client import get_db
    db = get_db()
    try:
        db.execute(text("DELETE FROM alerts"))
        db.execute(text("DELETE FROM snapshots"))
        db.execute(text("DELETE FROM detections"))
        db.execute(text("DELETE FROM hourly_stats"))
        db.commit()
        return {"message":"All detection data cleared"}
    except Exception as e:
        db.rollback(); logger.exception("clear-mock failed"); raise HTTPException(500, str(e))
    finally:
        db.close()