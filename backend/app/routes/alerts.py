"""
API routes for alert rules and alert management.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.alerts import (
    create_alert_rule,
    get_alert_rules,
    get_alert_rule,
    update_alert_rule,
    delete_alert_rule,
    get_alerts,
    get_alert,
    mark_alert_read,
    mark_all_read,
    resolve_alert,
    get_unread_count,
)
from app.models.schemas import AlertRuleCreate, AlertRuleUpdate
from app.services.alert_engine import alert_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# =====================================================================
# Alert Rules
# =====================================================================

@router.post("/rules", status_code=201)
async def api_create_rule(data: AlertRuleCreate):
    """Create a new alert rule."""
    try:
        rule = create_alert_rule(data)
        alert_engine.refresh_rules()
        return rule
    except Exception as exc:
        logger.exception("Failed to create alert rule")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/rules")
async def api_list_rules(camera_id: Optional[str] = Query(None)):
    """List all alert rules, optionally filtered by camera_id."""
    return get_alert_rules(camera_id=camera_id)


@router.put("/rules/{rule_id}")
async def api_update_rule(rule_id: str, data: AlertRuleUpdate):
    """Update an existing alert rule."""
    result = update_alert_rule(rule_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    alert_engine.refresh_rules()
    return result


@router.delete("/rules/{rule_id}")
async def api_delete_rule(rule_id: str):
    """Delete an alert rule."""
    if not delete_alert_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    alert_engine.refresh_rules()
    return {"ok": True}


# =====================================================================
# Alerts
# =====================================================================

@router.get("")
async def api_list_alerts(
    camera_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List alerts with optional filters and pagination."""
    return get_alerts(
        camera_id=camera_id,
        severity=severity,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count")
async def api_unread_count(camera_id: Optional[str] = Query(None)):
    """Return the count of unread alerts."""
    count = get_unread_count(camera_id=camera_id)
    return {"count": count}


@router.put("/{alert_id}/read")
async def api_mark_read(alert_id: str):
    """Mark a single alert as read."""
    if not mark_alert_read(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


class MarkAllReadBody(BaseModel):
    camera_id: Optional[str] = None

@router.post("/mark-all-read")
async def api_mark_all_read(body: MarkAllReadBody = MarkAllReadBody()):
    """Mark all unread alerts as read."""
    count = mark_all_read(camera_id=body.camera_id)
    return {"ok": True, "updated": count}


class ResolveBody(BaseModel):
    resolved_by: str

@router.put("/{alert_id}/resolve")
async def api_resolve_alert(alert_id: str, body: ResolveBody):
    """Resolve an alert."""
    if not resolve_alert(alert_id, body.resolved_by):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}
