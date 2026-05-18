-- =========================================================================
-- Face Surveillance — Initial Database Schema
-- Run this in Supabase SQL Editor (https://supabase.com/dashboard)
-- =========================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------
-- 1. cameras
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cameras (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    rtsp_url        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'offline'
                    CHECK (status IN ('offline', 'live', 'processing')),
    detection_zone  JSONB DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration helper: add column if table already exists
-- ALTER TABLE cameras ADD COLUMN IF NOT EXISTS detection_zone JSONB DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_cameras_status ON cameras (status);

-- -----------------------------------------------------------------
-- 2. detections
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detections (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id   UUID NOT NULL REFERENCES cameras (id) ON DELETE CASCADE,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    faces       JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_detections_camera_id ON detections (camera_id);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections (timestamp DESC);

-- -----------------------------------------------------------------
-- 3. snapshots
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshots (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id     UUID NOT NULL REFERENCES cameras (id) ON DELETE CASCADE,
    detection_id  UUID NOT NULL REFERENCES detections (id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_camera_id ON snapshots (camera_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots (created_at DESC);

-- -----------------------------------------------------------------
-- 4. hourly_stats
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hourly_stats (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id    UUID NOT NULL REFERENCES cameras (id) ON DELETE CASCADE,
    hour_bucket  TIMESTAMPTZ NOT NULL,
    total        INTEGER NOT NULL DEFAULT 0,
    male         INTEGER NOT NULL DEFAULT 0,
    female       INTEGER NOT NULL DEFAULT 0,
    emotions     JSONB NOT NULL DEFAULT '{}'::jsonb,
    age_groups   JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- One bucket per camera per hour
    UNIQUE (camera_id, hour_bucket)
);

CREATE INDEX IF NOT EXISTS idx_hourly_stats_camera ON hourly_stats (camera_id);
CREATE INDEX IF NOT EXISTS idx_hourly_stats_bucket ON hourly_stats (hour_bucket DESC);

-- -----------------------------------------------------------------
-- 5. Row Level Security (optional — enable if using anon key)
-- -----------------------------------------------------------------

-- Allow full access via service_role key (backend).
-- If you use the anon key, uncomment and adjust these policies.

-- ALTER TABLE cameras      ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE detections   ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE snapshots    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE hourly_stats ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY "Allow all for service role" ON cameras
--     FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "Allow all for service role" ON detections
--     FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "Allow all for service role" ON snapshots
--     FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "Allow all for service role" ON hourly_stats
--     FOR ALL USING (true) WITH CHECK (true);
