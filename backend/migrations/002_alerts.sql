-- ============================================================
-- Migration 002: Alert System Tables
-- ============================================================

-- Alert Rules — configurable rules that trigger alerts
CREATE TABLE IF NOT EXISTS alert_rules (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT            NOT NULL,
    rule_type       TEXT            NOT NULL,          -- "emotion", "crowd_count", "unknown_face", "age_group"
    condition       JSONB           NOT NULL,          -- e.g. {"emotion": "angry", "threshold": 1}
    severity        TEXT            DEFAULT 'warning',  -- "info", "warning", "critical"
    camera_id       UUID            REFERENCES cameras(id) ON DELETE CASCADE,  -- NULL = semua kamera
    is_active       BOOLEAN         DEFAULT true,
    cooldown_seconds INTEGER        DEFAULT 60,
    created_at      TIMESTAMPTZ     DEFAULT now(),
    updated_at      TIMESTAMPTZ     DEFAULT now()
);

-- Alerts — triggered alert records
CREATE TABLE IF NOT EXISTS alerts (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id         UUID            REFERENCES alert_rules(id) ON DELETE SET NULL,
    camera_id       UUID            REFERENCES cameras(id) ON DELETE CASCADE,
    alert_type      TEXT            NOT NULL,          -- same as rule_type
    severity        TEXT            DEFAULT 'warning',
    message         TEXT            NOT NULL,
    metadata        JSONB,                             -- snapshot_url, face_data, etc.
    is_read         BOOLEAN         DEFAULT false,
    is_resolved     BOOLEAN         DEFAULT false,
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_alerts_camera_id   ON alerts(camera_id);
CREATE INDEX IF NOT EXISTS idx_alerts_is_read     ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at  ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id     ON alerts(rule_id);

CREATE INDEX IF NOT EXISTS idx_alert_rules_camera_id ON alert_rules(camera_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_is_active ON alert_rules(is_active);

-- Auto-update updated_at on alert_rules
CREATE OR REPLACE FUNCTION update_alert_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_alert_rules_updated_at ON alert_rules;
CREATE TRIGGER trigger_alert_rules_updated_at
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_alert_rules_updated_at();
