-- =========================================================
-- Face Surveillance Schema
-- =========================================================

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";

-- =========================================================
-- Cameras
-- =========================================================
CREATE TABLE IF NOT EXISTS cameras (
    id              VARCHAR(36)  NOT NULL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    rtsp_url        TEXT         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'offline',

    detection_zone  JSON NULL,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_cameras_status (status),
    INDEX idx_cameras_created (created_at)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Detections
-- =========================================================
CREATE TABLE IF NOT EXISTS detections (
    id            VARCHAR(36) NOT NULL PRIMARY KEY,

    camera_id     VARCHAR(36) NOT NULL,

    timestamp     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    faces         JSON NULL,

    INDEX idx_det_camera (camera_id),
    INDEX idx_det_ts (timestamp),

    CONSTRAINT fk_det_cam
        FOREIGN KEY (camera_id)
        REFERENCES cameras(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Snapshots
-- =========================================================
CREATE TABLE IF NOT EXISTS snapshots (
    id             VARCHAR(36) NOT NULL PRIMARY KEY,

    camera_id      VARCHAR(36) NOT NULL,

    detection_id   VARCHAR(36) NOT NULL,

    url            TEXT NOT NULL,

    embedding      LONGBLOB NULL,

    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_snap_cam (camera_id),
    INDEX idx_snap_det (detection_id),
    INDEX idx_snap_ts (created_at),

    CONSTRAINT fk_snap_cam
        FOREIGN KEY (camera_id)
        REFERENCES cameras(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_snap_det
        FOREIGN KEY (detection_id)
        REFERENCES detections(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Hourly Statistics
-- =========================================================
CREATE TABLE IF NOT EXISTS hourly_stats (
    id              VARCHAR(36) NOT NULL PRIMARY KEY,

    camera_id       VARCHAR(36) NOT NULL,

    hour_bucket     TIMESTAMP NOT NULL,

    total           INT NOT NULL DEFAULT 0,
    male            INT NOT NULL DEFAULT 0,
    female          INT NOT NULL DEFAULT 0,

    emotions        JSON NULL,
    age_groups      JSON NULL,

    UNIQUE KEY uq_hourly (camera_id, hour_bucket),

    INDEX idx_hourly_bucket (hour_bucket),

    CONSTRAINT fk_hourly_cam
        FOREIGN KEY (camera_id)
        REFERENCES cameras(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Alert Rules
-- =========================================================
CREATE TABLE IF NOT EXISTS alert_rules (
    id                  VARCHAR(36) NOT NULL PRIMARY KEY,

    name                VARCHAR(255) NOT NULL,

    rule_type           VARCHAR(50) NOT NULL,

    `condition`         JSON NOT NULL,

    severity            VARCHAR(20) NOT NULL DEFAULT 'warning',

    camera_id           VARCHAR(36) NULL,

    is_active           BOOLEAN NOT NULL DEFAULT TRUE,

    cooldown_seconds    INT NOT NULL DEFAULT 60,

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_ar_active (is_active)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Alerts
-- =========================================================
CREATE TABLE IF NOT EXISTS alerts (
    id               VARCHAR(36) NOT NULL PRIMARY KEY,

    rule_id          VARCHAR(36) NULL,

    camera_id        VARCHAR(36) NOT NULL,

    alert_type       VARCHAR(50) NOT NULL,

    severity         VARCHAR(20) NOT NULL DEFAULT 'warning',

    message          TEXT NOT NULL,

    metadata         JSON NULL,

    is_read          BOOLEAN NOT NULL DEFAULT FALSE,

    is_resolved      BOOLEAN NOT NULL DEFAULT FALSE,

    resolved_by      VARCHAR(255) NULL,

    resolved_at      TIMESTAMP NULL,

    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_al_cam (camera_id),
    INDEX idx_al_read (is_read),
    INDEX idx_al_created (created_at),

    CONSTRAINT fk_al_cam
        FOREIGN KEY (camera_id)
        REFERENCES cameras(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- Optional Performance Optimization
-- =========================================================
SET GLOBAL innodb_flush_log_at_trx_commit = 2;
SET GLOBAL sync_binlog = 0;