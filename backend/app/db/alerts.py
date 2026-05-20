from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import text
from app.core.db_client import get_db
from app.models.schemas import AlertRuleCreate, AlertRuleUpdate

logger = logging.getLogger(__name__)


# ---------- Alert Rules ----------

def create_alert_rule(data: AlertRuleCreate) -> dict:
    db = get_db()
    try:
        rid = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
        db.execute(text("""
            INSERT INTO alert_rules (id,name,rule_type,`condition`,severity,camera_id,is_active,cooldown_seconds,created_at,updated_at)
            VALUES (:id,:name,:rt,:cond,:sev,:cam,:act,:cool,:now,:now)
        """), {"id": rid, "name": data.name, "rt": data.rule_type, "cond": json.dumps(data.condition),
               "sev": data.severity, "cam": data.camera_id, "act": 1 if data.is_active else 0,
               "cool": data.cooldown_seconds, "now": now})
        db.commit(); return get_alert_rule(rid)
    except Exception:
        db.rollback(); logger.exception("create_alert_rule failed"); raise
    finally:
        db.close()


def get_alert_rules(camera_id=None) -> list[dict]:
    db = get_db()
    try:
        params = {}; cf = ""
        if camera_id: cf = "AND camera_id = :c"; params["c"] = camera_id
        rows = db.execute(text(f"SELECT * FROM alert_rules WHERE 1=1 {cf} ORDER BY created_at DESC"), params).mappings().all()
        return [_par(dict(r)) for r in rows]
    except Exception:
        logger.exception("get_alert_rules failed"); return []
    finally:
        db.close()


def get_alert_rule(rule_id: str) -> Optional[dict]:
    db = get_db()
    try:
        row = db.execute(text("SELECT * FROM alert_rules WHERE id=:id LIMIT 1"), {"id": rule_id}).mappings().first()
        return _par(dict(row)) if row else None
    except Exception:
        logger.exception("get_alert_rule failed"); return None
    finally:
        db.close()


def update_alert_rule(rule_id: str, data: AlertRuleUpdate) -> Optional[dict]:
    updates = data.model_dump(exclude_none=True)
    if not updates: return get_alert_rule(rule_id)
    db = get_db()
    try:
        if "condition" in updates: updates["condition"] = json.dumps(updates["condition"])
        if "is_active" in updates: updates["is_active"] = 1 if updates["is_active"] else 0
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        sc = ", ".join((f"`{k}`=:{k}" if k=="condition" else f"{k}=:{k}") for k in updates)
        updates["rule_id"] = rule_id
        db.execute(text(f"UPDATE alert_rules SET {sc} WHERE id=:rule_id"), updates)
        db.commit(); return get_alert_rule(rule_id)
    except Exception:
        db.rollback(); logger.exception("update_alert_rule failed"); return None
    finally:
        db.close()


def delete_alert_rule(rule_id: str) -> bool:
    db = get_db()
    try:
        r = db.execute(text("DELETE FROM alert_rules WHERE id=:id"), {"id": rule_id})
        db.commit(); return r.rowcount > 0
    except Exception:
        db.rollback(); logger.exception("delete_alert_rule failed"); return False
    finally:
        db.close()


# ---------- Alerts ----------

def create_alert(rule_id, camera_id, alert_type, severity, message, metadata=None) -> dict:
    db = get_db()
    try:
        aid = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
        db.execute(text("""
            INSERT INTO alerts (id,rule_id,camera_id,alert_type,severity,message,metadata,is_read,is_resolved,created_at)
            VALUES (:id,:rid,:cam,:at,:sev,:msg,:meta,0,0,:now)
        """), {"id": aid, "rid": rule_id, "cam": camera_id, "at": alert_type,
               "sev": severity, "msg": message, "meta": json.dumps(metadata) if metadata else None, "now": now})
        db.commit(); return get_alert(aid)
    except Exception:
        db.rollback(); logger.exception("create_alert failed"); raise
    finally:
        db.close()


def get_alerts(camera_id=None, severity=None, is_read=None, limit=50, offset=0) -> list[dict]:
    db = get_db()
    try:
        conds, params = [], {"limit": limit, "offset": offset}
        if camera_id:          conds.append("camera_id=:cam");   params["cam"] = camera_id
        if severity:           conds.append("severity=:sev");    params["sev"] = severity
        if is_read is not None: conds.append("is_read=:ir");     params["ir"] = 1 if is_read else 0
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = db.execute(text(f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
        return [_paa(dict(r)) for r in rows]
    except Exception:
        logger.exception("get_alerts failed"); return []
    finally:
        db.close()


def get_alert(alert_id: str) -> Optional[dict]:
    db = get_db()
    try:
        row = db.execute(text("SELECT * FROM alerts WHERE id=:id LIMIT 1"), {"id": alert_id}).mappings().first()
        return _paa(dict(row)) if row else None
    except Exception:
        logger.exception("get_alert failed"); return None
    finally:
        db.close()


def mark_alert_read(alert_id: str) -> bool:
    db = get_db()
    try:
        r = db.execute(text("UPDATE alerts SET is_read=1 WHERE id=:id"), {"id": alert_id})
        db.commit(); return r.rowcount > 0
    except Exception:
        db.rollback(); return False
    finally:
        db.close()


def mark_all_read(camera_id=None) -> int:
    db = get_db()
    try:
        params = {}; cf = ""
        if camera_id: cf = "AND camera_id=:c"; params["c"] = camera_id
        r = db.execute(text(f"UPDATE alerts SET is_read=1 WHERE is_read=0 {cf}"), params)
        db.commit(); return r.rowcount
    except Exception:
        db.rollback(); return 0
    finally:
        db.close()


def resolve_alert(alert_id: str, resolved_by: str) -> bool:
    db = get_db()
    try:
        r = db.execute(text("""
            UPDATE alerts SET is_resolved=1, resolved_by=:by, resolved_at=:at WHERE id=:id
        """), {"by": resolved_by, "at": datetime.now(timezone.utc).isoformat(), "id": alert_id})
        db.commit(); return r.rowcount > 0
    except Exception:
        db.rollback(); return False
    finally:
        db.close()


def get_unread_count(camera_id=None) -> int:
    db = get_db()
    try:
        params = {}; cf = ""
        if camera_id: cf = "AND camera_id=:c"; params["c"] = camera_id
        return db.execute(text(f"SELECT COUNT(*) FROM alerts WHERE is_read=0 {cf}"), params).scalar() or 0
    except Exception:
        return 0
    finally:
        db.close()


def check_cooldown(rule_id: str, cooldown_seconds: int) -> bool:
    db = get_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)).isoformat()
        cnt = db.execute(text("SELECT COUNT(*) FROM alerts WHERE rule_id=:rid AND created_at>=:cut"),
                         {"rid": rule_id, "cut": cutoff}).scalar() or 0
        return cnt == 0
    except Exception:
        return False
    finally:
        db.close()


# ---------- Helpers ----------

def _par(row: dict) -> dict:
    if row.get("condition") and isinstance(row["condition"], str):
        row["condition"] = json.loads(row["condition"])
    row["is_active"] = bool(row.get("is_active", 0))
    for c in ("created_at","updated_at"):
        if row.get(c): row[c] = str(row[c])
    return row

def _paa(row: dict) -> dict:
    if row.get("metadata") and isinstance(row["metadata"], str):
        row["metadata"] = json.loads(row["metadata"])
    row["is_read"] = bool(row.get("is_read", 0))
    row["is_resolved"] = bool(row.get("is_resolved", 0))
    for c in ("created_at","resolved_at"):
        if row.get(c): row[c] = str(row[c])
    return row