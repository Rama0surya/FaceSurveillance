"""
Pydantic models for request / response bodies and WebSocket messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =====================================================================
# Camera
# =====================================================================

class CameraCreate(BaseModel):
    """Body for POST /api/cameras."""
    name: str = Field(..., min_length=1, max_length=255, examples=["Lobby Cam 1"])
    rtsp_url: str = Field(..., min_length=1, examples=["rtsp://192.168.1.10:554/stream"])
    detection_zone: Optional[dict[str, Any]] = Field(
        None,
        description='Detection polygon: {"type": "polygon", "points": [[x1,y1], [x2,y2], ...]}',
        examples=[{"type": "polygon", "points": [[100, 100], [400, 100], [400, 400], [100, 400]]}],
    )


class CameraUpdate(BaseModel):
    """Body for PUT /api/cameras/{id}."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    rtsp_url: Optional[str] = Field(None, min_length=1)
    detection_zone: Optional[dict[str, Any]] = Field(
        None,
        description='Detection polygon: {"type": "polygon", "points": [[x1,y1], [x2,y2], ...]}',
    )


class CameraResponse(BaseModel):
    """Returned by every camera endpoint."""
    id: str
    name: str
    rtsp_url: str
    status: str = "offline"  # offline | live | processing
    detection_zone: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None


# =====================================================================
# Detection
# =====================================================================

class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class DetectionFace(BaseModel):
    id: str
    bbox: BBox
    gender: str            # male | female
    emotion: str           # angry, disgust, fear, happy, sad, surprise, neutral
    age_group: str         # anak, remaja, dewasa, lansia
    age: int
    confidence: float
    snapshot_url: str


class DetectionResponse(BaseModel):
    id: str
    camera_id: str
    timestamp: str
    faces: list[DetectionFace]


# =====================================================================
# Stats
# =====================================================================

class StatsResponse(BaseModel):
    camera_id: str
    date: str
    hour: Optional[int] = None
    total: int = 0
    male: int = 0
    female: int = 0
    emotions: dict = {}      # e.g. {"happy": 5, "neutral": 12}
    age_groups: dict = {}    # e.g. {"dewasa": 10, "anak": 3}


class TodayStatsResponse(BaseModel):
    camera_id: str
    date: str
    total: int = 0
    male: int = 0
    female: int = 0
    emotions: dict = {}
    age_groups: dict = {}


# =====================================================================
# Snapshots
# =====================================================================

class SnapshotResponse(BaseModel):
    id: str
    camera_id: str
    detection_id: str
    url: str
    created_at: Optional[str] = None


# =====================================================================
# WebSocket messages
# =====================================================================

class StatsDelta(BaseModel):
    total: int
    male: int = 0
    female: int = 0
    emotion: Optional[str] = None


class WSDetectionMessage(BaseModel):
    """Message pushed via /ws/stream/{camera_id}."""
    type: str = "detection"
    camera_id: str
    timestamp: str
    faces: list[DetectionFace]
    stats_delta: StatsDelta


class WSFrameMessage(BaseModel):
    """Frame broadcast message via /ws/stream/{camera_id}."""
    type: str = "frame"
    camera_id: str
    data: str  # base64-encoded JPEG


class WSStatsMessage(BaseModel):
    """Message pushed via /ws/stats."""
    type: str = "stats_update"
    timestamp: str
    cameras: list[TodayStatsResponse]


# =====================================================================
# Alerts
# =====================================================================

class AlertRuleCreate(BaseModel):
    """Body for POST /api/alerts/rules."""
    name: str
    rule_type: str  # "emotion" | "crowd_count" | "unknown_face" | "age_group"
    condition: dict
    severity: str = "warning"
    camera_id: Optional[str] = None
    is_active: bool = True
    cooldown_seconds: int = 60


class AlertRuleUpdate(BaseModel):
    """Body for PUT /api/alerts/rules/{rule_id}."""
    name: Optional[str] = None
    condition: Optional[dict] = None
    severity: Optional[str] = None
    is_active: Optional[bool] = None
    cooldown_seconds: Optional[int] = None


class AlertRuleResponse(BaseModel):
    """Returned by alert rule endpoints."""
    id: str
    name: str
    rule_type: str
    condition: dict
    severity: str
    camera_id: Optional[str] = None
    is_active: bool
    cooldown_seconds: int
    created_at: Optional[str] = None


class AlertResponse(BaseModel):
    """Returned by alert endpoints."""
    id: str
    rule_id: Optional[str] = None
    camera_id: str
    alert_type: str
    severity: str
    message: str
    metadata: Optional[dict] = None
    is_read: bool
    is_resolved: bool
    created_at: Optional[str] = None


class WSAlertMessage(BaseModel):
    """Message pushed via /ws/alerts."""
    type: str = "alert"
    alert: AlertResponse


# =====================================================================
# Pagination
# =====================================================================

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page
