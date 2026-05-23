"""
=============================================================================
Face Surveillance - AI Semantic Search Routes (CLIP)
=============================================================================
Endpoints:
- POST /api/search/text: Text-to-Image search (e.g. "man wearing glasses")
- POST /api/search/image: Image-to-Image reverse face search (upload photo)
=============================================================================
"""

from __future__ import annotations

import io
import logging
from typing import Optional
from PIL import Image

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.db.detections import search_snapshots_by_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


class TextSearchRequest(BaseModel):
    query: str
    camera_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: Optional[int] = 20
    similarity_threshold: Optional[float] = 0.15


@router.post("/text")
async def search_by_text(req: TextSearchRequest):
    """
    Search snapshots by text description (e.g. 'man smiling', 'woman with red hair').
    """
    if not settings.CLIP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI Search (CLIP) is currently disabled on this server."
        )

    if not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query text cannot be empty."
        )

    try:
        # Generate query embedding
        query_vector = embedding_service.encode_text(req.query.strip())

        # Perform cosine similarity lookup in database
        results = search_snapshots_by_embedding(
            query_embedding=query_vector,
            camera_id=req.camera_id,
            date_from=req.date_from,
            date_to=req.date_to,
            limit=req.limit or 20,
            similarity_threshold=req.similarity_threshold or 0.15
        )

        return {"data": results, "count": len(results)}

    except Exception as e:
        logger.exception("AI Text search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Search error: {str(e)}"
        )


@router.post("/image")
async def search_by_image(
    file: UploadFile = File(...),
    camera_id: Optional[str] = Form(None),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str] = Form(None),
    limit: Optional[int] = Form(20),
    similarity_threshold: Optional[float] = Form(0.15),
):
    """
    Search snapshots using an uploaded reference face/image (reverse face search).
    """
    if not settings.CLIP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI Search (CLIP) is currently disabled on this server."
        )

    try:
        # Read uploaded image bytes
        contents = await file.read()
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")

        # Generate reference embedding
        query_vector = embedding_service.encode_image(pil_img)

        # Perform cosine similarity lookup in database
        results = search_snapshots_by_embedding(
            query_embedding=query_vector,
            camera_id=camera_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit or 20,
            similarity_threshold=similarity_threshold or 0.15
        )

        return {"data": results, "count": len(results)}

    except Exception as e:
        logger.exception("AI Image search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Search error: {str(e)}"
        )
