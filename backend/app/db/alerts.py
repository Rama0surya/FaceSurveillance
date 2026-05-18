"""
CRUD operations for the ``alert_rules`` and ``alerts`` tables.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.supabase_client import get_supabase
from app.models.schemas import AlertRuleCreate, AlertRuleUpdate

logger = logging.getLogger(__name__)

ALERT_RULES_TABLE = "alert_rules"
ALERTS_TABLE = "alerts"


# =====================================================================
# Alert Rules CRUD
# =====================================================================

def create_alert_rule(data: AlertRuleCreate) -> dict:
    """Insert a new alert rule and return it."""
    client = get_supabase()
    row = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "rule_type": data.rule_type,
        "condition": data.condition,
        "severity": data.severity,
        "camera_id": data.camera_id,
        "is_active": data.is_active,
        "cooldown_seconds": data.cooldown_seconds,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = client.table(ALERT_RULES_TABLE).insert(row).execute()
        return result.data[0] if result.data else row
    except Exception:
        logger.exception("Failed to create alert rule")
        raise


def get_alert_rules(camera_id: Optional[str] = None) -> list[dict]:
    """Return alert rules, optionally filtered by camera_id."""
    client = get_supabase()
    try:
        query = client.table(ALERT_RULES_TABLE).select("*")
        if camera_id:
            query = query.eq("camera_id", camera_id)
        query = query.order("created_at", desc=True)
        result = query.execute()
        return result.data or []
    except Exception:
        logger.exception("Failed to fetch alert rules")
        return []


def get_alert_rule(rule_id: str) -> Optional[dict]:
    """Fetch a single alert rule by ID."""
    client = get_supabase()
    try:
        result = (
            client.table(ALERT_RULES_TABLE)
            .select("*")
            .eq("id", rule_id)
            .maybe_single()
            .execute()
        )
        return result.data
    except Exception:
        logger.exception("Failed to fetch alert rule %s", rule_id)
        return None


def update_alert_rule(rule_id: str, data: AlertRuleUpdate) -> Optional[dict]:
    """Update fields on an existing alert rule."""
    client = get_supabase()
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return get_alert_rule(rule_id)

    try:
        result = (
            client.table(ALERT_RULES_TABLE)
            .update(updates)
            .eq("id", rule_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]
    except Exception:
        logger.exception("Failed to update alert rule %s", rule_id)
        return None


def delete_alert_rule(rule_id: str) -> bool:
    """Delete an alert rule. Returns True if a row was removed."""
    client = get_supabase()
    try:
        result = client.table(ALERT_RULES_TABLE).delete().eq("id", rule_id).execute()
        return bool(result.data)
    except Exception:
        logger.exception("Failed to delete alert rule %s", rule_id)
        return False


# =====================================================================
# Alerts CRUD
# =====================================================================

def create_alert(
    rule_id: Optional[str],
    camera_id: str,
    alert_type: str,
    severity: str,
    message: str,
    metadata: Optional[dict] = None,
) -> dict:
    """Insert a new alert record and return it."""
    client = get_supabase()
    row = {
        "id": str(uuid.uuid4()),
        "rule_id": rule_id,
        "camera_id": camera_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "metadata": metadata,
        "is_read": False,
        "is_resolved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = client.table(ALERTS_TABLE).insert(row).execute()
        return result.data[0] if result.data else row
    except Exception:
        logger.exception("Failed to create alert")
        raise


def get_alerts(
    camera_id: Optional[str] = None,
    severity: Optional[str] = None,
    is_read: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return alerts with optional filters and pagination."""
    client = get_supabase()
    try:
        query = client.table(ALERTS_TABLE).select("*")

        if camera_id:
            query = query.eq("camera_id", camera_id)
        if severity:
            query = query.eq("severity", severity)
        if is_read is not None:
            query = query.eq("is_read", is_read)

        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        return result.data or []
    except Exception:
        logger.exception("Failed to fetch alerts")
        return []


def get_alert(alert_id: str) -> Optional[dict]:
    """Fetch a single alert by ID."""
    client = get_supabase()
    try:
        result = (
            client.table(ALERTS_TABLE)
            .select("*")
            .eq("id", alert_id)
            .maybe_single()
            .execute()
        )
        return result.data
    except Exception:
        logger.exception("Failed to fetch alert %s", alert_id)
        return None


def mark_alert_read(alert_id: str) -> bool:
    """Mark a single alert as read."""
    client = get_supabase()
    try:
        result = (
            client.table(ALERTS_TABLE)
            .update({"is_read": True})
            .eq("id", alert_id)
            .execute()
        )
        return bool(result.data)
    except Exception:
        logger.exception("Failed to mark alert %s as read", alert_id)
        return False


def mark_all_read(camera_id: Optional[str] = None) -> int:
    """Mark all unread alerts as read. Returns count of updated rows."""
    client = get_supabase()
    try:
        query = (
            client.table(ALERTS_TABLE)
            .update({"is_read": True})
            .eq("is_read", False)
        )
        if camera_id:
            query = query.eq("camera_id", camera_id)

        result = query.execute()
        return len(result.data) if result.data else 0
    except Exception:
        logger.exception("Failed to mark all alerts as read")
        return 0


def resolve_alert(alert_id: str, resolved_by: str) -> bool:
    """Resolve an alert with resolver info and timestamp."""
    client = get_supabase()
    try:
        result = (
            client.table(ALERTS_TABLE)
            .update({
                "is_resolved": True,
                "resolved_by": resolved_by,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", alert_id)
            .execute()
        )
        return bool(result.data)
    except Exception:
        logger.exception("Failed to resolve alert %s", alert_id)
        return False


def get_unread_count(camera_id: Optional[str] = None) -> int:
    """Return the count of unread alerts."""
    client = get_supabase()
    try:
        query = (
            client.table(ALERTS_TABLE)
            .select("id", count="exact")
            .eq("is_read", False)
        )
        if camera_id:
            query = query.eq("camera_id", camera_id)

        result = query.execute()
        return result.count if result.count is not None else 0
    except Exception:
        logger.exception("Failed to get unread alert count")
        return 0


def check_cooldown(rule_id: str, cooldown_seconds: int) -> bool:
    """
    Check whether enough time has passed since the last alert for a rule.

    Returns True if it's OK to trigger (cooldown elapsed), False otherwise.
    """
    client = get_supabase()
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        ).isoformat()

        result = (
            client.table(ALERTS_TABLE)
            .select("id", count="exact")
            .eq("rule_id", rule_id)
            .gte("created_at", cutoff)
            .execute()
        )

        count = result.count if result.count is not None else 0
        return count == 0  # True = no recent alerts, OK to trigger
    except Exception:
        logger.exception("Failed to check cooldown for rule %s", rule_id)
        return False  # On error, don't trigger
