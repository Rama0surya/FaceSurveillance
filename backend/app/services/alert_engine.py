"""
Alert Engine — evaluates detection results against active alert rules.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.core.websocket import manager as ws_manager
from app.db.alerts import (
    check_cooldown,
    create_alert,
    create_alert_rule,
    get_alert_rules,
)
from app.models.schemas import AlertRuleCreate

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evaluates detection results against active alert rules."""

    def __init__(self) -> None:
        self._rules_cache: list[dict] = []
        self._cache_ttl: int = 30
        self._last_cache_time: float = 0

    def refresh_rules(self) -> None:
        """Fetch active rules from database and cache them."""
        try:
            all_rules = get_alert_rules()
            self._rules_cache = [r for r in all_rules if r.get("is_active", True)]
            self._last_cache_time = time.time()
        except Exception:
            logger.exception("Failed to refresh alert rules cache")

    def _ensure_cache(self) -> None:
        if time.time() - self._last_cache_time > self._cache_ttl:
            self.refresh_rules()

    def evaluate(self, camera_id: str, faces: list[dict], loop: asyncio.AbstractEventLoop) -> list[dict]:
        """Evaluate all active rules against detection results."""
        self._ensure_cache()
        if not self._rules_cache or not faces:
            return []

        triggered: list[dict] = []
        for rule in self._rules_cache:
            try:
                rule_camera = rule.get("camera_id")
                if rule_camera and rule_camera != camera_id:
                    continue
                match = self._check_rule(rule, faces)
                if not match:
                    continue
                rule_id = rule["id"]
                if not check_cooldown(rule_id, rule.get("cooldown_seconds", 60)):
                    continue

                message = self._build_message(rule, match, camera_id)
                metadata = {"rule_name": rule.get("name"), "match_details": match, "face_count": len(faces)}
                alert_rec = create_alert(
                    rule_id=rule_id, camera_id=camera_id,
                    alert_type=rule.get("rule_type", "unknown"),
                    severity=rule.get("severity", "warning"),
                    message=message, metadata=metadata,
                )
                triggered.append(alert_rec)

                ws_alert = {"type": "alert", "alert": {
                    "id": alert_rec.get("id", ""), "rule_id": rule_id,
                    "camera_id": camera_id, "alert_type": rule.get("rule_type"),
                    "severity": rule.get("severity", "warning"), "message": message,
                    "metadata": metadata, "is_read": False, "is_resolved": False,
                    "created_at": alert_rec.get("created_at", ""),
                }}
                try:
                    asyncio.run_coroutine_threadsafe(ws_manager.broadcast_alert(ws_alert), loop)
                except Exception:
                    logger.exception("WS alert broadcast failed")
            except Exception:
                logger.exception("Error evaluating rule %s", rule.get("id"))
        return triggered

    def _check_rule(self, rule: dict, faces: list[dict]) -> Optional[dict]:
        rt = rule.get("rule_type", "")
        cond = rule.get("condition", {})
        if rt == "emotion":
            em = cond.get("emotion", "")
            th = cond.get("threshold", 1)
            m = [f for f in faces if f.get("emotion") == em]
            return {"matched_emotion": em, "count": len(m), "threshold": th} if len(m) >= th else None
        elif rt == "crowd_count":
            mc = cond.get("min_count", 10)
            return {"face_count": len(faces), "min_count": mc} if len(faces) >= mc else None
        elif rt == "age_group":
            ag = cond.get("age_group", "")
            th = cond.get("threshold", 1)
            m = [f for f in faces if f.get("age_group") == ag]
            return {"matched_age_group": ag, "count": len(m), "threshold": th} if len(m) >= th else None
        elif rt == "unknown_face":
            th = cond.get("threshold", 1)
            m = [f for f in faces if f.get("identity") == "unknown"]
            return {"unknown_count": len(m), "threshold": th} if len(m) >= th else None
        return None

    def _build_message(self, rule: dict, match: dict, camera_id: str) -> str:
        name = rule.get("name", "Alert")
        rt = rule.get("rule_type", "")
        sev = rule.get("severity", "warning").upper()
        cam = camera_id[:8]
        if rt == "emotion":
            return f"[{sev}] {name}: {match.get('count')} wajah emosi '{match.get('matched_emotion')}' di kamera {cam}"
        elif rt == "crowd_count":
            return f"[{sev}] {name}: {match.get('face_count')} orang terdeteksi di kamera {cam}"
        elif rt == "age_group":
            return f"[{sev}] {name}: {match.get('count')} usia '{match.get('matched_age_group')}' di kamera {cam}"
        elif rt == "unknown_face":
            return f"[{sev}] {name}: {match.get('unknown_count')} wajah tidak dikenal di kamera {cam}"
        return f"[{sev}] {name} terpicu di kamera {cam}"


alert_engine = AlertEngine()


def seed_default_rules() -> None:
    """Create default alert rules if none exist yet."""
    try:
        if get_alert_rules():
            logger.info("Alert rules already exist, skipping seed.")
            return
        defaults = [
            AlertRuleCreate(name="Emosi Marah Terdeteksi", rule_type="emotion",
                            condition={"emotion": "angry", "threshold": 1}, severity="critical", cooldown_seconds=120),
            AlertRuleCreate(name="Emosi Takut Terdeteksi", rule_type="emotion",
                            condition={"emotion": "fear", "threshold": 1}, severity="critical", cooldown_seconds=120),
            AlertRuleCreate(name="Kerumunan Terdeteksi", rule_type="crowd_count",
                            condition={"min_count": 10}, severity="warning", cooldown_seconds=300),
            AlertRuleCreate(name="Anak Terdeteksi", rule_type="age_group",
                            condition={"age_group": "anak", "threshold": 1}, severity="info", cooldown_seconds=180),
        ]
        for rd in defaults:
            create_alert_rule(rd)
            logger.info("Seeded: %s", rd.name)
        logger.info("Default alert rules seeded ✓")
    except Exception:
        logger.exception("Failed to seed default alert rules")
